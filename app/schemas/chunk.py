from pydantic import BaseModel, ConfigDict


class CodeChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_id: int
    file_path: str
    start_line: int
    end_line: int
    code_text: str
