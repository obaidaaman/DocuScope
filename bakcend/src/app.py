from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy import text

from .database import engine, Base
from .routers import document_router, reconciliation_router

@asynccontextmanager
async def lifespan(app: FastAPI):

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(
    title="SuperDocs Analyst Ingestion Engine",
    description="Multimodal Document Ingestion & Title-Chunking Pipeline with pgvector",
    version="1.0.0",
    lifespan=lifespan
)

# Register routers
app.include_router(document_router)
app.include_router(reconciliation_router)

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "service": "SuperDocs Analyst Engine"}
