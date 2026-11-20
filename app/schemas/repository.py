import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class RepoCreate(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean_url = v.strip()
        if not clean_url:
            raise ValueError("Repository URL cannot be empty")
        
        # Match standard HTTP/HTTPS GitHub or Git repository URLs
        # e.g., https://github.com/owner/repo or http://github.com/owner/repo.git
        git_pattern = r"^https?:\/\/(?:www\.)?[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+(?:\.git)?\/?$"
        if not re.match(git_pattern, clean_url):
            raise ValueError(
                "Invalid repository URL. Expected a valid GitHub or Git repository URL (e.g. 'https://github.com/owner/repo')"
            )
        return clean_url


class RepoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    name: str
    status: str
    error_message: Optional[str] = None
    chunk_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime
