# 配置

所有配置均从环境变量读取。使用 `.env.development`、`.env.staging` 或 `.env.production` — 应用根据 `APP_ENV` 变量加载对应的文件。

从复制 `.env.example` 开始：

```bash
cp .env.example .env.development
```

---

## 应用

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `development` | 环境：`development`、`staging`、`production`、`test` |
| `PROJECT_NAME` | `FastAPI LangGraph Template` | API 文档和日志中显示的项目名称 |
| `VERSION` | `1.0.0` | API 版本 |
| `DEBUG` | `false` | 启用调试日志和性能分析中间件 |
| `API_V1_STR` | `/api/v1` | API 路由前缀 |
| `ALLOWED_ORIGINS` | `*` | 逗号分隔的 CORS 允许来源 |

---

## LLM

| 变量 | 默认值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | — | 是 | API 密钥（兼容 OpenAI、DeepSeek 等） |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | 否 | LLM API 地址，使用 DeepSeek 时设为 `https://api.deepseek.com/v1` |
| `DEFAULT_LLM_MODEL` | `deepseek-v4-flash` | 否 | 起始模型 — 降级顺序见 [LLM 服务](llm-service.md) |
| `DEFAULT_LLM_TEMPERATURE` | `0.2` | 否 | 聊天补全的温度参数 |
| `MAX_TOKENS` | `16000` | 否 | 每次 LLM 响应的最大 token 数 |
| `MAX_LLM_CALL_RETRIES` | `3` | 否 | 切换降级模型前每个模型的重试次数 |
| `LLM_TOTAL_TIMEOUT` | `180` | 否 | 整个降级循环的最大秒数 |

---

## 长期记忆

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DASHSCOPE_API_KEY` | — | DashScope API 密钥（用于 mem0ai 的 text-embedding-v4 嵌入模型） |
| `LONG_TERM_MEMORY_COLLECTION_NAME` | `longterm_memory` | pgvector 集合名称 |
| `LONG_TERM_MEMORY_MODEL` | `deepseek-v4-flash` | mem0 用于提取和处理记忆的 LLM |
| `LONG_TERM_MEMORY_EMBEDDER_MODEL` | `text-embedding-v4` | 语义搜索的嵌入模型（DashScope） |

---

## 深度研究

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TAVILY_API_KEY` | — | Tavily 搜索 API 密钥（深度研究必填） |
| `RESEARCH_MAX_CONCURRENT_SUBAGENTS` | `3` | 并行子任务最大数量 |
| `RESEARCH_MAX_SUBTASKS` | `3` | 每次研究最大子任务数 |
| `RESEARCH_MAX_SEARCHES_PER_SUBAGENT` | `5` | 每个子智能体最大搜索次数 |
| `RESEARCH_TAVILY_MAX_RESULTS` | `3` | Tavily 单次搜索最大返回条数 |
| `RESEARCH_WEBPAGE_FETCH_TIMEOUT` | `10.0` | 抓取网页内容的超时秒数 |
| `RESEARCH_MAX_REFLECTION_ROUNDS` | `3` | 子研究员 search→reflect 循环最大轮数 |
| `RESEARCH_MAX_SUPERVISOR_ROUNDS` | `2` | 首轮派发后最多再补的研究轮数 |
| `RESEARCH_MAX_TOTAL_SUBAGENTS` | `6` | 单次研究累计子研究员运行数硬上限 |

---

## A2A 多智能体

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `A2A_ENABLED` | `true` | 是否启用 A2A 多智能体系统 |
| `A2A_BASE_URL` | `http://localhost:8000` | 本进程的外部可访问地址，协调者据此解析各专家的 AgentCard |
| `A2A_MOUNT_PREFIX` | `/a2a` | A2A 服务器挂载前缀 |
| `A2A_COORDINATOR_MAX_PARALLEL` | `2` | 协调者并行委派的最大数量 |
| `A2A_CLIENT_TIMEOUT` | `300.0` | A2A 客户端调用超时秒数 |

---

