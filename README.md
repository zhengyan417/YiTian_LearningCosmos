# YiTianLearningCosmos

A production-ready template for building **multi-agent AI backends** with FastAPI + LangGraph + the A2A protocol. Five agents — one coordinator that routes to four specialists (research / search / writer / coder) — wired together with the production concerns already solved: stateful conversations, long-term memory, observability, rate limiting, auth, evals.

**Built for AI engineers** who want a solid foundation, not a tutorial project.

## What's included

- **Five-agent system** — a coordinator routes each request to one or more specialists (research / search / writer / coder) over the **A2A protocol**; each specialist runs as an independent LangGraph sub-application
- **Deep research agent** — planner + concurrent sub-researchers + cited synthesis, with PostgreSQL-backed checkpointing
- **Long-term memory** via mem0 + pgvector — semantic search per user, cache-backed
- **LLM service** with circular model fallback, exponential backoff retries, and total timeout budget
- **Langfuse** tracing on all LLM calls; Prometheus metrics + Grafana dashboards
- **JWT auth** with session management; rate limiting via slowapi
- **Alembic** migrations; optional Valkey/Redis cache layer
- **Structured logging** with request/session/user context on every line
- **Three-tier eval framework** — coordinator routing accuracy, per-agent quality, Langfuse trace post-hoc scoring

## Quickstart

```bash
git clone <repo-url> my-agent && cd my-agent
cp .env.example .env.development   # fill in your keys
make install
make docker-up                     # starts API + PostgreSQL
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) to see the interactive API.

> For local development without Docker see [docs/getting-started.md](docs/getting-started.md).

## How the multi-agent system works

A single user-facing endpoint, `POST /api/v1/chat`, hands every request to the **coordinator agent**. The coordinator runs a three-node LangGraph:

```
user request
     │
     ▼
   route        ← one LLM call: classify into specialist delegations or direct answer
     │
     ▼
  dispatch     ← concurrent A2A calls to research / search / writer / coder
     │
     ▼
 synthesize    ← LLM-written intro + verbatim specialist outputs
     │
     ▼
final answer
```

The four specialists are mounted as **A2A sub-applications** under `/a2a/<name>`. The coordinator reaches them as an A2A client — no specialist module imports another, so each agent is independently testable and replaceable.

| Agent | Role | Tools | Cost profile |
|---|---|---|---|
| `coordinator` | Routes requests, synthesizes the answer | LLM only | 2 LLM calls per request |
| `research` | Deep multi-source research with parallel sub-agents | Tavily + Postgres checkpoint | Most expensive — minutes / request |
| `search` | Single-shot web lookup + summary | Tavily | One search + one LLM call |
| `writer` | Pure text transformation, no info gathering | LLM only | One LLM call |
| `coder` | Code generation + explanation | LLM only | One LLM call |

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Documentation

| Guide | What it covers |
|---|---|
| [Getting Started](docs/getting-started.md) | Prerequisites, local setup, first API call |
| [Architecture](docs/architecture.md) | System design, request flow, component diagrams |
| [Configuration](docs/configuration.md) | All environment variables with defaults |
| [Authentication](docs/authentication.md) | JWT flow, sessions, endpoint reference |
| [Database & Migrations](docs/database.md) | Schema, Alembic migrations, pgvector |
| [LLM Service](docs/llm-service.md) | Models, retries, fallback, timeout budget |
| [Memory](docs/memory.md) | mem0 long-term memory, cache layer |
| [Observability](docs/observability.md) | Langfuse, structured logging, Prometheus, profiling |
| [Evaluation](docs/evaluation.md) | Routing / agent_quality / trace evals, custom metrics |
| [Tests](docs/tests.md) | Test layout and how to run them |
| [Docker](docs/docker.md) | Docker, Compose, full monitoring stack |

## Project structure

```
app/
  agents/                          # Five independent LangGraph agents
    base.py                        # Agent protocol every concrete agent satisfies
    coordinator/                   # A2A client — routes + synthesizes
      agent.py
      prompts/{router,synthesis}.md
    research/                      # Deep research: planner + sub-researchers + checkpointing
    search/                        # Single-shot Tavily lookup + summary
    writer/                        # Pure text transformation
    coder/                         # Code generation + explanation
  api/v1/                          # Route handlers (auth.py, chat.py)
  core/
    a2a/                           # A2A protocol adapter (server / client / executor)
    cache.py                       # Valkey/Redis + in-memory fallback
    config.py                      # Pydantic Settings
    limiter.py                     # Rate limiting (slowapi)
    logging.py                     # structlog setup
    metrics.py                     # Prometheus metrics
    middleware.py                  # Logging context + profiling middleware
    observability.py               # Langfuse client wiring
  models/                          # SQLModel ORM models
  schemas/                         # Pydantic request/response + multi-agent schemas
  services/
    llm/                           # LLM service with retries + circular fallback
    database.py
    memory.py                      # mem0 long-term memory
  tools/                           # Shared LangGraph tools (currently: tavily_search)
