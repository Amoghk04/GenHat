from typing import List, Dict, Any
from src.utils.file_utils import current_timestamp

def format_bm25_output(top_chunks: List[Dict[str, Any]], 
                      input_docs: List[str], 
                      persona: str, 
                      task: str) -> Dict[str, Any]:
    """
    Format BM25 results into the required output JSON structure
    """
    
    # Extract sections (top-level chunks with importance ranking)
    extracted_sections = []
    for chunk in top_chunks:
        section = {
            "document": chunk['pdf_name'],
            "section_title": chunk.get('heading', 'Document Content'),
            "importance_rank": chunk['importance_rank'],
            "page_number": chunk['page_number']
        }
        extracted_sections.append(section)
    
    # Subsection analysis (detailed content from each chunk)
    subsection_analysis = []
    for chunk in top_chunks:
        # Clean and format the content for refined_text
        content = chunk.get('content', '').strip()
        if content:
            # Truncate if too long (keep reasonable length for output)
            if len(content) > 1000:
                content = content[:1000] + "..."
            
            subsection = {
                "document": chunk['pdf_name'],
                "refined_text": content,
                "page_number": chunk['page_number']
            }
            subsection_analysis.append(subsection)
    
    # Build the complete output structure
    output = {
        "metadata": {
            "input_documents": input_docs,
            "persona": persona,
            "job_to_be_done": task,
            "processing_timestamp": current_timestamp()
        },
        "extracted_sections": extracted_sections,
        "subsection_analysis": subsection_analysis
    }
    
    return output 