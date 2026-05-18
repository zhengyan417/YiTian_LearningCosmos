"""Prometheus metrics configuration for the application.

This module sets up and configures Prometheus metrics for monitoring the application.
"""

from prometheus_client import Histogram
from starlette_prometheus import metrics

llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "Time spent processing LLM inference",
    ["model"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)


def setup_metrics(app):
    """Add the Prometheus /metrics endpoint to the application.

    Args:
        app: FastAPI application instance
    """
    app.add_route("/metrics", metrics)
