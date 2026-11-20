# DevDocs AI — Backend (Phase 1)

DevDocs AI is an intelligent codebase Q&A backend tool that allows developers to ingest GitHub repositories and ask contextual questions about the code. DevDocs AI parses source files, segments code into function and class chunks, embeds them using Google's Gemini Embedding model, stores them in PostgreSQL with `pgvector`, and performs semantic retrieval to generate precise answers with file and line citations.

---

## Tech Stack

- **Language:** Python 3.11
- **API Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Pydantic v2 + SQLAlchemy 2.0)
- **Database:** [PostgreSQL 16](https://www.postgresql.org/) with [pgvector](https://github.com/pgvector/pgvector) extension
- **LLM & Embeddings:** [Google Gemini API](https://aistudio.google.com/) (`gemini-embedding-001` with 768 dimensions & `gemini-3.5-flash` for synthesis)
- **Code Parsing & Chunking:** Python `ast` module (for Python files) and [Tree-Sitter](https://tree-sitter.github.io/tree-sitter/) (for JavaScript / TypeScript)
- **Orchestration:** Docker & Docker Compose
- **Testing:** Pytest & pytest-asyncio (with mocks for Gemini and isolated SQLite in-memory test DB)

---

## Architecture & Project Structure

```
DevDocs AI/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app factory, CORS, lifespan, global exception handling
│   ├── config.py                   # Pydantic BaseSettings loading from .env
│   ├── database.py                 # SQLAlchemy engine, session maker, pgvector extension init
│   ├── models/
│   │   ├── __init__.py
│   │   ├── repository.py           # Repository database model (status: pending, indexing, ready, failed)
│   │   └── code_chunk.py           # CodeChunk model with Vector(768) pgvector column
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── repository.py           # Pydantic models for RepoCreate, RepoResponse
│   │   ├── chunk.py                # Pydantic models for CodeChunkResponse
│   │   └── ask.py                  # Pydantic models for AskRequest, Citation, AskResponse
│   ├── services/
│   │   ├── __init__.py
│   │   ├── gemini_service.py       # Gemini API client (batch embeddings, exponential backoff, answer generation)
│   │   ├── repo_cloner.py          # Shallow git clone (--depth 1), directory traversal, binary & ignored file filtering
│   │   ├── indexer_service.py      # Background worker coordinating clone -> parse -> embed -> pgvector storage
│   │   ├── search_service.py       # pgvector cosine similarity search (<=>) + Gemini RAG answer synthesis
│   │   └── parser/
│   │       ├── __init__.py
│   │       ├── base.py             # ChunkResult dataclass
│   │       ├── python_parser.py    # Python AST function & class chunker
│   │       ├── js_parser.py        # JavaScript tree-sitter function & class chunker
│   │       └── parser_service.py   # File extension dispatcher
│   └── api/
│       ├── __init__.py
│       └── routes.py               # API route definitions for /repos and /repos/{id}/ask
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures: in-memory DB, TestClient, mock Gemini service
│   ├── test_ask.py                 # Unit and integration tests for POST /repos/{id}/ask
│   ├── test_parser.py              # Unit tests for Python AST & JS Tree-sitter chunking & binary file detection
│   └── test_repos.py               # Unit tests for POST /repos and GET /repos
├── Dockerfile                      # Production Docker container image definition (Python 3.11-slim)
├── docker-compose.yml              # Multi-container orchestration (FastAPI API + pgvector PostgreSQL)
├── requirements.txt                # Python dependencies
├── pytest.ini                      # Pytest runner configuration
├── .env.example                    # Environment variable template
└── README.md                       # Comprehensive documentation
```

---

## Features

1. **Repository Ingestion (`POST /repos`)**:
   - Performs a shallow clone (`git clone --depth 1`) in a temporary directory.
   - Automatically skips `.git/`, `node_modules/`, `__pycache__/`, `.venv/`, and build artifacts.
   - Ignores binary files via extension filtering and null-byte inspection (`\x00`).
   - Parses Python files (`.py`) by functions and classes using Python's native `ast` module.
   - Parses JavaScript / TypeScript files (`.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`) using Tree-Sitter grammar.
   - Stores each chunk with relative `file_path`, 1-indexed `start_line`, `end_line`, and `code_text`.
   - Tracks lifecycle status: `pending` → `indexing` → `ready` (or `failed`).

2. **Vector Embeddings & Storage**:
   - Embeds each code chunk into 768-dimensional vectors using the Gemini embedding API (`gemini-embedding-001`).
   - Batches embedding requests to optimize throughput and handle API limits.
   - Stores embeddings in PostgreSQL with the `pgvector` extension and indexing.

3. **Codebase Q&A (`POST /repos/{id}/ask`)**:
   - Embeds the user question using the same Gemini embedding model.
   - Performs cosine distance similarity search (`<=>`) in pgvector to retrieve the top 5 most relevant chunks.
   - Sends the retrieved chunks as context to the Gemini chat model (`gemini-3.5-flash`).
   - Returns a structured JSON response containing the synthesized answer and file citations (`file_path`, `start_line`, `end_line`).

4. **Repository Listing (`GET /repos`)**:
   - Lists all ingested repositories with their current status (`pending`, `indexing`, `ready`, `failed`), timestamps, and indexed chunk counts.

---

## Setup & Running with Docker Compose

### 1. Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/)

### 2. Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
```
Open `.env` and fill in your `GEMINI_API_KEY`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### 3. Start the Services
Run Docker Compose in the background:
```bash
docker compose up -d --build
```
This starts:
- **`devdocs_db`**: PostgreSQL 16 with pgvector on port `5432`
- **`devdocs_api`**: FastAPI backend server on port `8000`

### 4. Verify Health
```bash
curl http://localhost:8000/health
```
Response:
```json
{
  "status": "healthy",
  "env": "development",
  "embedding_model": "gemini-embedding-001",
  "generation_model": "gemini-3.5-flash"
}
```

Interactive Swagger documentation is available at:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 5. Open the UI

Open **[http://localhost:8000](http://localhost:8000)** in your browser. The redesigned DevDocs AI web interface features:

1. **Editorial Design:** Warm cream background, serif typography (`Newsreader` & `Instrument Serif`), clean sans accents, and in-memory light/dark mode.
2. **Interactive Hero:** Paste any GitHub repo URL or pick from popular presets (`vercel/next.js`, `facebook/react`, `microsoft/typescript`).
3. **4-Step Visual Stepper:** Real-time feedback covering *Downloading code* &rarr; *Reading files* &rarr; *Embedding chunks* &rarr; *Ready*, with chunk progress and clear error cards.
4. **Interactive Overview Card:** Auto-generated beginner-friendly repo breakdown with Markdown formatting, a collapsible *How to run* code snippet with one-click copy, and a decorative soft GitHub illustration.
5. **Contextual Chat Card:** Multi-turn Q&A with conversational user & assistant bubbles, typing indicator, and verified citation chips (e.g. `app.ts: 12-48`).
6. **Live Recent Repos:** 2-column grid populated live from `GET /repos` with chunk counts, relative time indicators, and status badges.
7. **Single Self-Contained File:** Served directly at `GET /` from [app/static/index.html](file:///D:/DevDocs%20AI/app/static/index.html) with zero build steps or external JavaScript frameworks. Swagger API docs remain accessible at `/docs`.

---

## Deploy on Render

DevDocs AI is configured for deployment on [Render](https://render.com) as a containerized **Docker Web Service** with PostgreSQL + `pgvector`.

### 1. Create PostgreSQL Database with pgvector
1. In the Render Dashboard, click **New +** &rarr; **PostgreSQL**.
2. Give your database a name (e.g. `devdocs-db`), choose a region, and click **Create Database**.
3. Once provisioned, copy the **Internal Database URL** (for lowest latency within Render) or **External Database URL**.
   > *Note:* Render database URLs starting with `postgres://` are automatically normalized to `postgresql://` by DevDocs AI at runtime.

### 2. Deploy Web Service
1. Click **New +** &rarr; **Web Service** &rarr; connect your GitHub repository.
2. Select **Docker** as the runtime. Render will automatically build and run the included `Dockerfile`.
3. In **Advanced Settings**, set **Health Check Path** to `/health`.
4. Add the required environment variables below and click **Deploy Web Service**.

### 3. Environment Variables Reference

All runtime configuration is read directly from environment variables:

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string. `postgres://` is automatically converted. |
| `GEMINI_API_KEY` | **Yes** | — | Gemini API key from [Google AI Studio](https://aistudio.google.com). |
| `PORT` | Auto | `8000` | Port for uvicorn to bind (Render sets this automatically). |
| `EMBEDDING_MODEL` | No | `gemini-embedding-001` | Model name for vector embeddings. |
| `GENERATION_MODEL` | No | `gemini-3.5-flash` | Model name for answer synthesis. |
| `EMBEDDING_DIMENSIONS` | No | `768` | Embedding vector dimensions (matches pgvector schema). |
| `APP_ENV` | No | `production` | Deployment environment (`production` or `development`). |
| `MAX_REPO_SIZE_MB` | No | `50` | Maximum allowed repository size in MB to protect disk & memory. |
| `RATE_LIMIT_REPOS_PER_HOUR` | No | `5` | Per-IP limit on `POST /repos` ingestions per hour. |
| `RATE_LIMIT_ASK_PER_HOUR` | No | `30` | Per-IP limit on `POST /repos/{id}/ask` questions per hour. |

### 4. Automatic Startup Migrations & Retries
- On startup, the service executes `CREATE EXTENSION IF NOT EXISTS vector;` and creates all required tables.
- If the database is still warming up during cold starts, the application automatically retries the connection for up to **30 seconds** before failing.
- Render pings `/health` to verify that the service is ready to receive traffic.

---

## Local Development (Without Docker)

### 1. Create Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate       # On Linux/macOS
# or on Windows:
.\.venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start a Local PostgreSQL + pgvector
If running Postgres via Docker separately:
```bash
docker run -d --name pgvector -p 5432:5432 -e POSTGRES_USER=devdocs -e POSTGRES_PASSWORD=devdocs_password -e POSTGRES_DB=devdocs pgvector/pgvector:pg16
```

### 4. Start the FastAPI Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Running Pytest Tests

The test suite runs with fully mocked Gemini API calls and uses an isolated SQLite in-memory database, so no live credentials or external databases are required to run tests.

Run all tests:
```bash
pytest -v
```

All 14 test cases verify:
- Python AST chunking (functions, classes, async functions, exact line ranges).
- JavaScript Tree-sitter chunking (function declarations, classes, exports, arrow functions).
- Binary file detection and ignored directory filtering.
- Repository ingestion flow (`POST /repos`) and status transitions.
- Question answering (`POST /repos/{id}/ask`), semantic retrieval, and citation mapping.
- Error handling for invalid URLs, indexing repositories, failed repositories, empty questions, and upstream API failures.

---

## API Reference & Examples

### 1. Ingest Repository
`POST /repos`

**Request:**
```bash
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/octocat/Hello-World"}'
```

**Response (HTTP 202 Accepted):**
```json
{
  "id": 1,
  "url": "https://github.com/octocat/Hello-World",
  "name": "octocat/Hello-World",
  "status": "pending",
  "error_message": null,
  "chunk_count": null,
  "created_at": "2026-11-18T05:20:00Z",
  "updated_at": "2026-11-18T05:20:00Z"
}
```

---

### 2. List Repositories
`GET /repos`

**Request:**
```bash
curl http://localhost:8000/repos
```

**Response (HTTP 200 OK):**
```json
[
  {
    "id": 1,
    "url": "https://github.com/octocat/Hello-World",
    "name": "octocat/Hello-World",
    "status": "ready",
    "error_message": null,
    "chunk_count": 8,
    "created_at": "2026-11-18T05:20:00Z",
    "updated_at": "2026-11-18T05:20:15Z"
  }
]
```

---

### 3. Ask a Question About a Repository
`POST /repos/{id}/ask`

**Request:**
```bash
curl -X POST http://localhost:8000/repos/1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the purpose of this repository and what functions are defined?"}'
```

**Response (HTTP 200 OK):**
```json
{
  "answer": "This repository provides example scripts and hello world implementations. The primary function `main` in `src/index.js` initializes the greeting sequence.",
  "citations": [
    {
      "file_path": "src/index.js",
      "start_line": 1,
      "end_line": 12
    },
    {
      "file_path": "utils/helper.py",
      "start_line": 5,
      "end_line": 18
    }
  ]
]
```

---

## Error Handling

| Scenario | HTTP Status | Response Details |
| :--- | :--- | :--- |
| **Invalid Repository URL** | `422 Unprocessable Content` | Validates regex pattern and ensures URL format matches standard Git/GitHub repositories. |
| **Repository Not Found** | `404 Not Found` | Raised when accessing `/repos/{id}` or `/repos/{id}/ask` with a non-existent ID. |
| **Repository Still Indexing** | `409 Conflict` | Returned when calling `/repos/{id}/ask` before indexing finishes (`pending` or `indexing`). |
| **Repository Ingestion Failed** | `400 Bad Request` | Returned when asking questions on a repository whose clone or parse step failed, detailing the root cause. |
| **Gemini API Failure / Rate Limit** | `502 Bad Gateway` | Caught and sanitized when Gemini API encounters network timeouts, quota limits, or transient 503 errors. |
| **Empty Question** | `422 Unprocessable Content` | Returned when `question` string is empty or contains only whitespace. |

---

## License
MIT License.
