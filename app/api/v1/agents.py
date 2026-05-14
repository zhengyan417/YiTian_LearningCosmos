"""Multi-agent coordinator API endpoint.

Exposes a single POST endpoint that hands the user's request to the Coordinator
agent, which routes it to the A2A specialist servers (research / search / writer
/ coder) and returns a synthesized answer.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from app.api.v1.auth import get_current_session
from app.core.a2a.coordinator import coordinator_agent
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.session import Session
from app.schemas.multi_agent import (
    MultiAgentRequest,
    MultiAgentResponse,
)

router = APIRouter()


@router.post("/chat", response_model=MultiAgentResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["agents"][0])
async def multi_agent_chat(
    request: Request,
    multi_agent_request: MultiAgentRequest,
    session: Session = Depends(get_current_session),
) -> MultiAgentResponse:
    """Route a request through the multi-agent coordinator and return the answer.

    Args:
        request: The FastAPI request object (used for rate limiting).
        multi_agent_request: The user's request payload.
        session: The current session from the auth token.

    Returns:
        MultiAgentResponse: The synthesized answer plus per-specialist results.

    Raises:
        HTTPException: When the coordinator workflow fails.
    """
    context_id = f"a2a-{session.id}-{uuid.uuid4().hex[:8]}"
    logger.info(
        "a2a_coordinator_request_received",
        session_id=session.id,
        context_id=context_id,
        query_chars=len(multi_agent_request.query),
    )

    try:
        result = await coordinator_agent.run(multi_agent_request.query, context_id)
        logger.info(
            "a2a_coordinator_request_completed",
            session_id=session.id,
            context_id=context_id,
            delegation_count=len(result.delegations),
        )
        return result
    except Exception as e:
        logger.exception(
            "a2a_coordinator_request_failed",
            session_id=session.id,
            context_id=context_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
