import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.gemini_service import gemini_service
from app.services.rate_limiter import limiter
from app.models.repository import Repository
from app.models.code_chunk import CodeChunk

# Setup in-memory SQLite database for fast and isolated test execution
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Ensure app.database engine uses test_engine during tests so startup lifespan initializes test DB
import app.database as app_db
app_db.engine = test_engine
app_db.SessionLocal = TestingSessionLocal


@pytest.fixture(scope="function", autouse=True)
def reset_rate_limit():
    """Reset rate limiter state before and after each test."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="function")
def db_session():
    """Provides a clean in-memory database session for each test function."""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_gemini(monkeypatch):
    """
    Mock GeminiService methods across tests by default so no real network API calls are made.
    """
    mock_vector = [0.05] * 768

    def mock_get_embedding(text: str):
        return mock_vector

    def mock_get_embeddings_batch(texts, batch_size=25):
        return [mock_vector for _ in texts]

    def mock_generate_answer(question: str, context_chunks):
        return f"Mocked Gemini answer for question: '{question}' using {len(context_chunks)} chunks."

    monkeypatch.setattr(gemini_service, "get_embedding", mock_get_embedding)
    monkeypatch.setattr(gemini_service, "get_embeddings_batch", mock_get_embeddings_batch)
    monkeypatch.setattr(gemini_service, "generate_answer", mock_generate_answer)

    return {
        "get_embedding": mock_get_embedding,
        "get_embeddings_batch": mock_get_embeddings_batch,
        "generate_answer": mock_generate_answer,
        "mock_vector": mock_vector
    }
