import time
import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Normalize database URL
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = "postgresql://" + db_url[len("postgres://"):]
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# Engine creation with connection pool settings
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to provide a transactional database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(max_wait_seconds: int = 30) -> None:
    """
    Initialize database schemas and extensions with retry logic.
    Retries connecting for up to max_wait_seconds before failing.
    """
    start_time = time.time()
    retry_delay = 2.0
    last_exception = None

    while time.time() - start_time < max_wait_seconds:
        try:
            with engine.connect() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                    conn.commit()
                    logger.info("Ensured PostgreSQL vector extension exists.")

            # Import models so Base has them registered
            import app.models  # noqa: F401
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified/created successfully.")
            return
        except Exception as e:
            last_exception = e
            elapsed = int(time.time() - start_time)
            logger.warning(
                f"Database connection attempt failed ({elapsed}s/{max_wait_seconds}s): {e}. Retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)

    logger.error(f"Failed to connect to and initialize database after {max_wait_seconds} seconds: {last_exception}")
    raise RuntimeError(f"Database initialization failed after {max_wait_seconds} seconds: {last_exception}")
