# extract/content_chunker.py
import fitz
from typing import List, Dict, Any
import re
from hashlib import sha256

def _make_chunk_id(pdf_name: str, heading: str, page_number: int, snippet: str) -> str:
    base = f"{pdf_name}||{heading}||{page_number}||{snippet[:200]}".encode("utf-8")
    return sha256(base).hexdigest()

def _make_chunk_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()

def extract_chunks_with_headings(pdf_path: str, headings: List[str]) -> List[Dict[str, Any]]:
    doc = fitz.open(pdf_path)
    chunks = []
    all_text_per_page = [page.get_text("text") for page in doc]
    all_text = "\n".join(all_text_per_page)
    doc.close()

    # If no headings found, create one chunk with all content
    if not headings:
        if all_text.strip():
            pdf_name = pdf_path.split("/")[-1]
            content = all_text.strip()
            chunk_hash = _make_chunk_hash(content)
            chunk_id = _make_chunk_id(pdf_name, "Document Content", 1, content)
            chunks.append({
                "heading": "Document Content",
                "content": content,
                "pdf_name": pdf_name,
                "page_number": 1,
                "chunk_id": chunk_id,
                "chunk_hash": chunk_hash
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
            # Sub-chunking for better RAG
            sub_chunks = split_text_sliding_window(content)
            pdf_name = pdf_path.split("/")[-1]
            for sub_chunk in sub_chunks:
                page_number = find_page_number(sub_chunk, all_text_per_page)
                chunk_hash = _make_chunk_hash(sub_chunk)
                chunk_id = _make_chunk_id(pdf_name, heading, page_number, sub_chunk)
                chunks.append({
                    "heading": heading,
                    "content": sub_chunk,
                    "pdf_name": pdf_name,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "chunk_hash": chunk_hash
                })
    
    # If no chunks were created despite having headings, create a fallback chunk
    if not chunks and all_text.strip():
        pdf_name = pdf_path.split("/")[-1]
        content = all_text.strip()
        chunk_hash = _make_chunk_hash(content)
        chunk_id = _make_chunk_id(pdf_name, "Document Content", 1, content)
        chunks.append({
            "heading": "Document Content",
            "content": content,
            "pdf_name": pdf_name,
            "page_number": 1,
            "chunk_id": chunk_id,
            "chunk_hash": chunk_hash
        })
    
    return chunks


def split_text_sliding_window(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into chunks with overlap, respecting sentence boundaries where possible."""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        
        # If we're at the end, just take the rest
        if end >= text_len:
            chunks.append(text[start:])
            break
            
        # Try to find a sentence break near the end
        # Look back from 'end' to find a period/punctuation
        split_point = -1
        search_start = max(start + chunk_size // 2, end - 150) # Look in the last 150 chars or second half
        
        for i in range(end, search_start, -1):
            if i < text_len and text[i] in '.!?\n':
                split_point = i + 1
                break
        
        # If no sentence break, look for space
        if split_point == -1:
            for i in range(end, search_start, -1):
                if i < text_len and text[i].isspace():
                    split_point = i + 1
                    break
                    
        # If still no break found, hard split
        if split_point == -1:
            split_point = end
            
        chunks.append(text[start:split_point].strip())
        
        # Move start forward, subtracting overlap
        # Ensure we don't get stuck
        next_start = split_point - overlap
        if next_start <= start:
            next_start = start + chunk_size // 2 # Force move forward if overlap is too big relative to split
            
        start = max(start + 1, next_start)
        
    return [c for c in chunks if c.strip()]


def find_page_number(content: str, pages: List[str]) -> int:
    for i, page in enumerate(pages):
        if content[:20] in page:
            return i + 1
    return 1  # Changed from -1 to 1 as default
