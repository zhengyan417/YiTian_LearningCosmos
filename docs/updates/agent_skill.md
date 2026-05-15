# Skill 抽象层设计文档

> **目标**：在不破坏现有 LangGraph + tool calling 范式的前提下，给主 agent 增加一层"能力封装"（skill），让 agent 知道"何时该用什么"，并把现有 deep_research / A2A 这些独立子系统也接入到主对话链路里。

## 1. 总览

### 1.1 设计原则

| 原则 | 说明 |
|---|---|
| **轻量** | skill 对外 = 一组 LangChain `BaseTool` + 一段 prompt 片段，不引入新的运行时 |
| **零侵入** | 现有 `app/core/langgraph/tools/` 不删除，沦为 skill 的"零件"；主 agent 只改 1 行绑定逻辑 |
| **自描述** | 每个 skill 自带 `when_to_use` / `when_not_to_use` / `examples`，自动渲染进 system prompt |
| **可观测** | skill 调用走 structlog + Langfuse，事件名固定为 `skill_<name>_*`，便于统一查询 |
| **可复用** | deep_research、A2A specialist 通过 *proxy skill* 暴露给主 agent，避免重复实现 |

### 1.2 关键路径变化

```
旧:  user ──▶ LangGraphAgent ──▶ bind_tools([duckduckgo, ask_human]) ──▶ LLM
新:  user ──▶ LangGraphAgent ──▶ bind_tools(SkillRegistry.collect_tools()) ──▶ LLM
                    │
                    └──▶ system prompt 注入 SkillRegistry.render_usage_guide()
```

---

## 2. 目录结构

```
app/core/langgraph/
├── tools/                       # 保留：原子工具（skill 的零件）
│   ├── __init__.py              # 仍然导出 tools/research_tools，向后兼容
│   ├── ask_human.py             # 已有
│   ├── duckduckgo_search.py     # 已有
│   ├── tavily_search.py         # 已有
│   ├── think_tool.py            # 已有
│   ├── fetch_url.py             # 新增：HTTP GET + markdown 转换
│   ├── read_codebase.py         # 新增：read-only 文件 / grep
│   ├── run_sql.py               # 新增：白名单只读 SQL
│   └── http_api_call.py         # 新增：白名单 host 的 HTTP 调用
│
├── skills/                      # 新增：能力封装层
│   ├── __init__.py              # SkillRegistry 单例 + 自动发现 + 入口
│   ├── base.py                  # Skill dataclass / 基类
│   ├── registry.py              # SkillRegistry 实现
│   ├── web_research/
│   │   ├── __init__.py          # 注册 skill
│   │   ├── skill.py             # WebResearchSkill 定义
│   │   └── prompt.md            # 该 skill 的 usage guide（被 render 拼到 system prompt）
│   ├── code_ops/
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── prompt.md
│   ├── data_query/
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── prompt.md
│   ├── deep_research_proxy/     # 包装现有 DeepResearchAgent
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── prompt.md
│   └── multi_agent_proxy/       # 包装现有 CoordinatorAgent
│       ├── __init__.py
│       ├── skill.py
│       └── prompt.md
│
├── deep_research/               # 不动
├── graph.py                     # 改 ~3 处（见 §6）
└── ...

app/core/prompts/
└── system.md                    # 增加 {tool_usage_guide} 占位符
```

---

## 3. 核心抽象

### 3.1 `Skill` 基类（[skills/base.py](app/core/langgraph/skills/base.py)）

```python
# 接口示意（不是实现）
@dataclass(frozen=True)
class Skill:
    name: str                          # 唯一标识，snake_case，例如 "web_research"
    summary: str                       # 一句话定位（≤80 字），用于 guide 标题
    when_to_use: str                   # 何时该用我（多行 markdown 列表）
    when_not_to_use: str               # 何时不要用我（避免误用）
    examples: list[str]                # few-shot 调用示例，2-4 条
    tools: list[BaseTool]              # 暴露给 LLM 的实际 tool（1~N 个）
    prompt_path: str | None = None     # 可选：从 .md 文件加载完整 guide

    def render_guide(self) -> str:
        """渲染成注入 system prompt 的 markdown 片段。"""
```

