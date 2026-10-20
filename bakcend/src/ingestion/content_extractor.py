from typing import Dict, Any, List

def extract_chunk_details(chunk: Any) -> Dict[str, Any]:
    """
    Inspects a chunk and its orig_elements:
    - Extracts raw text
    - Extracts structured table HTML
    - Extracts image base64
    - Identifies exact page number
    """
    data: Dict[str, Any] = {
        "text": getattr(chunk, "text", str(chunk)),
        "tables": [],
        "images": [],
        "page_number": 1,
        "types": ["text"]
    }

    # Unstructured chunk holds original elements in metadata
    pages = set()
    if hasattr(chunk, "metadata") and hasattr(chunk.metadata, "orig_elements"):
        for element in chunk.metadata.orig_elements:
            # 1. Page Number
            elem_page = getattr(getattr(element, "metadata", None), "page_number", None)
            chunk_page = getattr(getattr(chunk, "metadata", None), "page_number", None)
            if elem_page is not None:
                data["page_number"] = elem_page
                pages.add(elem_page)
            elif chunk_page is not None:
                data["page_number"] = chunk_page
                pages.add(chunk_page)

            element_type = type(element).__name__

            # 2. Tables (HTML representation)
            if element_type == "Table":
                data["types"].append("table")
                table_html = getattr(element.metadata, "text_as_html", None)
                if not table_html:
                    table_html = getattr(element, "text", "")
                data["tables"].append(table_html)

            # 3. Images (Base64 representation)
            elif element_type == "Image":
                img_b64 = getattr(getattr(element, "metadata", None), "image_base64", None)
                if img_b64:
                    data["types"].append("image")
                    data["images"].append(img_b64)

    elif hasattr(chunk, "metadata"):
        chunk_page = getattr(chunk.metadata, "page_number", None)
        if chunk_page is not None:
            data["page_number"] = chunk_page
            pages.add(chunk_page)

    data["pages_spanned"] = sorted([p for p in pages if p is not None]) or [data["page_number"]]
    data["types"] = list(set(data["types"]))
    return data

