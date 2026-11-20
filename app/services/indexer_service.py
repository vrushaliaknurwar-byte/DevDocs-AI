import tempfile
import logging
from typing import List
from sqlalchemy.orm import Session
from app.models.repository import Repository
from app.models.code_chunk import CodeChunk
from app.services.repo_cloner import clone_repository, scan_repository_files
from app.services.parser.parser_service import parse_code_file
from app.services.parser.base import ChunkResult
from app.services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


def process_repository_indexing(repo_id: int, db: Session) -> None:
    """
    Background worker task to clone, parse, embed, and store a repository.
    Handles lifecycle status transitions: pending -> indexing -> ready (or failed).
    """
    repo = db.query(Repository).filter(Repository.id == repo_id).first()
    if not repo:
        logger.error(f"Cannot index repository: repo with id {repo_id} not found.")
        return

    repo.status = "indexing"
    repo.error_message = None
    db.commit()
    db.refresh(repo)

    temp_dir = tempfile.TemporaryDirectory(prefix=f"devdocs_repo_{repo_id}_")

    try:
        # 1. Shallow clone repository
        clone_repository(repo.url, temp_dir.name)

        # 2. Scan and parse files
        all_chunks: List[ChunkResult] = []
        for rel_path, content in scan_repository_files(temp_dir.name):
            file_chunks = parse_code_file(content, rel_path)
            all_chunks.extend(file_chunks)

        logger.info(f"Repository {repo.url} extracted {len(all_chunks)} chunks.")

        if all_chunks:
            # 3. Generate embeddings
            code_texts = [c.code_text for c in all_chunks]
            embeddings = gemini_service.get_embeddings_batch(code_texts)

            # 4. Store chunks in database
            db_chunks = []
            for chunk_data, vector in zip(all_chunks, embeddings):
                chunk_obj = CodeChunk(
                    repo_id=repo.id,
                    file_path=chunk_data.file_path,
                    start_line=chunk_data.start_line,
                    end_line=chunk_data.end_line,
                    code_text=chunk_data.code_text,
                    embedding=vector
                )
                db_chunks.append(chunk_obj)

            db.bulk_save_objects(db_chunks)

        # 5. Mark as ready
        repo.status = "ready"
        repo.error_message = None
        db.commit()
        logger.info(f"Repository {repo.url} (id={repo.id}) successfully indexed.")

    except Exception as e:
        logger.exception(f"Error indexing repository {repo.url} (id={repo.id}): {e}")
        db.rollback()
        # Refresh and update status to failed
        repo = db.query(Repository).filter(Repository.id == repo_id).first()
        if repo:
            repo.status = "failed"
            repo.error_message = str(e)
            db.commit()
    finally:
        try:
            temp_dir.cleanup()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp dir {temp_dir.name}: {e}")
