import logging
import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.api.routes import router as repos_router

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("devdocs")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables and pgvector extension are created with up to 30s retry
    logger.info("Initializing DevDocs AI database tables and extensions...")
    init_db(max_wait_seconds=30)
    yield
    # Shutdown
    logger.info("Shutting down DevDocs AI application.")


app = FastAPI(
    title="DevDocs AI API",
    description="Codebase Q&A tool backend powered by FastAPI, PostgreSQL + pgvector, and Gemini API",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for future frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(repos_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root():
    """Serve the DevDocs AI frontend."""
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "env": settings.APP_ENV,
        "embedding_model": settings.EMBEDDING_MODEL,
        "generation_model": settings.GENERATION_MODEL
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."}
    )
