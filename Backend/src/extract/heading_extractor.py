import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import fitz  # PyMuPDF

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PDFHeadingExtractor:
    """Extract headings from PDF documents."""
    
    def __init__(self):
        """Initialize the extractor."""
        pass
    
    def detect_heading_level(self, text: str, font_size: float, font_flags: int, 
                       avg_font_size: float, y_position: float = 0, 
                       x_position: float = 0, page_num: int = 0) -> bool:
        """Simplified heading detection - returns True if text is a heading."""
        clean_text = text.strip()
        if not clean_text or len(clean_text) < 2:
            return False
            
        # Skip very long texts (likely paragraphs)
        if len(clean_text) > 300:
            return False
        
        # Enhanced font analysis
        font_ratio = font_size / avg_font_size if avg_font_size > 0 else 1.0
        is_bold = bool(font_flags & 2**4)
        
        # Enhanced heading patterns
        heading_patterns = [
            r'^\d+\.?\s+[A-Z]',  # "1. Chapter" or "1 Chapter"
            r'^\d+\.\d+\.?\s+[A-Z]',  # "1.1 Section"
            r'^\d+\.\d+\.\d+\.?\s+[A-Z]',  # "1.1.1 Subsection"
            r'^[IVX]+\.\s+[A-Z]',  # "I. Introduction"
            r'^[A-Z]\.\s+[A-Z]',  # "A. Introduction"
            r'^(Chapter|Section|Part|Appendix)\s+\d+',
            r'^(CHAPTER|SECTION|PART|APPENDIX)\s+\d+',
            r'^[A-Z][A-Z\s]{3,50}$',
            r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){1,8}$',
            r'^(What|How|Why|When|Where|Who)\s+[A-Z]',
            r'^(Conclusion|Summary|Abstract|Introduction|Background|Methodology|Results|Discussion)s?$',
        ]
        
        has_heading_pattern = any(re.match(pattern, clean_text, re.IGNORECASE) 
                                 for pattern in heading_patterns)
        
        # Position-based hints
        is_left_aligned = x_position < 0.1
        
        # Content-based scoring
        word_count = len(clean_text.split())
        is_reasonable_length = 1 <= word_count <= 20
        
        # Calculate heading score
        score = 0
        
        # Font size scoring
        if font_ratio >= 1.5:
            score += 3
        elif font_ratio >= 1.3:
            score += 2
        elif font_ratio >= 1.1:
            score += 1
        
        # Style scoring
        if is_bold:
            score += 2
        
        # Pattern scoring
        if has_heading_pattern:
            score += 3
        
        # Position scoring
        if is_left_aligned:
            score += 1
        
        # Length scoring
        if is_reasonable_length:
            score += 1
        
        # First page bonus
        if page_num == 1:
            score += 1
        
        return score >= 4
    
    def calculate_average_font_size(self, doc: fitz.Document) -> float:
        """Calculate average font size across the document for baseline comparison."""
        font_sizes = []
        
        # Sample first few pages to get representative font sizes
        max_pages = min(5, len(doc))
        for page_num in range(max_pages):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if span["size"] > 0:
                                font_sizes.append(span["size"])
        
        return sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
    
    def extract_headings(self, pdf_path: str) -> List[str]:
        """Extract all headings from PDF and return as list of strings."""
        try:
            doc = fitz.open(pdf_path)
            
            # Calculate baseline font size
            avg_font_size = self.calculate_average_font_size(doc)
            
            # Collect all text elements with context
            all_elements = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                blocks = page.get_text("dict")["blocks"]
                page_height = page.rect.height
                page_width = page.rect.width
                
                for block in blocks:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                text = span["text"].strip()
                                if text:
                                    all_elements.append({
                                        'text': text,
                                        'font_size': span["size"],
                                        'font_flags': span["flags"],
                                        'y_position': block["bbox"][1] / page_height,
                                        'x_position': block["bbox"][0] / page_width,
                                        'page': page_num
                                    })
            
            # Detect headings
            headings = []
            seen_headings = set()
            
            for element in all_elements:
                is_heading = self.detect_heading_level(
                    element['text'], 
                    element['font_size'], 
                    element['font_flags'], 
                    avg_font_size,
                    element['y_position'],
                    element['x_position'],
                    element['page']
                )
                
                if is_heading and element['text']:
                    # Remove duplicates
                    text_normalized = re.sub(r'\s+', ' ', element['text'].lower().strip())
                    
                    if text_normalized not in seen_headings:
                        headings.append(element['text'])
                        seen_headings.add(text_normalized)
            
            doc.close()
            return headings
            
        except Exception as e:
            logger.error(f"Error processing {pdf_path}: {e}")
            return []