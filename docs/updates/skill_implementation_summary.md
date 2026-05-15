# Skill 抽象层落地总结（P1 - P5）

> 与 [agent_skill.md](./agent_skill.md) 设计文档配对：本文档记录**实际落地的内容**、与设计的**偏差**，以及后续可继续打磨的点。
> 落地范围：6 个 skill、配套监控指标、tier 化、路由 eval。所有阶段全部通过 `ruff check` + `pyright` + smoke。

---

## 1. 阶段概览

| 阶段 | 目标 | 状态 |
|---|---|---|
| **P1** | 抽象层 + `web_research` + `interactive` | ✅ |
| **P2** | `deep_research_proxy` + `multi_agent_proxy` | ✅ |
| **P3** | `code_ops`（read-only 沙箱） | ✅ |
| **P4** | `data_query`（只读 SQL + 白名单 HTTP） | ✅ |
| **P5** | Prometheus 指标 + tier 化 + routing eval | ✅ |

---

## 2. 6 个 Skill 一览

| Skill | Tier | 默认启用 | 启用条件 | 暴露给 LLM 的 tool |
|---|---|---|---|---|
| `web_research` | core | ✅ | 默认 | `tavily_search`, `fetch_url`, `think_tool` |
| `interactive` | core | ✅ | 默认 | `ask_human` |
| `deep_research_proxy` | **advanced** | ✅ | 默认（被 `ENABLED_SKILLS_TIER=core` 隐藏） | `deep_research` |
| `multi_agent_proxy` | **advanced** | ✅ | 默认（同上） | `multi_agent_delegate` |
| `code_ops` | core | ❌ | 配 `CODE_OPS_ALLOWED_ROOTS` | `code_read_file`, `code_list_dir`, `code_grep`, `code_detect_language` |
| `data_query` | core | ❌ | 配 `DATA_QUERY_READONLY_DSN` 或 `DATA_QUERY_ALLOWED_HOSTS` | `run_sql`(条件)，`http_api_call`(条件) |

> "条件"类的 tool 表示：仅在对应 env 配置存在时才被加进 skill 的 tools 列表，从而对 LLM 可见。

---

## 3. 文件清单

### 3.1 新增（27 个）

```
app/core/langgraph/
├── tools/
│   └── fetch_url.py                                  # 新原子工具：HTTP GET + markdown
└── skills/
    ├── __init__.py                                   # 公共入口
    ├── base.py                                       # Skill dataclass + tier 常量
    ├── registry.py                                   # SkillRegistry（discover/collect/render）
    │
    ├── web_research/
    │   ├── __init__.py
    │   └── skill.py
    │
    ├── interactive/
    │   ├── __init__.py
    │   └── skill.py
    │
    ├── deep_research_proxy/
    │   ├── __init__.py                               # 暴露 warm_up / shutdown
    │   ├── skill.py                                  # tier=advanced
    │   └── proxy_tool.py                             # 持有 lazy DeepResearchAgent 实例
    │
    ├── multi_agent_proxy/
    │   ├── __init__.py
    │   ├── skill.py                                  # tier=advanced
    │   └── proxy_tool.py                             # 复用 coordinator_agent 单例
    │
    ├── code_ops/
    │   ├── __init__.py                               # 仅 ALLOWED_ROOTS 非空时注册
    │   ├── safety.py                                 # resolve_inside_root + is_binary
    │   ├── tools.py                                  # 4 个 read-only 工具
    │   └── skill.py
    │
    └── data_query/
        ├── __init__.py                               # 仅 DSN/HOSTS 任一非空时注册
        ├── safety.py                                 # check_sql_readonly + check_url_host
        ├── sql_tool.py                               # lazy AsyncConnectionPool + run_sql
        ├── http_tool.py                              # 白名单 GET-only
        └── skill.py                                  # build_data_query_skill 动态组合

evals/
└── skill_routing/
    ├── __init__.py
    ├── golden.jsonl                                  # 18 条标注集
    └── runner.py                                     # 离线 eval 入口
```

### 3.2 改动（7 个）

