import time

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

REQUESTS = Counter("docagent_http_requests_total", "HTTP requests", ["route", "method", "status"])
LATENCY = Histogram("docagent_http_request_seconds", "HTTP request latency", ["route"])
RUN_LATENCY = Histogram("docagent_run_seconds", "RAG/agent run latency", ["mode"])
AGENT_STEPS = Histogram("docagent_agent_steps", "Agent steps per run", buckets=(1, 2, 3, 4, 6, 8, 12))
FALLBACKS = Counter("docagent_agent_fallbacks_total", "Agent runs that fell back to plain RAG")
RUN_ERRORS = Counter("docagent_run_errors_total", "Failed runs", ["mode"])


async def metrics_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    name = getattr(route, "path", request.url.path)
    LATENCY.labels(name).observe(time.perf_counter() - t0)
    REQUESTS.labels(name, request.method, str(response.status_code)).inc()
    return response


def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
