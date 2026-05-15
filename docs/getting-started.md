# 快速开始

## 前置条件

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- Docker + Docker Compose（推荐用于本地开发）
- LLM API 密钥（兼容 OpenAI、DeepSeek 等）
- Langfuse 账号（可选 — 设置 `LANGFUSE_TRACING_ENABLED=false` 可跳过）

## 方式 A：Docker（推荐）

最快启动方式。一条命令启动 API 和带 pgvector 的 PostgreSQL。

```bash
git clone <仓库地址> my-agent
cd my-agent

# 复制并填写环境文件
cp .env.example .env.development
# 必填：OPENAI_API_KEY, JWT_SECRET_KEY
# 可选：LANGFUSE_* 密钥（或设置 LANGFUSE_TRACING_ENABLED=false）
# 如果使用 DeepSeek：设置 LLM_BASE_URL=https://api.deepseek.com/v1

make install       # 安装 Python 依赖 + pre-commit hooks
make docker-up     # 启动 API（端口 8000）+ PostgreSQL
make migrate       # 运行 Alembic 迁移
```

打开 [http://localhost:8000/docs](http://localhost:8000/docs)。

## 方式 B：本地 Python

```bash
git clone <仓库地址> my-agent
cd my-agent

cp .env.example .env.development
# 填写：OPENAI_API_KEY, JWT_SECRET_KEY, POSTGRES_*（指向你的数据库）
# 如果使用 DeepSeek：设置 LLM_BASE_URL=https://api.deepseek.com/v1

make install       # 安装依赖 + pre-commit hooks
make migrate       # 通过 Alembic 创建表
make dev           # 启动热重载开发服务器，端口 8000
```

## 你的第一次 API 调用

### 1. 注册用户

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "Secret123!", "username": "you"}'  # pragma: allowlist secret
```

返回 `user_id` 和 JWT 令牌。

### 2. 创建会话

```bash
curl -X POST http://localhost:8000/api/v1/auth/session \
  -H "Authorization: Bearer <步骤1的令牌>"
```

返回 `session_id` 和会话作用域的 JWT。

### 3. 聊天

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/chat \
  -H "Authorization: Bearer <会话令牌>" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "你好！"}]}'
```

或使用流式端点获取实时响应：

```bash
curl -X POST http://localhost:8000/api/v1/chatbot/chat/stream \
  -H "Authorization: Bearer <会话令牌>" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "你好！"}]}'
```

### 4. 深度研究

```bash
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{"query": "量子计算的最新进展"}'
```

### 5. 多智能体协调

```bash
curl -X POST http://localhost:8000/api/v1/agents/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "帮我研究一下 Rust 在嵌入式系统中的应用，并写一份总结"}'
```

## 自定义智能体

你最可能需要修改的部分：

| 内容 | 位置 |
|---|---|
| 智能体人格与指令 | `app/core/prompts/system.md` |
| 可用工具 | `app/core/langgraph/tools/__init__.py`（主智能体工具列表） |
| LLM 模型与降级顺序 | `app/services/llm/registry.py` → `LLMRegistry.LLMS` |
| 记忆集合名称 | `.env` 中的 `LONG_TERM_MEMORY_COLLECTION_NAME` |
| 系统提示词模板 | `app/core/prompts/` 目录下的 `.md` 文件 |

## 运行 pre-commit hooks

Hooks 在 `git commit` 时自动运行。手动运行：

```bash
make pre-commit
```

包含的检查项：行尾空格、YAML/TOML/JSON 格式、密钥检测、ruff lint + format。

## 故障排除

**启动时报数据库连接错误**
确保 PostgreSQL 正在运行，且 `.env` 中的 `POSTGRES_*` 变量正确。使用 Docker 时：`make docker-up` 已自动处理。

**`detect-secrets` 阻止了提交**
如果是误报，在标记行末尾添加 `# pragma: allowlist secret`。

**Langfuse 报错**
在 `.env` 中设置 `LANGFUSE_TRACING_ENABLED=false`，开发期间完全禁用追踪。

**DeepSeek API 调用失败**
确认 `LLM_BASE_URL` 已设为 `https://api.deepseek.com/v1`，且 `OPENAI_API_KEY` 填写的是 DeepSeek 的 API 密钥。
