import os
from typing import List, Any, Dict
from dotenv import load_dotenv
from unstructured_transform_client import TransformClient
from unstructured.staging.base import elements_from_dicts
from unstructured.chunking.title import chunk_by_title

load_dotenv()

UNSTRUCTURED_API_KEY = os.getenv("UNSTRUCTURED_API_KEY")

def partition_and_chunk_pdf(file_path: str) -> List[Any]:
    """
    Serverless Ingestion Pipeline:
    1. Uses Unstructured Transform Serverless API (Cloud handles OCR, Layout & Tables).
    2. Converts cloud elements to Unstructured Element objects.
    3. Runs intelligent title-based chunking while preserving page numbers and table HTML.
    """
    if not UNSTRUCTURED_API_KEY:
        raise ValueError("UNSTRUCTURED_API_KEY is required for serverless PDF partitioning.")

    client = TransformClient(api_key=UNSTRUCTURED_API_KEY)

    print(f"☁️ [SERVERLESS UNSTRUCTURED] Uploading {os.path.basename(file_path)} to Unstructured Cloud...")
    
    with open(file_path, "rb") as f:
        response = client.parse.run(input=f, output="elements")

    raw_elements = response.elements if hasattr(response, "elements") else (
        response if isinstance(response, list) else []
    )

    if not raw_elements:
        raise ValueError("No elements returned from Unstructured Serverless API.")

    # Convert SDK elements to standard dictionary representations
    element_dicts: List[Dict[str, Any]] = []
    for el in raw_elements:
        if hasattr(el, "to_dict"):
            d = el.to_dict()
        elif hasattr(el, "__dict__"):
            d = el.__dict__
        elif isinstance(el, dict):
            d = el
        else:
            continue

        raw_meta = d.get("metadata") or {}
        # Filter out None values (e.g. coordinates: None) which cause Unstructured's elements_from_dicts to crash
        cleaned_meta = {k: v for k, v in raw_meta.items() if v is not None} if isinstance(raw_meta, dict) else {}

        # Standardize structure for unstructured.staging.base
        element_dicts.append({
            "element_id": d.get("element_id"),
            "type": d.get("type", "NarrativeText"),
            "text": d.get("text", ""),
            "metadata": cleaned_meta
        })

    print(f"📦 Received {len(element_dicts)} atomic elements from cloud. Applying title-based chunking...")

    # Convert to Unstructured Element objects
    unstructured_elements = elements_from_dicts(element_dicts)

    # Intelligent Title-Based Chunking (Pure Python in memory, preserving page numbers & orig_elements)
    chunks = chunk_by_title(
        elements=unstructured_elements,
        max_characters=3000,
        new_after_n_chars=2400,
        combine_text_under_n_chars=500
    )

    print(f"✅ Chunking complete: {len(chunks)} smart chunks generated with page numbers.")
    return chunks
