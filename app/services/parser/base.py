from dataclasses import dataclass
from typing import Optional


@dataclass
class ChunkResult:
    file_path: str
    start_line: int
    end_line: int
    code_text: str
    chunk_type: str = "function_or_class"
    name: Optional[str] = None