**约定**：
- 每个 `tools[i].name` 必须以 `<skill_name>__` 前缀开头，例如 `web_research__tavily_search`，便于 Langfuse / 日志按 skill 聚合
- `when_to_use` / `when_not_to_use` 直接拼到 tool 的 docstring 末尾（LLM 实际"看到的"就是这个）

### 3.2 `SkillRegistry`（[skills/registry.py](app/core/langgraph/skills/registry.py)）

```python
class SkillRegistry:
    _skills: ClassVar[dict[str, Skill]] = {}

    @classmethod
    def register(cls, skill: Skill) -> None: ...

    @classmethod
    def get(cls, name: str) -> Skill: ...

    @classmethod
    def collect_tools(cls) -> list[BaseTool]:
        """拍平所有 skill 的 tools，去重后返回（替代旧的 tools list）。"""

    @classmethod
    def render_usage_guide(cls) -> str:
        """生成完整的 markdown guide，注入到 system prompt 的 {tool_usage_guide} 处。"""

    @classmethod
    def discover(cls) -> None:
        """import app.core.langgraph.skills.* 触发各 skill 包的副作用注册。"""
```

**注册时机**：在 `app/main.py` 的 startup hook 里调一次 `SkillRegistry.discover()`，避免任何请求路径上的 import 副作用。

---

## 4. 四类 Skill 详细设计

### 4.1 `web_research` — 通用 web 信息获取

| 项 | 内容 |
|---|---|
| tools 暴露 | `web_research__tavily_search`、`web_research__fetch_url`、`web_research__think` |
| 复用 | [tavily_search.py](app/core/langgraph/tools/tavily_search.py)、[think_tool.py](app/core/langgraph/tools/think_tool.py)（已存在，从 `research_tools` 升格到主 agent） |
| 新增 | `fetch_url(url)` — 给定 URL，返回 markdown 化的正文（用 `tavily_search` 内部已有的 `_fetch_webpage_content` 抽出来即可） |
| when_to_use | 用户问"实时/外部/最新"信息；需要核实事实；需要多步搜索 → 反思 → 再搜索 |
| when_not_to_use | 用户问的是项目内部状态；可以直接答；问题已有 long_term_memory 答案 |
| 注意点 | tavily 已用 `RESEARCH_TAVILY_MAX_RESULTS` 限速；fetch_url 走 [config.py:164](app/core/config.py:164) 的 `RESEARCH_WEBPAGE_FETCH_TIMEOUT` |

### 4.2 `code_ops` — 代码 / 文件理解

| 项 | 内容 |
|---|---|
| 定位 | **read-only 代码理解**，不涉及写文件（写操作交给后续单独的 skill 或人类审核） |
| tools 暴露 | `code_ops__read_file`、`code_ops__list_dir`、`code_ops__grep`、`code_ops__detect_language` |
| 实现 | 基于 `pathlib` + `ripgrep` 子进程（推荐）或纯 Python 的 `re`；所有路径**必须**经过 `app/utils/sanitization.py` 校验 |
| 安全 | 通过 `settings.CODE_OPS_ALLOWED_ROOTS`（新增）限制可访问根目录；禁止 `..` / 符号链接逃逸 |
| when_to_use | 用户上传/指定一个文件或目录，需要分析、定位 bug、解释代码 |
| when_not_to_use | 用户只是要写一段新代码（不需要先读现有文件） |
| 备注 | 这是给"对话式 agent 服务用户的代码"用的，不是给 agent 改自己代码用的 |

### 4.3 `data_query` — DB / API 查询

