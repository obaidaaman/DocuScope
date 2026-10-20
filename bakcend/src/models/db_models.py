from sqlalchemy import String, ForeignKey, DateTime, Integer, Text, Boolean, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from typing import List, Optional, Any, Dict
from datetime import datetime

from ..database import Base

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[List["DocumentChunk"]] = relationship(
        back_populates="document", 
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    searchable_content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    tables_html: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    has_images: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_thread_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), default="CONFLICT")
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), default="MEDIUM")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DeliverableSection(Base):
    __tablename__ = "deliverable_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_thread_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    committed_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
