import os
from typing import List
from app.services.parser.base import ChunkResult
from app.services.parser.python_parser import parse_python_file
from app.services.parser.js_parser import parse_javascript_file

PYTHON_EXTENSIONS = {".py"}
JS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


def parse_code_file(content: str, rel_file_path: str) -> List[ChunkResult]:
    """
    Parse a source code file into chunks based on its extension.
    Supported: Python and JavaScript/TypeScript.
    """
    _, ext = os.path.splitext(rel_file_path.lower())

    if ext in PYTHON_EXTENSIONS:
        return parse_python_file(content, rel_file_path)
    elif ext in JS_EXTENSIONS:
        return parse_javascript_file(content, rel_file_path)
    else:
        return []
