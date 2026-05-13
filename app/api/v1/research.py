"""Deep research API endpoint.

Exposes a single POST endpoint that takes a research question, runs the
multi-agent research workflow end-to-end, and returns the final markdown
report. Each request is given its own ``thread_id`` so that LangGraph
checkpointing does not pollute regular chat sessions.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.core.langgraph.deep_research import DeepResearchAgent
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User
from app.schemas.research import (
    ResearchRequest,
    ResearchResponse,
)

router = APIRouter()
agent = DeepResearchAgent()


@router.post("/research", response_model=ResearchResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["research"][0])
async def deep_research(
    request: Request,
    research_request: ResearchRequest,
    user: User = Depends(get_current_user),
):
    """Run a deep research workflow and return the synthesized report.

    Args:
        request: The FastAPI request object (used for rate limiting).
        research_request: The research query payload.
        user: The authenticated user.

    Returns:
        ResearchResponse: The thread id and final markdown report.

    Raises:
        HTTPException: When the workflow fails.
    """
    thread_id = f"research-{uuid.uuid4()}"
    logger.info(
        "research_request_received",
        user_id=user.id,
        thread_id=thread_id,
        query_chars=len(research_request.query),
    )

    try:
        report = await agent.run(
            query=research_request.query,
            thread_id=thread_id,
            user_id=str(user.id),
        )
        logger.info("research_request_completed", user_id=user.id, thread_id=thread_id)
        return ResearchResponse(thread_id=thread_id, report=report)
    except Exception as e:
        logger.exception(
            "research_request_failed",
            user_id=user.id,
            thread_id=thread_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
