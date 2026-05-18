"""Multi-agent chat endpoint — the project's sole user-facing route.

A single ``POST /api/v1/chat`` hands the request to the coordinator agent,
which (via LangGraph) routes it to the appropriate specialists over A2A and
synthesizes the integrated answer.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from app.agents.coordinator.agent import coordinator_agent
from app.api.v1.auth import get_current_session
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.schemas.multi_agent import (
    MultiAgentRequest,
    MultiAgentResponse,
)

router = APIRouter()


@router.post("", response_model=MultiAgentResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    multi_agent_request: MultiAgentRequest,
    session: Session = Depends(get_current_session),
) -> MultiAgentResponse:
    """Route a request through the coordinator and return the synthesized answer.

    Args:
        request: The FastAPI request object (used for rate limiting).
        multi_agent_request: The user's request payload.
        session: The current session from the auth token.

    Returns:
        MultiAgentResponse: The synthesized answer plus per-specialist results.

    Raises:
        HTTPException: When the coordinator workflow fails.
    """
    context_id = f"chat-{session.id}-{uuid.uuid4().hex[:8]}"
    logger.info(
        "chat_request_received",
        session_id=session.id,
        context_id=context_id,
        query_chars=len(multi_agent_request.query),
    )

    try:
        result = await coordinator_agent.run_full(multi_agent_request.query, context_id)
        logger.info(
            "chat_request_completed",
            session_id=session.id,
            context_id=context_id,
            delegation_count=len(result.delegations),
        )
        return result
    except Exception as e:
        logger.exception(
            "chat_request_failed",
            session_id=session.id,
            context_id=context_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
