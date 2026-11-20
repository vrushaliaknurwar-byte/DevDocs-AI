import math
import logging
from typing import List, Tuple
from sqlalchemy.orm import Session
from app.models.repository import Repository
from app.models.code_chunk import CodeChunk
from app.schemas.ask import Citation
from app.services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Fallback cosine similarity computation for non-PostgreSQL databases (e.g. SQLite tests)."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def search_top_chunks(repo_id: int, query_vector: List[float], db: Session, limit: int = 5) -> List[CodeChunk]:
    """
    Search top N most relevant chunks using vector similarity.
    Uses pgvector native cosine distance (<=>) on PostgreSQL, with in-memory fallback for test databases.
    """
    engine = db.get_bind()
    if engine.dialect.name == "postgresql":
        return (
            db.query(CodeChunk)
            .filter(CodeChunk.repo_id == repo_id)
            .order_by(CodeChunk.embedding.cosine_distance(query_vector))
            .limit(limit)
            .all()
        )
    else:
        # Fallback for SQLite in local test suites
        repo_chunks = db.query(CodeChunk).filter(CodeChunk.repo_id == repo_id).all()
        scored_chunks = []
        for c in repo_chunks:
            if c.embedding is not None:
                # pgvector on sqlite returns list or string; ensure list of floats
                vec = list(c.embedding) if hasattr(c.embedding, "__iter__") else []
                score = _cosine_similarity(query_vector, vec)
                scored_chunks.append((score, c))
            else:
                scored_chunks.append((0.0, c))
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_chunks[:limit]]


def answer_repo_question(repo_id: int, question: str, db: Session) -> Tuple[str, List[Citation]]:
    """
    1. Verify repository state.
    2. Embed the question with Gemini.
    3. Retrieve the top 5 most similar code chunks from pgvector.
    4. Call Gemini to synthesize an answer.
    5. Return the answer string and citations list.
    """
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        raise ValueError(f"Repository with ID {repo_id} not found.")

    if repo.status in ("pending", "indexing"):
        raise RuntimeError(
            f"Repository '{repo.name}' is currently {repo.status}. Please wait until indexing completes."
        )
    elif repo.status == "failed":
        raise RuntimeError(
            f"Repository '{repo.name}' failed indexing: {repo.error_message or 'Unknown error'}"
        )

    # 1. Embed question
    query_vector = gemini_service.get_embedding(question)

    # 2. Retrieve top 5 chunks
    chunks = search_top_chunks(repo_id, query_vector, db, limit=5)

    if not chunks:
        return (
            "No indexed code chunks found for this repository to answer the question.",
            []
        )

    # 3. Format chunks for Gemini prompt
    chunk_dicts = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "code_text": c.code_text
        }
        for c in chunks
    ]

    # 4. Synthesize answer with Gemini
    answer = gemini_service.generate_answer(question, chunk_dicts)

    # 5. Extract citations
    citations = [
        Citation(
            file_path=c.file_path,
            start_line=c.start_line,
            end_line=c.end_line
        )
        for c in chunks
    ]

    return answer, citations
