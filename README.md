# YiTianLearningCosmos

一个基于 **FastAPI + LangGraph + A2A 协议** 构建的完整多智能体 AI 后端项目。系统由 5 个智能体组成 —— 1 个协调器（coordinator）负责将请求路由到 4 个专业智能体（research / search / writer / coder），并已经把生产环境需要的各项能力打通：有状态会话、长期记忆、可观测性、限流、鉴权、评测。

**面向 AI 工程师** —— 这是一个可以直接用于实际业务的完整工程，而不是停留在 demo 阶段的玩具。

## 核心特性

- **五智能体系统** —— 协调器通过 **A2A 协议** 将每个请求路由到一个或多个专业智能体（research / search / writer / coder）；每个专业智能体都是独立运行的 LangGraph 子应用
- **深度研究智能体** —— 规划器 + 并发子研究员 + 带引用的综合输出，使用 PostgreSQL 持久化检查点
- **长期记忆**：基于 mem0 + pgvector —— 按用户进行语义检索，带缓存层
- **LLM 服务**：循环式模型 fallback、指数退避重试、整体超时预算控制
- **Langfuse** 全链路 LLM 调用追踪；Prometheus 指标 + Grafana 监控面板
- **JWT 鉴权** 与会话管理；通过 slowapi 实现限流
- **Alembic** 数据库迁移；可选的 Valkey/Redis 缓存层
- **结构化日志**：每条日志都带有 request/session/user 上下文
- **三层评测框架** —— 协调器路由准确率、各专业智能体的输出质量、Langfuse trace 事后评分

## 快速开始

```bash
git clone <repo-url> my-agent && cd my-agent
cp .env.example .env.development   # 填入你的密钥
make install
make docker-up                     # 启动 API + PostgreSQL
```

