from app.models.repository import Repository
from app.models.code_chunk import CodeChunk


def test_post_repo_valid_url(client, db_session):
    response = client.post(
        "/repos",
        json={"url": "https://github.com/psf/requests"}
    )
    assert response.status_code == 202
    data = response.json()
    assert data["url"] == "https://github.com/psf/requests"
    assert data["name"] == "psf/requests"
    assert data["status"] == "pending"
    assert "id" in data


def test_post_repo_invalid_url(client):
    # Invalid URLs
    bad_urls = [
        "not_a_url",
        "ftp://github.com/repo",
        "https://just-a-domain.com",
        "http://",
        ""
    ]
    for url in bad_urls:
        response = client.post("/repos", json={"url": url})
        assert response.status_code == 422


def test_get_repos_list(client, db_session):
    # Create two repos with different statuses
    r1 = Repository(
        url="https://github.com/fastapi/fastapi",
        name="fastapi/fastapi",
        status="ready"
    )
    r2 = Repository(
        url="https://github.com/encode/uvicorn",
        name="encode/uvicorn",
        status="indexing"
    )
    db_session.add_all([r1, r2])
    db_session.commit()
    db_session.refresh(r1)

    # Add chunks to r1
    c1 = CodeChunk(
        repo_id=r1.id,
        file_path="main.py",
        start_line=1,
        end_line=5,
        code_text="def main(): pass",
        embedding=[0.1] * 768
    )
    db_session.add(c1)
    db_session.commit()

    response = client.get("/repos")
    assert response.status_code == 200
    repos = response.json()
    assert len(repos) == 2

    repo_map = {r["name"]: r for r in repos}
    assert repo_map["fastapi/fastapi"]["status"] == "ready"
    assert repo_map["fastapi/fastapi"]["chunk_count"] == 1
    assert repo_map["encode/uvicorn"]["status"] == "indexing"
    assert repo_map["encode/uvicorn"]["chunk_count"] == 0


def test_post_repos_rate_limiting(client):
    # 5 requests should succeed (status 202)
    for i in range(5):
        res = client.post(
            "/repos",
            json={"url": f"https://github.com/org/repo-{i}"}
        )
        assert res.status_code == 202

    # 6th request from the same client IP should trigger 429
    res6 = client.post(
        "/repos",
        json={"url": "https://github.com/org/repo-overflow"}
    )
    assert res6.status_code == 429
    assert "Rate limit exceeded" in res6.json()["detail"]
    assert "Retry-After" in res6.headers


def test_repo_size_limit_rejection(monkeypatch, tmp_path):
    import os
    from app.services.repo_cloner import clone_repository
    from app.config import get_settings

    settings = get_settings()
    # Mock subprocess.run to succeed
    class MockResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: MockResult())

    # Create a dummy large file exceeding MAX_REPO_SIZE_MB
    target_dir = str(tmp_path)
    large_file = os.path.join(target_dir, "large.bin")
    # Simulate directory size larger than limit
    monkeypatch.setattr("app.services.repo_cloner.get_dir_size_bytes", lambda d: (settings.MAX_REPO_SIZE_MB + 1) * 1024 * 1024)

    import pytest
    with pytest.raises(RuntimeError) as exc_info:
        clone_repository("https://github.com/org/huge-repo", target_dir)

    assert "exceeds maximum allowed limit" in str(exc_info.value)
