import pytest
from app.models.repository import Repository
from app.models.code_chunk import CodeChunk
from app.services.gemini_service import gemini_service


def test_ask_ready_repository_success(client, db_session):
    # 1. Seed a ready repository
    repo = Repository(
        url="https://github.com/fastapi/fastapi",
        name="fastapi/fastapi",
        status="ready"
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # 2. Seed code chunks with embeddings
    c1 = CodeChunk(
        repo_id=repo.id,
        file_path="fastapi/applications.py",
        start_line=50,
        end_line=120,
        code_text="class FastAPI(Starlette):\n    def __init__(self):\n        pass",
        embedding=[0.05] * 768
    )
    c2 = CodeChunk(
        repo_id=repo.id,
        file_path="fastapi/routing.py",
        start_line=200,
        end_line=250,
        code_text="def get(path: str):\n    return APIRoute(path)",
        embedding=[0.05] * 768
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    # 3. Ask question
    response = client.post(
        f"/repos/{repo.id}/ask",
        json={"question": "How does routing work in FastAPI?"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "routing work in FastAPI" in data["answer"]
    assert "citations" in data
    assert len(data["citations"]) == 2

    # Check citation structure
    cit = data["citations"][0]
    assert "file_path" in cit
    assert "start_line" in cit
    assert "end_line" in cit
    assert cit["file_path"] in ["fastapi/applications.py", "fastapi/routing.py"]


def test_ask_non_existent_repository(client):
    response = client.post(
        "/repos/9999/ask",
        json={"question": "Where is the main entrypoint?"}
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_ask_indexing_repository_returns_409(client, db_session):
    repo = Repository(
        url="https://github.com/owner/indexing-repo",
        name="owner/indexing-repo",
        status="indexing"
    )
    db_session.add(repo)
    db_session.commit()

    response = client.post(
        f"/repos/{repo.id}/ask",
        json={"question": "What is this repo?"}
    )
    assert response.status_code == 409
    assert "indexing" in response.json()["detail"]


def test_ask_failed_repository_returns_400(client, db_session):
    repo = Repository(
        url="https://github.com/owner/failed-repo",
        name="owner/failed-repo",
        status="failed",
        error_message="Git clone failed: Repository not found"
    )
    db_session.add(repo)
    db_session.commit()

    response = client.post(
        f"/repos/{repo.id}/ask",
        json={"question": "What is this repo?"}
    )
    assert response.status_code == 400
    assert "failed indexing" in response.json()["detail"]


def test_ask_empty_question_returns_422(client, db_session):
    repo = Repository(
        url="https://github.com/owner/ready-repo",
        name="owner/ready-repo",
        status="ready"
    )
    db_session.add(repo)
    db_session.commit()

    response = client.post(
        f"/repos/{repo.id}/ask",
        json={"question": "   "}
    )
    assert response.status_code == 422


def test_ask_gemini_api_failure_returns_502(client, db_session, monkeypatch):
    repo = Repository(
        url="https://github.com/owner/ready-repo-error",
        name="owner/ready-repo-error",
        status="ready"
    )
    db_session.add(repo)
    db_session.commit()

    c1 = CodeChunk(
        repo_id=repo.id,
        file_path="app.py",
        start_line=1,
        end_line=10,
        code_text="print('hi')",
        embedding=[0.1] * 768
    )
    db_session.add(c1)
    db_session.commit()

    # Simulate Gemini failure
    def failing_generate_answer(question, context):
        raise RuntimeError("Failed to generate answer from Gemini API: 503 UNAVAILABLE")

    monkeypatch.setattr(gemini_service, "generate_answer", failing_generate_answer)

    response = client.post(
        f"/repos/{repo.id}/ask",
        json={"question": "Why is this failing?"}
    )
    assert response.status_code == 502
    assert "Upstream AI service error" in response.json()["detail"]
