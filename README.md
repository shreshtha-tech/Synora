# Synora

Synora is an AI-powered study assistant that transforms PDF documents into interactive learning experiences. It generates dynamic mind maps, extracts key topics, and provides an intelligent Q&A chat interface to help students understand complex material faster.

## Visuals

### Homepage
![Homepage](Project-images/Homepage.png)

### Dashboard
![Dashboard](Project-images/Dashboard.png)

### Interactive Mind Map
![Mind Map](Project-images/Mindtree.png)

### AI Q&A Interface
![AI Q&A](Project-images/AI_Q&A.png)

### Key Topics Extraction
![Key Topics](Project-images/Keytopics.png)

### Predicted Questions
![Predicted Questions](Project-images/Predicted_Q&A.png)

## Features

- **Interactive Mind Maps**: Visualizes concepts from your PDFs in a hierarchical tree structure using React Flow.
- **AI-Powered Q&A**: Chat with your documents. The system uses RAG (Retrieval-Augmented Generation) to provide accurate answers based *only* on the specific document's content.
- **Topic Extraction**: Automatically identifies and explains key topics.
- **Parallel Processing**: Optimized backend processes large PDFs quickly by running analysis and vector embedding tasks concurrently.

## Technology Stack

### Frontend
- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Visualization**: React Flow (for Mind Maps)

### Backend
- **Framework**: FastAPI (Python)
- **LLM**: Google Gemini (Flash 2.0 & Pro)
- **Vector DB**: Pinecone
- **Storage**: Google Cloud Storage (GCS)
- **Caching/Progress**: Redis
- **Orchestration**: LangGraph (for analysis workflows)

## Quick Start

### Run locally in VS Code

Open this folder in VS Code. Copy `.env.example` to `.env` and fill in the real
PostgreSQL, Gemini, Pinecone, UploadThing, and Google OAuth credentials. Keep
`.env` private. Configure the Google OAuth redirect URI as
`http://localhost:3000/api/auth/callback/google`.

For Docker Desktop, run `docker compose up --build` in the VS Code terminal.
The development Compose file uses the root `.env` for both services and starts
Redis. Open `http://localhost:3000`; the API is at `http://localhost:8000/docs`.
The database must already be reachable and have the Prisma schema applied:
from `backend`, run `prisma db push` against the configured database before
using authentication or documents. Review schema changes before applying them
to a database that contains data.

For a native development run, install backend dependencies from
`backend/requirements.txt`, run `prisma generate`, and install frontend
dependencies with `npm ci` in `frontend`. Copy the root `.env` to
`backend/.env` and `frontend/.env.local`, or link those files to `../.env`.
Start Redis locally, then use separate terminals:

```bash
cd backend && REDIS_URL=redis://localhost:6379 uvicorn main:app --reload
cd frontend && API_URL=http://localhost:8000 npm run dev
```

The native run needs Python 3.12 and Node 20 or newer. The root `.env` defaults
to Docker service names for `REDIS_URL` and `API_URL`, so the overrides above
are required outside Docker.

### Using Docker Compose (Recommended)

The easiest way to run the entire stack (Frontend, Backend, Redis) is with Docker Compose.

```bash
docker-compose up --build
```

Access the app at `http://localhost:3000`.

### Manual Setup

Please refer to the specific README files for detailed setup instructions:

- [Backend README](./backend/README.md)
- [Frontend README](./frontend/README.md)