alembic/                           # Database migrations
evals/                             # Three eval runners (routing / agent_quality / trace)
docs/                              # All guides linked above
```

## Contributing

PRs welcome. Please read [docs/getting-started.md](docs/getting-started.md) to get your environment set up, then follow the coding conventions in [AGENTS.md](AGENTS.md).

Report security issues privately — see [SECURITY.md](SECURITY.md).

## License

See [LICENSE](LICENSE).

## FAQ

### General

**What is this template?**
A production-ready foundation for **multi-agent AI backends** built on FastAPI + LangGraph + the A2A protocol. It ships a five-agent system (coordinator + research / search / writer / coder) plus the components you'd otherwise wire up by hand: long-term memory, observability, rate limiting, JWT auth, and a three-tier eval framework.

**How does this differ from a basic LangGraph setup?**
The base LangGraph quickstart stops at "one agent runs locally". This template adds a coordinator-routed multi-agent architecture connected by A2A, Alembic migrations, mem0 + pgvector long-term memory, Langfuse tracing, Prometheus + Grafana dashboards, JWT sessions, slowapi rate limiting, structured logging with per-request context, a circular-fallback LLM service, and a three-tier eval framework — production concerns you'd otherwise build separately.

**Why A2A and not just direct function calls between agents?**
A2A keeps each specialist truly decoupled: no specialist module imports another, every cross-agent call goes through HTTP, and each specialist can be replaced or moved to a separate process without touching the coordinator. The same architecture scales from "all five in one Python process" to "specialists as independent services" with zero code changes.

### Setup & Configuration

**Do I need Docker?**
Recommended but not required. `make docker-up` starts the API + PostgreSQL together. For local-only setup see [docs/getting-started.md](docs/getting-started.md).

**Which LLM providers are supported?**
Today: **OpenAI-compatible providers** via the `LLMRegistry` in `app/services/llm/registry.py` (OpenAI, DeepSeek, anything that speaks the OpenAI Chat Completions API). Multi-provider support (Anthropic, Google, OpenRouter) via LangChain's `init_chat_model` is planned. Configure your model via `DEFAULT_LLM_MODEL` in `.env.development`.

**How do I configure long-term memory?**
Long-term memory is self-hosted: mem0 runs in-process and persists into your existing PostgreSQL via pgvector — there is no separate mem0 cloud account or API key. You only need a working `OPENAI_API_KEY` (used for fact extraction + embeddings) and the pgvector extension enabled. See [docs/memory.md](docs/memory.md).

### Development

**How do I add a custom tool?**
Drop a LangChain `@tool`-decorated function in `app/tools/` and export it from `app/tools/__init__.py`. Then import it inside whichever agent should use it (e.g. `from app.tools import my_tool`) and wire it into that agent's graph node. Each agent owns its own tool bindings — no shared global registry — so adding a tool to one specialist never affects the others.

**How do I add a new specialist agent?**
1. Create `app/agents/<name>/` with `agent.py`, `state.py`, `card.py`, and a `prompts/` directory
2. Implement the `Agent` protocol from `app/agents/base.py` (an `async run(task, context_id) -> str` plus a `create_graph()`)
3. Register the agent in `_load_registry()` in `app/agents/__init__.py` and add its name to `SPECIALIST_NAMES` so it gets mounted as an A2A server
4. Update [`app/agents/coordinator/prompts/router.md`](app/agents/coordinator/prompts/router.md) to describe when the coordinator should delegate to it
5. Add a per-agent metric stack entry in [`evals/agent_quality/runner.py`](evals/agent_quality/runner.py) and a `goldens/<name>.jsonl` so the eval framework covers it

**How does the LLM service handle failures?**
Two layers: (1) per-call exponential-backoff retry via `tenacity`, (2) **circular fallback** — if the active model exhausts its retries, the service rotates to the next model in `LLMRegistry` and continues. A total timeout budget caps the whole call so latency stays bounded. See [docs/llm-service.md](docs/llm-service.md).

**Can I use this without Langfuse?**
Yes. Set `LANGFUSE_TRACING_ENABLED=false` (or omit the Langfuse keys). The agents run unchanged; structured logs still capture request/session/user context.

**How do I run the evals?**
`make eval-routing` checks coordinator routing accuracy (offline golden set, no Tavily/research cost). `make eval-quality AGENT=writer` (or `search` / `coder` / `research`) scores one specialist's outputs against its metric stack. `make eval` post-hoc scores recent Langfuse traces. `make eval-all` chains them. See [docs/evaluation.md](docs/evaluation.md).

### Troubleshooting

**The API won't start**
- Ensure PostgreSQL is running (`make docker-up` brings it up alongside the API)
- Confirm `.env.development` exists — copy from `.env.example` and fill in required keys
- Apply migrations: `make migrate`

**Memory / semantic search returns nothing**
- Verify the `pgvector` extension is enabled in your PostgreSQL instance
- Confirm `OPENAI_API_KEY` is valid (mem0 calls OpenAI for fact extraction + embeddings)
- Check `LONG_TERM_MEMORY_MODEL` and `LONG_TERM_MEMORY_EMBEDDER_MODEL` are set in `.env.development`

**A specialist times out or "agent unavailable" appears in the answer**
- Each A2A specialist call has its own timeout (`A2A_CLIENT_TIMEOUT`). Research is the most likely to time out because it fans out into sub-researchers and Tavily searches — bump the timeout in `.env.development`, or cap research's `RESEARCH_MAX_CONCURRENT_SUBAGENTS` / `RESEARCH_MAX_SUBTASKS`
- The coordinator's `synthesize` step still produces a structured answer that calls out which specialists failed — failures don't break the response, they just degrade it

**Rate limiting is too aggressive**
Limits are defined in `app/core/limiter.py` (slowapi). Adjust per-route decorators or the default rate in that file. See [docs/configuration.md](docs/configuration.md) for the related env vars.
