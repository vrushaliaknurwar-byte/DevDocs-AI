from typing import List
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question about the repository code")


class Citation(BaseModel):
    file_path: str = Field(..., description="Relative file path in repository")
    start_line: int = Field(..., description="1-indexed starting line number")
    end_line: int = Field(..., description="1-indexed ending line number")


class AskResponse(BaseModel):
    answer: str = Field(..., description="Synthesized answer from Gemini")
    citations: List[Citation] = Field(default_factory=list, description="Source code citations supporting the answer")