| 项 | 内容 |
|---|---|
| tools 暴露 | `data_query__run_sql`、`data_query__http_api_call` |
| `run_sql` 约束 | 只允许 `SELECT`（用 `sqlglot` 解析 AST 校验）；走只读连接；查询超时 5s；返回行数上限 100 |
| `http_api_call` 约束 | 仅允许 GET；host 必须在 `settings.DATA_QUERY_ALLOWED_HOSTS` 白名单；超时 10s |
| 复用 | 复用 [services/database.py](app/services/database.py) 的 async session，但要新增"只读 user / 只读 schema" |
| when_to_use | 用户问业务数据（订单、用户行为…）；问内部 API 状态 |
| when_not_to_use | 写操作；跨表事务；问的是公开互联网信息（应走 web_research） |
| 风险 | SQL 注入 / 数据泄露 — **必须**先和你确认白名单和只读账号策略 |

### 4.4 `deep_research_proxy` — 包装现有 deep research

| 项 | 内容 |
|---|---|
| tools 暴露 | 单个 tool：`deep_research_proxy__run`，签名 `run(query: str) -> str` |
| 实现 | 内部调用现有 [DeepResearchAgent.run()](app/core/langgraph/deep_research/graph.py:221)（注意 thread_id 要从主 agent 的 thread_id 派生，例如 `f"deepresearch-sub-{parent_thread}"`） |
| when_to_use | 用户的问题需要"多源、多步、综合"研究（用户明显说"详细研究/对比/调研"） |
| when_not_to_use | 简单一次搜索能搞定（用 `web_research__tavily_search` 即可，更便宜） |
| 取舍 | 这个 tool 一次调用可能耗时数十秒并产出长报告；要在 docstring 里明确告知 LLM "这是重操作" |

### 4.5 `multi_agent_proxy` — 包装现有 A2A coordinator

| 项 | 内容 |
|---|---|
| tools 暴露 | 单个 tool：`multi_agent_proxy__delegate`，签名 `delegate(task: str) -> str` |
| 实现 | 内部调用 [CoordinatorAgent.run()](app/core/a2a/coordinator.py:39)（context_id 从主 agent 的 thread_id 派生） |
| when_to_use | 任务横跨多个领域（既要研究又要写代码又要总结）；coordinator 比单一 skill 更适合做路由 |
| when_not_to_use | 任务能被 1~2 个 skill 直接搞定（避免双层 LLM 路由的延迟和 token 浪费） |
| 注意 | A2A 已通过 [A2A_BASE_URL](app/core/config.py:171) 配置，proxy skill 不需要新增配置 |

---

## 5. System Prompt 改造

### 5.1 [system.md](app/core/prompts/system.md) 新版结构（草案）

```markdown
# Name: {agent_name}
# Role: A world class assistant with specialized skills

You help the user by either answering directly or invoking the right skill.

# Available skills
{tool_usage_guide}     ← SkillRegistry.render_usage_guide() 注入

# Decision principles
1. Prefer the cheapest path: direct answer > single tool > deep_research_proxy / multi_agent_proxy.
2. Always read `when_not_to_use` before invoking a skill.
3. If a tool fails twice with the same error, stop retrying and ask the user (`ask_human`) or fall back to a simpler skill.
4. Never invent tool outputs — only cite what tools actually returned.

# What you know about the user
{long_term_memory}

# Current date and time
{current_date_and_time}

{user_context}
```

### 5.2 `render_usage_guide()` 输出示例（节选）

```markdown
## web_research — 通用 web 信息获取
**When to use**: 用户问实时/外部信息、需要核实事实、需要"搜→想→再搜"循环。
**When NOT to use**: 用户问项目内部状态；问题已被 long_term_memory 覆盖。
**Tools**: `web_research__tavily_search(query)`, `web_research__fetch_url(url)`, `web_research__think(reflection)`
**Examples**:
- "今天美股收盘怎么样？" → tavily_search("US stock market close 2026-05-15")
- "这个 issue 详情" → fetch_url("https://github.com/.../issues/123")

## deep_research_proxy — 深度多步研究（重操作）
...
```

