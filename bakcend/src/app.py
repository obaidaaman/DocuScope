from fastapi import FastAPI
from contextlib import asynccontextmanager
from sqlalchemy import text

from .database import engine, Base
from .routers import (
    document_router,
    reconciliation_router,
    auth_router,
    project_router
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE compliance_audits "
            "ADD COLUMN IF NOT EXISTS finalized BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE compliance_audits "
            "ADD COLUMN IF NOT EXISTS source_truth_doc_id INTEGER "
            "REFERENCES documents(id) ON DELETE SET NULL"
        ))
    yield
    await engine.dispose()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SuperDocs Analyst Ingestion Engine",
    description="Multimodal Document Ingestion, Auth, Multi-Tenancy & Reconciliation with pgvector",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(project_router)
app.include_router(document_router)
app.include_router(reconciliation_router)

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "healthy", "service": "SuperDocs Analyst Engine"}