打开 [http://localhost:8000/docs](http://localhost:8000/docs) 查看交互式 API 文档。

> 不使用 Docker 的本地开发方式请参考 [docs/getting-started.md](docs/getting-started.md)。

## 多智能体系统工作原理

对外只有一个统一的入口 `POST /api/v1/chat`，所有请求都交给 **协调器智能体** 处理。协调器内部是一个三节点的 LangGraph：

```
用户请求
     │
     ▼
   route        ← 一次 LLM 调用：判断转发给哪些专业智能体，还是直接回答
     │
     ▼
  dispatch     ← 通过 A2A 并发调用 research / search / writer / coder
     │
     ▼
 synthesize    ← LLM 写引言 + 原样附上各专业智能体的输出
     │
     ▼
最终回答
```

4 个专业智能体作为 **A2A 子应用** 挂载在 `/a2a/<name>` 路径下。协调器以 A2A 客户端的身份调用它们 —— 任何一个专业智能体的代码都不会 import 另一个，因此每个智能体都可以独立测试、独立替换。

| 智能体 | 角色 | 工具 | 成本特征 |
|---|---|---|---|
| `coordinator` | 路由请求、综合最终答案 | 仅 LLM | 每个请求 2 次 LLM 调用 |
| `research` | 多源深度研究，含并行子智能体 | Tavily + Postgres 检查点 | 最贵 —— 单请求耗时分钟级 |
| `search` | 单轮联网查询 + 摘要 | Tavily | 一次搜索 + 一次 LLM 调用 |
| `writer` | 纯文本改写，不收集信息 | 仅 LLM | 一次 LLM 调用 |
| `coder` | 代码生成与解释 | 仅 LLM | 一次 LLM 调用 |

完整系统设计参见 [docs/architecture.md](docs/architecture.md)。

## 文档导航

| 文档 | 内容 |
|---|---|
| [Getting Started](docs/getting-started.md) | 环境依赖、本地启动、第一次 API 调用 |
| [Architecture](docs/architecture.md) | 系统设计、请求流转、组件图 |
| [Configuration](docs/configuration.md) | 所有环境变量及默认值 |
| [Authentication](docs/authentication.md) | JWT 流程、会话、接口参考 |
| [Database & Migrations](docs/database.md) | 表结构、Alembic 迁移、pgvector |
| [LLM Service](docs/llm-service.md) | 模型管理、重试、fallback、超时预算 |
| [Memory](docs/memory.md) | mem0 长期记忆、缓存层 |
| [Observability](docs/observability.md) | Langfuse、结构化日志、Prometheus、性能分析 |
| [Evaluation](docs/evaluation.md) | 路由 / 智能体质量 / trace 评测，自定义指标 |
| [Tests](docs/tests.md) | 测试目录结构与运行方式 |
| [Docker](docs/docker.md) | Docker、Compose、完整监控栈 |

## 项目结构

```
app/
  agents/                          # 5 个相互独立的 LangGraph 智能体
    base.py                        # 所有智能体共同遵循的 Agent 协议
    coordinator/                   # A2A 客户端 —— 路由 + 综合输出
      agent.py
      prompts/{router,synthesis}.md
    research/                      # 深度研究：规划器 + 子研究员 + 检查点
    search/                        # 单轮 Tavily 查询 + 摘要
    writer/                        # 纯文本改写
    coder/                         # 代码生成与解释
  api/v1/                          # 路由处理函数（auth.py、chat.py）
  core/
    a2a/                           # A2A 协议适配层（server / client / executor）
    cache.py                       # Valkey/Redis + 内存兜底
    config.py                      # Pydantic Settings 配置
    limiter.py                     # 限流（slowapi）
    logging.py                     # structlog 配置
    metrics.py                     # Prometheus 指标
    middleware.py                  # 日志上下文 + profiling 中间件
    observability.py               # Langfuse 客户端接线
  models/                          # SQLModel ORM 模型
  schemas/                         # Pydantic 请求/响应 + 多智能体 schema
  services/
    llm/                           # 带重试 + 循环 fallback 的 LLM 服务
    database.py
    memory.py                      # mem0 长期记忆
  tools/                           # 共享的 LangGraph 工具（当前：tavily_search）
alembic/                           # 数据库迁移
evals/                             # 三个评测 runner（routing / agent_quality / trace）
docs/                              # 上面表格中的全部文档
```

## 贡献

欢迎 PR。请先按 [docs/getting-started.md](docs/getting-started.md) 配置好开发环境，然后遵循 [AGENTS.md](AGENTS.md) 中的代码规范。

安全问题请私下反馈 —— 参见 [SECURITY.md](SECURITY.md)。

## 许可证

参见 [LICENSE](LICENSE)。

## 常见问题

### 通用

**这个项目是做什么的？**
一个完整的多智能体 AI 后端工程，基于 FastAPI + LangGraph + A2A 协议构建。开箱即用地提供了 5 个智能体的系统（coordinator + research / search / writer / coder），以及通常需要自己拼接的各项能力：长期记忆、可观测性、限流、JWT 鉴权、三层评测框架。

**它和基础的 LangGraph 用法有什么区别？**
LangGraph 官方 quickstart 一般止步于"一个智能体能跑起来"。本项目在此之上加入了：由协调器路由 + A2A 串联的多智能体架构、Alembic 数据库迁移、mem0 + pgvector 长期记忆、Langfuse 链路追踪、Prometheus + Grafana 监控、JWT 会话、slowapi 限流、带请求级上下文的结构化日志、带循环 fallback 的 LLM 服务、三层评测框架 —— 这些都是生产环境通常需要单独构建的能力。

**为什么用 A2A，而不是智能体之间直接函数调用？**
A2A 让每个专业智能体保持真正的解耦：没有任何专业智能体的代码会 import 另一个，跨智能体调用全部走 HTTP，每个智能体都可以被替换、或被拆分到独立进程而不需要改动协调器。同一套架构可以从"5 个智能体都跑在一个 Python 进程里"无缝过渡到"专业智能体作为独立服务部署"，无需修改代码。

### 安装与配置

**必须用 Docker 吗？**
推荐但非必须。`make docker-up` 会同时启动 API 和 PostgreSQL。如果只想本地起服务，参见 [docs/getting-started.md](docs/getting-started.md)。

**支持哪些 LLM 提供商？**
当前：通过 `app/services/llm/registry.py` 中的 `LLMRegistry` 支持 **OpenAI 兼容协议** 的提供商（OpenAI、DeepSeek，以及任何兼容 OpenAI Chat Completions API 的服务）。基于 LangChain `init_chat_model` 的多提供商支持（Anthropic、Google、OpenRouter）在规划中。通过 `.env.development` 中的 `DEFAULT_LLM_MODEL` 配置使用的模型。

**长期记忆怎么配置？**
长期记忆完全自托管：mem0 跑在进程内部，数据通过 pgvector 持久化到已有的 PostgreSQL —— 不需要单独的 mem0 云账号或 API key。只需要一个可用的 `OPENAI_API_KEY`（用于事实抽取 + embedding）和启用 pgvector 扩展。详见 [docs/memory.md](docs/memory.md)。

### 开发

**怎么添加自定义工具？**
在 `app/tools/` 里写一个带 `@tool` 装饰的 LangChain 函数，从 `app/tools/__init__.py` 导出。然后在需要使用它的智能体里 import（例如 `from app.tools import my_tool`），把它接入该智能体的图节点。每个智能体管理自己的工具绑定 —— 没有全局共享注册表 —— 所以给某个专业智能体加工具不会影响其他智能体。

**怎么新增一个专业智能体？**
1. 创建 `app/agents/<name>/` 目录，包含 `agent.py`、`state.py`、`card.py` 以及 `prompts/` 子目录
2. 实现 `app/agents/base.py` 中的 `Agent` 协议（一个 `async run(task, context_id) -> str` 方法 + 一个 `create_graph()`）
3. 在 `app/agents/__init__.py` 的 `_load_registry()` 里注册，并把名字加进 `SPECIALIST_NAMES`，使它被挂载为 A2A 服务
4. 在 [`app/agents/coordinator/prompts/router.md`](app/agents/coordinator/prompts/router.md) 里描述协调器何时应该路由到它
5. 在 [`evals/agent_quality/runner.py`](evals/agent_quality/runner.py) 里加上对应的指标栈，并新建 `goldens/<name>.jsonl`，让评测框架覆盖它

**LLM 服务怎么处理失败？**
两层：(1) 单次调用的指数退避重试（`tenacity`）；(2) **循环 fallback** —— 当前模型重试耗尽后，服务自动切换到 `LLMRegistry` 中的下一个模型继续。整体超时预算限定了一次完整调用的延迟上限。详见 [docs/llm-service.md](docs/llm-service.md)。

**不用 Langfuse 行不行？**
可以。设置 `LANGFUSE_TRACING_ENABLED=false`（或者干脆不填 Langfuse 的 key）即可。智能体运行不受影响，结构化日志仍然记录 request/session/user 上下文。

**怎么跑评测？**
`make eval-routing` 检测协调器路由准确率（离线 golden 集，不产生 Tavily / research 费用）。`make eval-quality AGENT=writer`（也可以是 `search` / `coder` / `research`）针对单个专业智能体的输出按其指标栈评分。`make eval` 对近期的 Langfuse trace 做事后评分。`make eval-all` 串行执行以上全部。详见 [docs/evaluation.md](docs/evaluation.md)。

### 故障排查

**API 起不来**
- 确认 PostgreSQL 已经在跑（`make docker-up` 会把它和 API 一起拉起来）
- 确认 `.env.development` 存在 —— 从 `.env.example` 复制并填入必要的 key
- 跑迁移：`make migrate`

**记忆 / 语义搜索返回为空**
- 确认 PostgreSQL 启用了 `pgvector` 扩展
- 确认 `OPENAI_API_KEY` 有效（mem0 调用 OpenAI 做事实抽取 + embedding）
- 确认 `.env.development` 中已设置 `LONG_TERM_MEMORY_MODEL` 和 `LONG_TERM_MEMORY_EMBEDDER_MODEL`

**某个专业智能体超时，或回答里出现 "agent unavailable"**
- 每个 A2A 调用有独立的超时（`A2A_CLIENT_TIMEOUT`）。research 最容易超时，因为它会扇出成多个子研究员 + Tavily 搜索 —— 可以在 `.env.development` 调大这个超时值，或者收紧 research 的 `RESEARCH_MAX_CONCURRENT_SUBAGENTS` / `RESEARCH_MAX_SUBTASKS`
- 协调器的 `synthesize` 节点会在最终回答里明确标出哪些专业智能体失败 —— 失败不会让整体响应崩溃，只会让答案有所降级

**限流过于严格**
限流规则定义在 `app/core/limiter.py`（slowapi）。可以调整每个路由的装饰器或文件内的默认速率。相关环境变量参见 [docs/configuration.md](docs/configuration.md)。
