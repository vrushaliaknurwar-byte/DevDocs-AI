import ast
import logging
from typing import List
from app.services.parser.base import ChunkResult

logger = logging.getLogger(__name__)


def parse_python_file(content: str, file_path: str) -> List[ChunkResult]:
    """
    Parse Python source code using the standard ast module.
    Chunks code by top-level and inner functions, async functions, and classes.
    Falls back to windowed chunking if no functions/classes exist or upon syntax errors.
    """
    lines = content.splitlines()
    if not lines or not content.strip():
        return []

    chunks: List[ChunkResult] = []

    try:
        tree = ast.parse(content)
        
        # Traverse AST nodes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                s_line = node.lineno
                # Python 3.8+ includes end_lineno
                e_line = getattr(node, "end_lineno", s_line)
                
                chunk_slice = lines[s_line - 1 : e_line]
                code_text = "\n".join(chunk_slice).strip()
                if code_text:
                    node_type = "class" if isinstance(node, ast.ClassDef) else "function"
                    chunks.append(
                        ChunkResult(
                            file_path=file_path,
                            start_line=s_line,
                            end_line=e_line,
                            code_text=code_text,
                            chunk_type=node_type,
                            name=node.name
                        )
                    )
    except SyntaxError as e:
        logger.warning(f"Syntax error parsing {file_path}: {e}. Falling back to line-based chunking.")
    except Exception as e:
        logger.warning(f"Error parsing Python AST for {file_path}: {e}. Falling back to line-based chunking.")

    # If no functions or classes were found (e.g., config file or script), chunk the file in windows
    if not chunks and content.strip():
        window_size = 60
        total_lines = len(lines)
        for i in range(0, total_lines, window_size):
            chunk_slice = lines[i : min(i + window_size, total_lines)]
            chunk_text = "\n".join(chunk_slice).strip()
            if chunk_text:
                chunks.append(
                    ChunkResult(
                        file_path=file_path,
                        start_line=i + 1,
                        end_line=min(i + window_size, total_lines),
                        code_text=chunk_text,
                        chunk_type="block",
                        name=None
                    )
                )

    return chunks