### 5.3 `prompts/__init__.py` 改动

[prompts/__init__.py:34-42](app/core/prompts/__init__.py:34) 的 `load_system_prompt` 增加一个 kwarg：
```python
def load_system_prompt(username=None, *, tool_usage_guide: str = "", **kwargs):
    return _SYSTEM_PROMPT_TEMPLATE.format(
        ...,
        tool_usage_guide=tool_usage_guide,
        **kwargs,
    )
```
调用方（[graph.py:150](app/core/langgraph/graph.py:150)）改成传入 `SkillRegistry.render_usage_guide()`。

---

## 6. 主 Agent 集成（[graph.py](app/core/langgraph/graph.py)）

只需 3 处小改动：

| 行号 | 现状 | 改动 |
|---|---|---|
| [graph.py:48](app/core/langgraph/graph.py:48) | `from app.core.langgraph.tools import tools` | 改为 `from app.core.langgraph.skills import SkillRegistry` |
| [graph.py:80-81](app/core/langgraph/graph.py:80) | `self.llm_service.bind_tools(tools)` `self.tools_by_name = {t.name: t for t in tools}` | 改为 `_tools = SkillRegistry.collect_tools()` 然后 bind + 索引 |
| [graph.py:150](app/core/langgraph/graph.py:150) | `SYSTEM_PROMPT = load_system_prompt(username=..., long_term_memory=...)` | 增加 `tool_usage_guide=SkillRegistry.render_usage_guide()` |

`_tool_call` 节点（[graph.py:187](app/core/langgraph/graph.py:187)）**完全不动** —— 它只关心 `tool_calls[i]["name"]` → `tools_by_name[name]`，对 skill 抽象无感知。

---

## 7. 可观测性 & 日志规范

按现有 [AGENTS.md](AGENTS.md) "10 commandments" 的规则：

| 关键点 | 规范 |
|---|---|
| 事件命名 | `skill_<skill_name>_invoked`、`skill_<skill_name>_completed`、`skill_<skill_name>_failed` |
| 字段 | 必带 `skill_name`、`tool_name`、`session_id`、`duration_ms`，敏感参数（如 SQL 文本）截断到 200 字符 |
| Langfuse | 在 `Skill` 基类里给每个 tool 自动包一层 `RunnableLambda` + `@traceable`（或依赖现有 LangChain callback 自动捕获），span 名 = `skill.<name>.<tool>` |
| 指标 | 新增 Prometheus counter `skill_invocations_total{skill, status}`、histogram `skill_duration_seconds{skill}`，复用 [metrics.py](app/core/metrics.py) 现有模式 |
| 重试 | 用 tenacity（[AGENTS.md 规则 5](AGENTS.md)），exponential backoff；失败两次不再重试，让 agent 自己决定下一步 |

---

## 8. 配置项新增（[config.py](app/core/config.py)）

```
SKILLS_ENABLED                 = "web_research,code_ops,deep_research_proxy,multi_agent_proxy"
                                 # 默认开启的 skill 白名单，逗号分隔，便于灰度
CODE_OPS_ALLOWED_ROOTS         = "/workspace/uploads"   # code_ops skill 可访问的根目录
DATA_QUERY_READONLY_DSN        = ""                     # 仅 SELECT 的只读 DSN
DATA_QUERY_ALLOWED_HOSTS       = ""                     # http_api_call 白名单
SKILL_TOOL_DEFAULT_TIMEOUT     = 30                     # tool 单次调用默认超时(s)
```

`SKILLS_ENABLED` 这个白名单很重要：你可以先只开 `web_research` 跑通链路，再逐个开。

---

## 9. 测试 & Eval

