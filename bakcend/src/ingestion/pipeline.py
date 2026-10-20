import os
import asyncio
from typing import List, Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

from ..database import AsyncSessionLocal
from ..models.db_models import Document, DocumentChunk
from .partitioner import partition_and_chunk_pdf
from .content_extractor import extract_chunk_details
from .summarizer import generate_ai_summary_if_needed

load_dotenv()

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

async def run_document_ingestion(doc_id: int, file_path: str):
    """
    Complete Ingestion Pipeline for a single document:
    Partition -> Title-based Chunking -> Mixed Content Enrichment -> Batch Embeddings -> PostgreSQL
    """
    print(f"[INGESTION START] Doc ID: {doc_id} | Path: {file_path}")

    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if not doc:
            print(f"ERROR Doc ID {doc_id} not found in database.")
            return

        doc.status = "PROCESSING"
        await session.commit()

        try:
            # Step 1: Partition & Chunk in background thread (non-blocking)
            chunks = await asyncio.to_thread(partition_and_chunk_pdf, file_path)
            
            if not chunks:
                raise ValueError("No elements or text could be extracted from document.")

            chunk_records: List[Dict[str, Any]] = []
            texts_to_embed: List[str] = []

            # Step 2: Extract details and generate AI summary if needed
            for i, chunk in enumerate(chunks):
                details = extract_chunk_details(chunk)

                searchable_content = await generate_ai_summary_if_needed(
                    text=details["text"],
                    tables=details["tables"],
                    images=details["images"]
                )

                chunk_records.append({
                    "chunk_index": i,
                    "page_number": details["page_number"],
                    "searchable_content": searchable_content,
                    "raw_text": details["text"],
                    "tables_html": details["tables"] if details["tables"] else None,
                    "has_images": len(details["images"]) > 0,
                    "metadata_info": {
                        "types": details["types"],
                        "pages_spanned": details.get("pages_spanned", [details["page_number"]])
                    }
                })

                texts_to_embed.append(searchable_content)

            # Step 3: Batch Embeddings via OpenAI
            print(f"Generating embeddings for {len(texts_to_embed)} chunks (Doc {doc_id})...")
            emb_response = await openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts_to_embed
            )
            embeddings = [item.embedding for item in emb_response.data]

            # Step 4: Save to PostgreSQL document_chunks table
            db_chunks = []
            for record, emb in zip(chunk_records, embeddings):
                db_chunks.append(DocumentChunk(
                    document_id=doc_id,
                    chunk_index=record["chunk_index"],
                    page_number=record["page_number"],
                    searchable_content=record["searchable_content"],
                    raw_text=record["raw_text"],
                    tables_html=record["tables_html"],
                    has_images=record["has_images"],
                    metadata_info=record["metadata_info"],
                    embedding=emb
                ))

            session.add_all(db_chunks)
            doc.status = "PARSED"
            doc.error_message = None
            await session.commit()
            print(f"Success Ingestion Doc ID {doc_id} fully parsed & stored with {len(db_chunks)} chunks.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await session.rollback()
            doc.status = "FAILED"
            doc.error_message = str(e)
            await session.commit()
            print(f"Ingestion faled Doc ID {doc_id}: {str(e)}")
