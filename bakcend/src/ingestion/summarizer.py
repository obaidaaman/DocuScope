import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

load_dotenv()

# Vision model for mixed content
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
vision_llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

async def generate_ai_summary_if_needed(text: str, tables: List[str], images: List[str]) -> str:
    """
    Creates an AI-enhanced searchable summary if a chunk contains mixed content (tables/images).
    If plain text only, returns original text directly (saves time and LLM cost).
    """
    if not tables and not images:
        return text

    prompt = f"""You are creating a searchable description for document content retrieval.

CONTENT TO ANALYZE:
TEXT CONTENT:
{text}
"""
    if tables:
        prompt += "\nTABLES:\n"
        for i, table in enumerate(tables):
            prompt += f"Table {i+1}:\n{table}\n\n"

    prompt += """
YOUR TASK:
Generate a comprehensive, searchable description that covers:
1. Key facts, rates, payment terms, dates, numbers, and data points from text and tables.
2. Main topics and parties involved.
3. Questions this content could answer.
4. Visual charts/diagram analysis if images exist.

Make it detailed and searchable - prioritize findability over brevity.

SEARCHABLE DESCRIPTION:"""

    message_content = [{"type": "text", "text": prompt}]

    for image_b64 in images:
        message_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
        })

    try:
        message = HumanMessage(content=message_content)
        response = await vision_llm.ainvoke([message])
        return response.content
    except Exception as e:
        print(f"[WARN] AI summary generation failed: {e}. Falling back to raw text.")
        summary = text
        if tables:
            summary += f" [Contains {len(tables)} table(s)]"
        return summary
