# Default repository-root build deploys the FastAPI backend.
# The Next.js frontend is built separately with frontend/Dockerfile.
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/prisma ./prisma
RUN prisma generate

COPY backend/main.py ./main.py
COPY backend/app ./app

EXPOSE 8000
CMD ["sh", "-c", "prisma db push --skip-generate && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