## 数据库

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POSTGRES_HOST` | `localhost` | PostgreSQL 主机 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 端口 |
| `POSTGRES_DB` | `mydb` | 数据库名 |
| `POSTGRES_USER` | `myuser` | 数据库用户 |
| `POSTGRES_PASSWORD` | `mypassword` | 数据库密码 |
| `POSTGRES_POOL_SIZE` | `5` | SQLAlchemy 连接池大小 |
| `POSTGRES_MAX_OVERFLOW` | `10` | 超出连接池大小的最大溢出连接数 |

---

## 认证

| 变量 | 默认值 | 必填 | 说明 |
| --- | --- | --- | --- |
| `JWT_SECRET_KEY` | — | 是 | JWT 签名密钥 — 生产环境请使用足够长的随机字符串 |
| `JWT_ALGORITHM` | `HS256` | 否 | JWT 签名算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_DAYS` | `30` | 否 | 令牌有效期（天） |

---

## 缓存（Valkey/Redis — 可选）

当设置了 `VALKEY_HOST` 时，应用使用 Valkey/Redis 进行记忆搜索缓存和限流。未设置时降级为内存 TTL 缓存（多实例不共享）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VALKEY_HOST` | ``（禁用） | Valkey/Redis 主机 — 留空则使用内存降级 |
| `VALKEY_PORT` | `6379` | 端口 |
| `VALKEY_DB` | `0` | 数据库编号 |
| `VALKEY_PASSWORD` | `` | 密码（如需要） |
| `VALKEY_MAX_CONNECTIONS` | `20` | 连接池大小 |
| `CACHE_TTL_SECONDS` | `60` | 记忆搜索结果缓存 TTL |

---

## 可观测性（Langfuse）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LANGFUSE_TRACING_ENABLED` | `true` | 设为 `false` 完全禁用调用链追踪 |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse 项目公钥 |
| `LANGFUSE_SECRET_KEY` | — | Langfuse 项目密钥 |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse 地址（自托管或云） |

---

## 限流

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RATE_LIMIT_DEFAULT` | `1000 per day, 200 per hour` | 兜底限制（开发环境） |
| `RATE_LIMIT_CHAT` | `100 per minute` | POST /api/v1/chat |
| `RATE_LIMIT_LOGIN` | `100 per minute` | POST /auth/login |
| `RATE_LIMIT_RESEARCH` | `5 per minute` | 深度研究（Coordinator 内部触发） |
| `RATE_LIMIT_HEALTH` | `60 per minute` | GET /health |

当配置了 Valkey 时，限流在所有应用实例间共享。未配置时限流为单进程级别。

> **注意**：开发/测试环境的限流默认值更宽松（`1000 per day, 200 per hour`），具体由 `config.py` 中的 `apply_environment_settings()` 控制。

---

## 性能分析（仅 DEBUG 模式）

仅在 `DEBUG=true` 时生效。对每个请求进行性能分析，当耗时超过阈值时保存 JSON 报告。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PROFILING_DIR` | `/tmp/fastapi_profiles` | 性能分析 JSON 文件目录 |
| `PROFILING_THRESHOLD_SECONDS` | `2.0` | 触发保存的最低耗时（秒）。设为 `0` 则每个请求都保存。 |

---

## 评估

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `EVALUATION_LLM` | `deepseek-v4-pro` | 评估所用的 LLM 模型 |
| `EVALUATION_BASE_URL` | `https://api.deepseek.com/v1` | 评估 LLM 的 API 地址 |
| `EVALUATION_API_KEY` | 同 `OPENAI_API_KEY` | 评估 LLM 的 API 密钥 |
| `EVALUATION_SLEEP_TIME` | `10` | 评估间等待秒数（避免触发限流） |

---

## 日志

| 变量 | 开发环境默认值 | 生产环境默认值 | 说明 |
| --- | --- | --- | --- |
| `LOG_LEVEL` | `DEBUG` | `WARNING` | 日志级别 |
| `LOG_FORMAT` | `console` | `json` | `console` 为彩色终端输出，`json` 为结构化生产日志 |
| `LOG_DIR` | `logs` | `logs` | JSONL 日志文件目录 |
