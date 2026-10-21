import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.api import api_router
from app.db.prisma import connect_db, disconnect_db
from app.core.redis import redis_client

app = FastAPI(title="Synora API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await connect_db()
    await redis_client.connect()

@app.on_event("shutdown")
async def shutdown():
    await disconnect_db()
    await redis_client.close()

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to Synora API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