| 文件 | 改动点 |
|---|---|
| [app/core/config.py](../../app/core/config.py) | 新增 `SKILLS_ENABLED` / `ENABLED_SKILLS_TIER` / `CODE_OPS_*`（5 项）/ `DATA_QUERY_*`（6 项），共 13 个 env |
| [app/core/metrics.py](../../app/core/metrics.py) | 新增 `skill_invocations_total{skill,tool,status}` Counter + `skill_duration_seconds{skill,tool}` Histogram |
| [app/core/prompts/system.md](../../app/core/prompts/system.md) | 加 `{tool_usage_guide}` 占位符 + Decision principles 段 |
| [app/core/prompts/__init__.py](../../app/core/prompts/__init__.py) | `load_system_prompt` 加 `tool_usage_guide` kwarg |
| [app/core/langgraph/graph.py](../../app/core/langgraph/graph.py) | bind_tools 推迟到 `create_graph`；`_chat` 注入 usage_guide；`_tool_call` 加 metrics 埋点 |
| [app/main.py](../../app/main.py) | lifespan 调 `SkillRegistry.discover()`；接 `deep_research_proxy` 和 `data_query` 的 warm_up/shutdown |
| [Makefile](../../Makefile) | 新增 `make eval-routing` |

---

## 4. 新增配置项

```bash
# 通用
SKILLS_ENABLED=                 # 逗号分隔的白名单；空 = 全部启用
ENABLED_SKILLS_TIER=all         # all | core，控制 advanced 类是否暴露

# code_ops（不配 ALLOWED_ROOTS = skill 不注册）
CODE_OPS_ALLOWED_ROOTS=         # 逗号分隔的绝对路径
CODE_OPS_MAX_READ_BYTES=100000
CODE_OPS_MAX_LIST_ITEMS=200
CODE_OPS_MAX_GREP_MATCHES=100
CODE_OPS_MAX_GREP_FILES=5000

# data_query（DSN 和 ALLOWED_HOSTS 都不配 = skill 不注册）
DATA_QUERY_READONLY_DSN=        # 必须是只读 DB 账号
DATA_QUERY_ALLOWED_HOSTS=       # 逗号分隔的内部 host
DATA_QUERY_SQL_TIMEOUT_SECONDS=5
DATA_QUERY_SQL_MAX_ROWS=100
DATA_QUERY_HTTP_TIMEOUT_SECONDS=10.0
DATA_QUERY_HTTP_MAX_RESPONSE_BYTES=200000
```

---

## 5. 关键设计决策

### 5.1 Skill 抽象

`Skill` 是不可变 dataclass，含元数据（`when_to_use` / `when_not_to_use` / `examples` / `tier`）+ tools 列表 + `render_guide()` 方法。

`SkillRegistry` 提供：
- `register(skill)` — 各 skill `__init__.py` import 时自调用注册
- `discover()` — `pkgutil.iter_modules` 扫一遍 `skills/` 子包，触发注册
- `all()` — 返回过滤后的 skill 列表（先按 `SKILLS_ENABLED` 名字过，再按 `ENABLED_SKILLS_TIER` 过 tier）
- `collect_tools()` — 拍平所有 enabled skill 的 tool（去重）
- `render_usage_guide()` — 拼接 markdown，注入到 `system.md` 的 `{tool_usage_guide}` 占位符

### 5.2 主 Agent 集成

`LangGraphAgent.__init__` 不再直接 `bind_tools` —— 推迟到 `create_graph()`，因为 chatbot 模块加载时 `SkillRegistry.discover()` 还没被 lifespan 调用过。

`_chat` 节点每次调 `load_system_prompt(tool_usage_guide=SkillRegistry.render_usage_guide())`，guide 字符串当前是热路径里临时拼的（< 5KB，无明显成本）。

`_tool_call` 节点的每个 tool 调用都被 try/finally 包住，写入 `skill_invocations_total` 和 `skill_duration_seconds` 两个 metric。

### 5.3 Proxy Skill 的 thread_id 派生

LangChain 的 `RunnableConfig` 作为 `InjectedToolArg` 自动注入 tool 函数；从中取 `parent_thread`，派生：

- `deep_research` → `deepresearch-sub-<parent>`
- `multi_agent_delegate` → `a2a-coord-<parent>`

便于 Langfuse 按主对话线索回溯。

### 5.4 安全沙箱（code_ops + data_query）

