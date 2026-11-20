import os
import subprocess
import logging
from typing import Generator, Tuple
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
    "coverage",
    ".mypy_cache",
    ".ruff_cache"
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".bmp", ".tiff", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
    ".exe", ".bin", ".so", ".dll", ".dylib", ".o", ".a",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".webm",
    ".pyc", ".pyo", ".pyd",
    ".db", ".sqlite", ".sqlite3"
}

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"
}


def get_dir_size_bytes(directory: str) -> int:
    """Calculate the total size in bytes of all files in a directory."""
    total_size = 0
    for root, _, files in os.walk(directory):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
            except OSError:
                pass
    return total_size


def clone_repository(repo_url: str, target_dir: str) -> None:
    """
    Perform a shallow clone of a git repository (depth=1).
    Validates that the repository size is within MAX_REPO_SIZE_MB limit.
    Raises RuntimeError on failure with a sanitized descriptive error.
    """
    logger.info(f"Cloning repository {repo_url} into {target_dir} (shallow clone)")
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        repo_url,
        target_dir
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=settings.CLONE_TIMEOUT_SECONDS,
            check=False
        )
        if result.returncode != 0:
            err_msg = result.stderr.strip() or result.stdout.strip()
            # Clean sensitive info if any
            logger.error(f"Git clone failed for {repo_url}: {err_msg}")
            raise RuntimeError(f"Git clone failed: {err_msg}")
        logger.info(f"Successfully cloned {repo_url}")

        # Check repository size against MAX_REPO_SIZE_MB limit
        total_bytes = get_dir_size_bytes(target_dir)
        max_bytes = settings.MAX_REPO_SIZE_MB * 1024 * 1024
        if total_bytes > max_bytes:
            size_mb = total_bytes / (1024 * 1024)
            logger.error(
                f"Repository {repo_url} size ({size_mb:.1f} MB) exceeds limit ({settings.MAX_REPO_SIZE_MB} MB)"
            )
            raise RuntimeError(
                f"Repository size ({size_mb:.1f} MB) exceeds maximum allowed limit of {settings.MAX_REPO_SIZE_MB} MB"
            )

    except subprocess.TimeoutExpired:
        logger.error(f"Git clone timed out after {settings.CLONE_TIMEOUT_SECONDS}s for {repo_url}")
        raise RuntimeError(f"Repository clone timed out after {settings.CLONE_TIMEOUT_SECONDS} seconds")
    except FileNotFoundError:
        logger.error("Git executable not found in system PATH")
        raise RuntimeError("Git executable is not installed or not found in system PATH")


def is_binary_file(file_path: str) -> bool:
    """Check if a file is binary by extension or null byte presence."""
    _, ext = os.path.splitext(file_path.lower())
    if ext in BINARY_EXTENSIONS:
        return True

    if not os.path.isfile(file_path):
        return False

    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return False
    return False


def scan_repository_files(repo_dir: str) -> Generator[Tuple[str, str], None, None]:
    """
    Walk cloned repo directory and yield (relative_file_path, text_content).
    Skips .git, node_modules, binary files, files > MAX_FILE_SIZE_BYTES, and non-supported files.
    """
    for root, dirs, files in os.walk(repo_dir):
        # Prune ignored directories in-place so os.walk does not recurse into them
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]

        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, repo_dir).replace("\\", "/")

            _, ext = os.path.splitext(file.lower())
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                if os.path.getsize(full_path) > settings.MAX_FILE_SIZE_BYTES:
                    logger.debug(f"Skipping large file: {rel_path}")
                    continue
            except OSError:
                continue

            if is_binary_file(full_path):
                logger.debug(f"Skipping binary file: {rel_path}")
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                yield rel_path, content
            except Exception as e:
                logger.warning(f"Could not read file {rel_path}: {e}")
                continue
