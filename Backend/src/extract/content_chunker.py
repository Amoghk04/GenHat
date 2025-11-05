# extract/content_chunker.py
import fitz
from typing import List, Dict, Any
import re

def extract_chunks_with_headings(pdf_path: str, headings: List[str]) -> List[Dict[str, Any]]:
    doc = fitz.open(pdf_path)
    chunks = []
    all_text_per_page = [page.get_text("text") for page in doc]
    all_text = "\n".join(all_text_per_page)
    doc.close()

    # If no headings found, create one chunk with all content
    if not headings:
        if all_text.strip():
            chunks.append({
                "heading": "Document Content",
                "content": all_text.strip(),
                "pdf_name": pdf_path.split("/")[-1],
                "page_number": 1
            })
        return chunks

    headings_pattern = '|'.join(re.escape(h) for h in sorted(headings, key=len, reverse=True))
    split_pattern = rf"(?=^({headings_pattern})\s*$)"  # Lookahead to keep heading
    parts = re.split(split_pattern, all_text, flags=re.MULTILINE)

    # Group into heading-content pairs
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        content = parts[i+1].strip() if i+1 < len(parts) else ""
        if heading and content:
            chunks.append({
                "heading": heading,
                "content": content,
                "pdf_name": pdf_path.split("/")[-1],
                "page_number": find_page_number(content, all_text_per_page)
            })
    
    # If no chunks were created despite having headings, create a fallback chunk
    if not chunks and all_text.strip():
        chunks.append({
            "heading": "Document Content",
            "content": all_text.strip(),
            "pdf_name": pdf_path.split("/")[-1],
            "page_number": 1
        })
    
    return chunks


def find_page_number(content: str, pages: List[str]) -> int:
    for i, page in enumerate(pages):
        if content[:20] in page:
            return i + 1
    return 1  # Changed from -1 to 1 as default