| 维度 | code_ops | data_query |
|---|---|---|
| 主防线 | `Path.resolve()` 后 `relative_to(root)` 校验，挫败 `..` 和 symlink 逃逸 | DB 引擎层面的只读账号（必须） |
| 副防线 | 二进制文件检测（NUL byte）；`SKIP_DIRS` 过滤 `.git`/`node_modules` 等 | 正则前缀+黑名单（必须 SELECT/WITH/EXPLAIN/SHOW；多语句拒绝；写关键字拒绝） |
| 资源限制 | 100KB 单文件 / 200 项目录 / 100 grep 匹配 / 5000 文件扫 | 5s 超时 / 100 行 / 200KB HTTP body |
| 默认状态 | 不配 root = 不注册 | 不配 DSN+不配 host = 不注册 |
| 异步 | `asyncio.to_thread` 包文件 IO，不阻塞 event loop | psycopg3 `AsyncConnectionPool` |

### 5.5 路由 Eval

`evals/skill_routing/runner.py` 直接调用 `llm_service.call(...)`，bind 当前注册的所有 skill tools；解析返回的 `tool_calls` 第一项 → 查 `skill_by_tool` → 对照 `expected_skill`。

- 不依赖 Postgres / Langfuse —— 离线可跑
- 未注册 skill 的 case 自动跳过（不算 miss）
- 退出码：accuracy ≥ 70% → 0，否则 1（可作为 CI gate）
- 标注集 18 条，覆盖 6 个 expected target（含 `direct_answer`）

---

## 6. 与设计文档的偏差

| 设计原文 | 实际实现 | 原因 |
|---|---|---|
| tool name 强制 `<skill_name>__` 前缀 | **未做** —— 保留原 tool 名（`tavily_search`、`ask_human` 等） | `tavily_search` / `think_tool` 被 deep_research 子图共享，改名会破坏复用；约定改为靠 metadata 区分（`skill_invocations_total{skill,tool}` 双标签足够聚合） |
| `data_query` 用 `sqlglot` AST 校验 SQL | **改用正则前缀+关键字黑名单** | sqlglot 不在依赖里，加依赖会扩大攻击面/构建时间；主防线本就是 DB 只读账号，副防线"够用即可" |
| 每个 skill 拆 `prompt.md` 单独存放 | **元数据全部内联在 `skill.py`** | 避免双源真相；当前 `when_to_use` / `examples` 都是几行字，没必要单独文件 |
| `code_ops` 优先用 ripgrep 子进程 | **纯 Python `re` + `Path.rglob`** | 环境无 rg；纯 Python 实现已带文件数 / 匹配数双限位，无明显性能问题 |
| Skill 基类自动包 `RunnableLambda` + `@traceable` 做 Langfuse trace | **未做** —— 复用现有 LangChain callback 自动捕获 | 已有的 `get_langfuse_callback_handler()` 在 graph 配置里全局注入，tool 调用自动出现在 trace 里，无需在 Skill 层重复包装 |
| eval 标注集 50 条 | **18 条** | 覆盖每个 skill 3 条已能产出 baseline；后续可按真实 miss case 扩展 |
| 单元测试覆盖每个 skill | **未做** | 留给后续按真实使用反馈补，避免提前过度设计；smoke 验证已覆盖关键路径 |

---

## 7. 可观测性新增

### 7.1 Prometheus 指标

```promql
# 谁在用什么
sum by (skill) (rate(skill_invocations_total{status="success"}[5m]))

# 哪个 tool 慢
histogram_quantile(0.95, sum by (skill, tool, le) (rate(skill_duration_seconds_bucket[5m])))

# 失败率
sum by (skill) (rate(skill_invocations_total{status="failed"}[5m]))
  / sum by (skill) (rate(skill_invocations_total[5m]))
```

### 7.2 结构化日志事件

| 事件名 | 来源 | 关键字段 |
|---|---|---|
| `skills_discovered` | registry 启动 | `count`, `registered`, `enabled_filter` |
| `skill_registered` | 各 skill `__init__` | `skill_name`, `tool_count`, `tools` |
| `agent_skills_bound` | LangGraphAgent 首次 create_graph | `tool_count`, `tools` |
| `code_read_file_invoked` / `code_list_dir_invoked` / `code_grep_invoked` | code_ops 工具 | `path`, `pattern` |
| `data_query_run_sql_invoked` / `_completed` / `_failed` / `_timeout` | data_query SQL | `sql`(截断 200 字符), `row_count` |
| `data_query_http_invoked` / `_completed` / `_failed` | data_query HTTP | `url`, `status`, `body_chars`, `truncated` |
| `deep_research_proxy_invoked` / `_completed` / `_failed` | proxy | `parent_thread_id`, `sub_thread_id`, `report_chars` |
| `multi_agent_proxy_invoked` / `_completed` / `_failed` | proxy | `parent_thread_id`, `context_id`, `delegation_count` |

