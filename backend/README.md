# Synora Backend

The backend for Synora, an AI-powered document assistant. Built with FastAPI, it handles document processing, vector embeddings, and LLM interactions.

## Features

- **FastAPI**: High-performance async API.
- **LangGraph**: Orchestrates complex analysis workflows (Topic Extraction, Mind Maps).
- **Google Gemini**: Powers the AI intelligence.
- **Pinecone**: Vector database for semantic search.
- **Redis**: Caching and progress tracking.
- **Prisma**: ORM for database management.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file with:
    ```env
    DATABASE_URL="postgresql://..."
    PINECONE_API_KEY="..."
    GEMINI_API_KEY="..."
    REDIS_URL="redis://localhost:6379"
    ```

3.  **Run Server**:
    ```bash
    uvicorn main:app --reload
    ```

## Docker

The repository-root Dockerfile supports hosting services that use the default
`./Dockerfile` path. From the repository root, build it with:

```bash
docker build -t synora-backend .
```

This builds the backend. The frontend is deployed separately.

From the repository root (`Synora-main`), build and run the backend container:

```bash
docker build -f backend/Dockerfile -t synora-backend ./backend
docker run -p 8000:8000 --env-file .env synora-backend
```

### Render backend settings

For an existing Render Docker service, open **Settings → Build & Deploy**:

| Setting | Value |
| --- | --- |
| Root Directory | Leave empty (repository root) |
| Dockerfile Path | `./backend/Dockerfile` |
| Docker Build Context Directory | `./backend` |

Alternatively, leave Root Directory empty and use `./Dockerfile` with build
context `.` to use the repository-root backend Dockerfile. The two combinations
are supported; keep each Dockerfile paired with its matching context.

Save the settings and choose **Manual Deploy → Deploy latest commit**. A service
created manually does not automatically take its settings from `render.yaml`;
use a Render Blueprint to manage the service through that file.

The Dockerfile inside `backend/` expects the backend folder as its build
context. The root Dockerfile expects the repository root as its build context.

## API Documentation

Once running, visit `http://localhost:8000/docs` for the interactive Swagger UI.