| 层级 | 内容 |
|---|---|
| 单元测试 | 每个 skill 一个 test 文件：mock 底层 tool，验证 `Skill.tools` 注册正确、`render_guide` 输出含关键字段 |
| 集成测试 | 用 in-memory checkpointer 跑 `LangGraphAgent`，断言典型 query → 命中预期 skill |
| LLM Eval | 在 [evals/metrics/prompts/](evals/) 新增 `skill_routing.md` 评估指标，给定 50 条 query × 期望 skill 的标注集，计算路由准确率，作为 `make eval` 的一部分 |
| 关键 case | (a) 简单事实问题不该触发 deep_research_proxy；(b) 多领域复合问题该走 multi_agent_proxy；(c) tool 失败后 agent 应优雅降级或问 ask_human |

---

## 10. 分阶段落地路线

| 阶段 | 范围 | 验收 |
|---|---|---|
| **P1（1-2 天）** | 写 `Skill` 基类 + `SkillRegistry` + 1 个 `web_research` skill；改 [graph.py](app/core/langgraph/graph.py) 的 3 处；扩 system.md | 旧用例不回归；新 query 能命中 tavily |
| **P2（1 天）** | 加 `deep_research_proxy` + `multi_agent_proxy`（纯包装，零新原子 tool） | 主 agent 能在对话里触发深度研究 / A2A 协作 |
| **P3（2-3 天）** | 加 `code_ops` skill（read_file / grep / list_dir）+ 安全沙箱 | 安全审计通过 + 单测覆盖路径校验 |
| **P4（视业务而定）** | 加 `data_query` skill（需先和你定 DSN 和白名单） | DBA 审过只读账号 + SQL 解析白名单覆盖 |
| **P5（1 天）** | 写 skill_routing eval + Grafana 板子展示 skill 使用分布 | eval 准确率 baseline 出来 |

---

## 11. 风险与取舍

| 风险 | 缓解 |
|---|---|
| **Token 膨胀**：注入的 usage_guide 随 skill 数线性增长 | 给 `Skill` 加 `tier: 'core' \| 'advanced'`，advanced 仅在用户明确触发关键词时才注入；或把 guide 拆成"概要 + 详细"两段 |
| **路由错误**：LLM 选错 skill | 1) `when_not_to_use` 写得越具体越好；2) 用 P5 的 eval 持续监测；3) 失败案例进 few-shot examples |
| **Proxy skill 嵌套调用**：主 agent → deep_research_proxy → 内部又有 LLM 调用 → token 爆炸 | proxy tool 的 docstring **明确**注明"重操作、慢"；在 LLM 路由 prompt 里要求"先评估是否值得" |
| **数据泄露**：data_query 是新攻击面 | 强制只读账号 + SQL AST 校验 + 白名单 host + Langfuse 全量 trace |
| **和 A2A 重叠**：`multi_agent_proxy` 和已有 [/agents 端点](app/api/v1/agents.py) 功能重复 | 不冲突 —— /agents 是给前端直连的，proxy skill 是给主对话循环用的，两者并存 |

---

## 12. 我没回答的几个问题（需要你后续定）

1. **`code_ops` 的"代码源"在哪里**？用户上传 zip 解压到本地？给定 git URL 现拉？还是已经挂载在容器里？
2. **`data_query` 的只读 DSN 是否已就绪**？用现有 [POSTGRES_*](app/core/config.py:198) 同库不同 user，还是另接业务 DB？
3. **是否需要"用户级 skill 开关"**？比如某些用户没权限用 `data_query`，需要在 [auth.py](app/api/v1/auth.py) 的 session 上挂权限位。
4. **deep_research_proxy 的并发控制**：目前 [DeepResearchAgent](app/core/langgraph/deep_research/graph.py) 是 module 级单例，主 agent 多用户并发触发时如果都走它，会互相排队吗？需要看 checkpointer 的并发模型再定。