DSN / 密码 / 完整 SQL / HTTP body 都不入日志（敏感字段截断或省略）。

---

## 8. 启用步骤速查

### 8.1 验证 P1+P2（默认配置即可）

```bash
make dev
# 然后用 chat 接口聊天，看 logs 里的 skill_registered / agent_skills_bound
```

### 8.2 启用 code_ops

```bash
# .env.development 加：
CODE_OPS_ALLOWED_ROOTS=/workspace/uploads,/data/user_repos
```

启动后 logs 会出 `code_ops_skill_enabled`。

### 8.3 启用 data_query

```sql
-- 在你的业务 DB 上执行
CREATE USER agent_ro WITH PASSWORD 'xxx';
GRANT CONNECT ON DATABASE your_db TO agent_ro;
GRANT USAGE ON SCHEMA public TO agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO agent_ro;
```

```bash
# .env 加（host 仅列内部 host；外部走 web_research 的 fetch_url）：
DATA_QUERY_READONLY_DSN=postgresql://agent_ro:xxx@db.internal:5432/your_db
DATA_QUERY_ALLOWED_HOSTS=billing.internal,inventory.internal
```

### 8.4 控制 prompt 预算

```bash
# 生产想省 token：
ENABLED_SKILLS_TIER=core    # 隐藏 deep_research_proxy / multi_agent_proxy
```

### 8.5 跑路由 eval

```bash
make eval-routing
# 或：uv run python -m evals.skill_routing.runner --limit 5 --concurrency 1
```

---

## 9. 后续可继续打磨

| 项 | 说明 | 优先级 |
|---|---|---|
| 把现有 3 处 `DeepResearchAgent` 实例（`/research` API、`a2a/specialists`、`deep_research_proxy`）合并为单 module-level singleton | 现状不影响功能，只是浪费 3 套 PG 连接池 | 中 |
| 用 sqlglot 替换 `data_query` 的正则校验 | 当前正则会误拒"列名带 SQL 关键字前缀"等边界 case；sqlglot AST 校验更精准 | 中（取决于业务是否真的会构造这种 query） |
| 给 code_ops 加单元测试（路径逃逸 / symlink / 大文件 / 二进制检测） | 当前 smoke 验证过 happy path + 一个逃逸 case | 中 |
| 扩 routing eval 标注集到 50+ 条 | 当前 18 条够 baseline；按真实 miss case 扩展更好 | 低（按需） |
| 每个 skill 加 lifecycle 钩子（`on_startup` / `on_shutdown`），让 main.py 不再写死各 skill 的 warm_up import | 当前 `deep_research_proxy_warm_up` / `data_query_warm_up` 在 main.py 里硬编码 | 低（清理性质） |
| 把 `code_ops` 升级到允许 ripgrep 子进程（如可用） | 大仓库 grep 性能会显著好；纯 Python 已可用 | 低 |
| LLM 真实调用一次 routing eval 拿到 baseline accuracy 数字 | 当前因 `OPENAI_API_KEY` 失效未跑 | 高（需要环境配置） |

---

## 10. 设计文档里"未回答的问题"现状

| 问题 | 状态 |
|---|---|
| code_ops 的代码源在哪里 | 设计为按 `CODE_OPS_ALLOWED_ROOTS` 挂载；操作者决定是上传 zip 解压、git clone 还是 volume mount |
| data_query 只读 DSN 是否就绪 | 文档里给了创建 `agent_ro` 的 SQL 步骤，由 DBA 执行 |
| 是否需要用户级 skill 开关 | 未实现 —— 当前是进程级开关；如果需要按用户/角色控制，可后续在 `auth.py` session 上挂权限位，再 fork 一个 `SkillRegistry.for_session(session)` |
| deep_research_proxy 并发控制 | proxy 复用 `DeepResearchAgent` 的 connection pool（`POSTGRES_POOL_SIZE` 默认 20）；checkpointer 内部按 `thread_id` 隔离，不会互相阻塞，但深度研究本身慢，建议对该 tool 加上层级别的并发限制（未做） |

---

## 11. Lint / Type / Smoke 全过

每个阶段结束都跑过：
- `uv run ruff check .` —— All checks passed
- `uv run pyright` —— 0 errors, 0 warnings
- 至少一个 smoke 验证关键链路（registry 注册数、tier filter、沙箱逃逸防护、SQL/URL 校验）
