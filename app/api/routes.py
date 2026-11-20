import re
import logging
from typing import List
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.repository import Repository
from app.models.code_chunk import CodeChunk
from app.schemas.repository import RepoCreate, RepoResponse
from app.schemas.ask import AskRequest, AskResponse
from app.services.indexer_service import process_repository_indexing
from app.services.search_service import answer_repo_question
from app.services.rate_limiter import rate_limit_repos, rate_limit_ask

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["Repositories"])


def _extract_repo_name(url: str) -> str:
    """Extract owner/repo name from URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    elif parts:
        return parts[-1]
    return "unknown/repository"


@router.post(
    "",
    response_model=RepoResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a new GitHub repository"
)
def create_repository(
    repo_in: RepoCreate,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Ingest a GitHub repository:
    1. Validates repository URL.
    2. Applies per-IP rate limiting (5 per hour).
    3. Initializes repository record with status 'pending'.
    4. Queues shallow clone, size checking, parsing, embedding, and pgvector storage.
    """
    # Enforce per-IP rate limit for repository ingestion
    rate_limit_repos(http_request)

    repo_name = _extract_repo_name(repo_in.url)

    # Check if this repository was already ingested
    existing_repo = db.query(Repository).filter(Repository.url == repo_in.url).first()
    if existing_repo:
        if existing_repo.status == "ready":
            # Repository is already ready
            count = db.query(func.count(CodeChunk.id)).filter(CodeChunk.repo_id == existing_repo.id).scalar()
            resp = RepoResponse.model_validate(existing_repo)
            resp.chunk_count = count
            return resp
        elif existing_repo.status == "indexing":
            resp = RepoResponse.model_validate(existing_repo)
            return resp
        else:
            # Re-index if failed or pending
            existing_repo.status = "pending"
            existing_repo.error_message = None
            db.commit()
            db.refresh(existing_repo)
            background_tasks.add_task(process_repository_indexing, existing_repo.id, db)
            return RepoResponse.model_validate(existing_repo)

    # Create new record
    new_repo = Repository(
        url=repo_in.url,
        name=repo_name,
        status="pending"
    )
    db.add(new_repo)
    db.commit()
    db.refresh(new_repo)

    # Queue background indexing task
    background_tasks.add_task(process_repository_indexing, new_repo.id, db)

    return RepoResponse.model_validate(new_repo)


@router.get(
    "",
    response_model=List[RepoResponse],
    summary="List all ingested repositories and their indexing statuses"
)
def list_repositories(db: Session = Depends(get_db)):
    """
    List all ingested repositories along with status (pending, indexing, ready, failed).
    """
    repos = db.query(Repository).order_by(Repository.created_at.desc()).all()
    results = []
    for r in repos:
        count = db.query(func.count(CodeChunk.id)).filter(CodeChunk.repo_id == r.id).scalar()
        item = RepoResponse.model_validate(r)
        item.chunk_count = count
        results.append(item)
    return results


@router.get(
    "/{repo_id}",
    response_model=RepoResponse,
    summary="Get repository details and indexing status"
)
def get_repository(repo_id: int, db: Session = Depends(get_db)):
    """Get single repository details by ID."""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repo_id} not found"
        )
    count = db.query(func.count(CodeChunk.id)).filter(CodeChunk.repo_id == repo.id).scalar()
    resp = RepoResponse.model_validate(repo)
    resp.chunk_count = count
    return resp


@router.post(
    "/{repo_id}/ask",
    response_model=AskResponse,
    summary="Ask a question about the repository codebase"
)
def ask_repository(
    repo_id: int,
    request_body: AskRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    """
    Codebase Q&A:
    1. Validates non-empty question.
    2. Applies per-IP rate limiting (30 per hour).
    3. Embeds the user's question with the Gemini embedding model.
    4. Retrieves top 5 most similar code chunks using pgvector cosine distance.
    5. Calls Gemini chat/generation model to synthesize an answer.
    6. Returns the answer and citations (file path, line range) as JSON.
    """
    if not request_body.question.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty"
        )

    # Enforce per-IP rate limit for repository queries
    rate_limit_ask(http_request)

    try:
        answer, citations = answer_repo_question(repo_id, request_body.question, db)
        return AskResponse(answer=answer, citations=citations)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except RuntimeError as e:
        err_text = str(e)
        if "is currently" in err_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=err_text
            )
        elif "failed indexing" in err_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_text
            )
        elif "Gemini API" in err_text or "Failed to generate" in err_text:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Upstream AI service error: {err_text}"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=err_text
            )
    except Exception as e:
        logger.exception(f"Unexpected error in /repos/{repo_id}/ask: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
