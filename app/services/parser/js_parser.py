import logging
from typing import List, Optional
from app.services.parser.base import ChunkResult

logger = logging.getLogger(__name__)

# Initialize tree-sitter parser for JavaScript
_parser = None
_language = None


def _get_js_parser():
    global _parser, _language
    if _parser is None:
        try:
            import tree_sitter_javascript as tsjs
            from tree_sitter import Language, Parser
            _language = Language(tsjs.language())
            _parser = Parser(_language)
        except Exception as e:
            logger.warning(f"Could not initialize tree-sitter-javascript: {e}")
            return None
    return _parser


def parse_javascript_file(content: str, file_path: str) -> List[ChunkResult]:
    """
    Parse JavaScript and TypeScript files using tree-sitter.
    Chunks functions, classes, and variable-assigned arrow/regular functions.
    Falls back to windowed chunking if tree-sitter is unavailable or file has no functions/classes.
    """
    lines = content.splitlines()
    if not lines or not content.strip():
        return []

    chunks: List[ChunkResult] = []
    parser = _get_js_parser()

    if parser is not None:
        try:
            source_bytes = content.encode("utf-8", errors="replace")
            tree = parser.parse(source_bytes)

            def _extract_name(node) -> Optional[str]:
                for child in node.children:
                    if child.type == "identifier":
                        return child.text.decode("utf-8", errors="replace")
                return None

            def _traverse(node):
                # Handle export statement wrapping declarations
                if node.type in ("export_statement", "export_default_declaration"):
                    for child in node.children:
                        if child.type in ("function_declaration", "class_declaration", "function"):
                            s_line = child.start_point[0] + 1
                            e_line = child.end_point[0] + 1
                            name = _extract_name(child)
                            code_text = "\n".join(lines[s_line - 1 : e_line]).strip()
                            if code_text:
                                chunks.append(
                                    ChunkResult(
                                        file_path=file_path,
                                        start_line=s_line,
                                        end_line=e_line,
                                        code_text=code_text,
                                        chunk_type="class" if child.type == "class_declaration" else "function",
                                        name=name
                                    )
                                )
                            return
                        elif child.type in ("lexical_declaration", "variable_declaration"):
                            _traverse(child)
                            return

                if node.type in ("function_declaration", "class_declaration"):
                    s_line = node.start_point[0] + 1
                    e_line = node.end_point[0] + 1
                    name = _extract_name(node)
                    code_text = "\n".join(lines[s_line - 1 : e_line]).strip()
                    if code_text:
                        chunks.append(
                            ChunkResult(
                                file_path=file_path,
                                start_line=s_line,
                                end_line=e_line,
                                code_text=code_text,
                                chunk_type="class" if node.type == "class_declaration" else "function",
                                name=name
                            )
                        )
                elif node.type in ("lexical_declaration", "variable_declaration"):
                    for decl in node.children:
                        if decl.type == "variable_declarator":
                            name = _extract_name(decl)
                            for child in decl.children:
                                if child.type in ("arrow_function", "function_expression"):
                                    s_line = node.start_point[0] + 1
                                    e_line = node.end_point[0] + 1
                                    code_text = "\n".join(lines[s_line - 1 : e_line]).strip()
                                    if code_text:
                                        chunks.append(
                                            ChunkResult(
                                                file_path=file_path,
                                                start_line=s_line,
                                                end_line=e_line,
                                                code_text=code_text,
                                                chunk_type="function",
                                                name=name
                                            )
                                        )
                                    break
                else:
                    for child in node.children:
                        _traverse(child)

            _traverse(tree.root_node)

        except Exception as e:
            logger.warning(f"Tree-sitter error parsing {file_path}: {e}. Falling back to line-based chunking.")

    # Fallback to windowed chunking if no functions or classes were found
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
