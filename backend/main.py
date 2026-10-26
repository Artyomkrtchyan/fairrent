import psycopg
import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from pydantic import ValidationError

try:
    from .listing_routes import router
    from .market_routes import router as market_router
    from .review_routes import router as review_router
except ImportError:
    from listing_routes import router
    from market_routes import router as market_router
    from review_routes import router as review_router

app = FastAPI(title="FairRent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[value.strip() for value in os.environ.get(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if value.strip()],
    allow_methods=["GET", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)
app.include_router(router)
app.include_router(market_router)
app.include_router(review_router)


@app.middleware("http")
async def request_identity(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def api_error(request, status, code, message, details=None):
    return JSONResponse(status_code=status, headers={"X-Request-ID": request.state.request_id}, content={
        "code": code, "message": message,
        "request_id": request.state.request_id, "details": details or [],
    })


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return api_error(request, 422, "validation_error", "Invalid request", [
        {"field": ".".join(str(part) for part in error["loc"]) or "query",
         "message": error["msg"]} for error in exc.errors()
    ])


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    code = {401: "unauthenticated", 403: "forbidden", 404: "not_found",
            409: "conflict", 422: "validation_error"}.get(exc.status_code, "internal_error")
    response = api_error(request, exc.status_code, code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    return api_error(request, 503, "service_unavailable", "Database unavailable")


@app.exception_handler(ResponseValidationError)
@app.exception_handler(ValidationError)
async def invalid_response(request, exc):
    return api_error(request, 500, "internal_error", "Invalid listing response")


@app.exception_handler(Exception)
async def internal_error(request, exc):
    return api_error(request, 500, "internal_error", "Internal server error")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with psycopg.connect(connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except psycopg.Error:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable"},
        )

    return {"status": "ok", "database": "ok"}
