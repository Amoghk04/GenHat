import os
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
import fitz  # PyMuPDF
import jsonschema

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PDFOutlineExtractor:
    
    def __init__(self, schema_path: Optional[str] = None):
        self.schema = None
        if schema_path and os.path.exists(schema_path):
            try:
                with open(schema_path, 'r') as f:
                    self.schema = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load schema: {e}")
    
    def extract_title(self, doc: fitz.Document) -> str:
        if len(doc) > 0:
            page = doc[0]
            blocks = page.get_text("dict")["blocks"]
            page_height = page.rect.height

            # Gather all font sizes in the top half
            font_sizes = []
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            y_pos = block["bbox"][1]
                            if y_pos < page_height * 0.5:
                                font_sizes.append(span["size"])

            if not font_sizes:
                return ""

            max_font_size = max(font_sizes)

            # Go line by line, add largest font size
            def merge_strings(s1: str, s2: str) -> str:
                max_overlap = 0
                overlap_len = min(len(s1), len(s2))
                for i in range(1, overlap_len + 1):
                    if s1.endswith(s2[:i]):
                        max_overlap = i
                return s1 + s2[max_overlap:]

            title_lines = []

            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        line_text = ""
                        line_font_sizes = []
                        y_pos = block["bbox"][1]

                        if y_pos < page_height * 0.5:
                            for span in line["spans"]:
                                line_font_sizes.append(span["size"])
                                line_text += span["text"].strip() + " "

                            line_text = line_text.strip()
                            if not line_text:
                                continue

                            # Heading with largest font
                            if all(abs(sz - max_font_size) < 1e-2 for sz in line_font_sizes):
                                if title_lines:
                                    title_lines[-1] = merge_strings(title_lines[-1], line_text)
                                else:
                                    title_lines.append(line_text)
                            
                            # Heading with slightly smaller font 
                            elif all(sz >= 22 and sz < max_font_size for sz in line_font_sizes):
                                title_lines[-1] += " "
                                if title_lines:
                                    title_lines[-1] = merge_strings(title_lines[-1], line_text) + " "
                                
                                else:
                                    title_lines.append(line_text)
                    if title_lines:
                        title_lines[-1] += " "

            # Return the fully merged title
            return title_lines[-1] if title_lines else ""
    
    def detect_heading_level(self, text: str, font_size: float, font_flags: int, 
                       avg_font_size: float, x_position: float = 0, page_num: int = 0) -> Optional[str]:
        clean_text = text.strip()
        if not clean_text or len(clean_text) < 2:
            return None
            
        # Skip very long texts, paragraphs
        if len(clean_text) > 300:
            return None
        
        # Enhanced font analysis
        font_ratio = font_size / avg_font_size if avg_font_size > 0 else 1.0
        is_bold = bool(font_flags & 2**4)
        is_italic = bool(font_flags & 2**1)
        
        # Enhanced heading patterns with more coverage
        heading_patterns = [
            # Numbered sections
            r'^\d+\.?\s+[A-Z]',  # "1. Chapter" or "1 Chapter"
            r'^\d+\.\d+\.?\s+[A-Z]',  # "1.1 Section"
            r'^\d+\.\d+\.\d+\.?\s+[A-Z]',  # "1.1.1 Subsection"
            
            # Roman numerals
            r'^[IVX]+\.\s+[A-Z]',  # "I. Introduction"
            
            # Letter sections
            r'^[A-Z]\.\s+[A-Z]',  # "A. Introduction"
            
            # Chapter/Section keywords
            r'^(Chapter|Section|Part|Appendix)\s+\d+',
            r'^(CHAPTER|SECTION|PART|APPENDIX)\s+\d+',
            
            # All caps
            r'^[A-Z][A-Z\s]{3,50}$',
            
            # Title case patterns
            r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){1,8}$',
            
            # Question headings
            r'^(What|How|Why|When|Where|Who)\s+[A-Z]',
            
            # Conclusion/Summary patterns
            r'^(Conclusion|Summary|Abstract|Introduction|Background|Methodology|Results|Discussion)s?$',
        ]
        
        has_heading_pattern = any(re.match(pattern, clean_text, re.IGNORECASE) 
                                 for pattern in heading_patterns)
        
        # Position-based hints
        is_left_aligned = x_position < 0.1  # Close to left margin
        
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
        if is_italic:
            score += 1
        
        # Pattern scoring
        if has_heading_pattern:
            score += 3
        
        # Position scoring
        if is_left_aligned:
            score += 1
        
        # Length scoring
        if is_reasonable_length:
            score += 1
        
        # First page bonus (more likely to have headings)
        if page_num == 1:
            score += 1
        
        # Determine level based on score and specific criteria
        if score >= 4:  # Threshold for being a heading
            # Classify H1, H2, H3 based on font size and patterns
            if (font_ratio >= 1.6 or 
                re.match(r'^(CHAPTER|PART|SECTION)\s+\d+', clean_text, re.IGNORECASE) or
                re.match(r'^[A-Z][A-Z\s]{5,}$', clean_text)):
                return "H1"
            elif (font_ratio >= 1.3 or 
                  re.match(r'^\d+\.?\s+[A-Z]', clean_text) or
                  re.match(r'^[IVX]+\.\s', clean_text)):
                return "H2"
            elif score >= 4:
                return "H3"
        
        return None
    
    def calculate_average_font_size(self, doc: fitz.Document) -> float:
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
    
    def detect_table_of_contents(self, doc: fitz.Document) -> Optional[List[Dict]]:
        toc_outline = []
        
        # First check if PDF has built-in table of contents
        try:
            pdf_toc = doc.get_toc()
            if pdf_toc:
                logger.info("Found built-in PDF table of contents")
                for level, title, page in pdf_toc:
                    if title.strip() and page > 0:
                        # Map PDF TOC levels to our heading levels
                        if level == 1:
                            heading_level = "H1"
                        elif level == 2:
                            heading_level = "H2"
                        else:
                            heading_level = "H3"
                        
                        toc_outline.append({
                            "level": heading_level,
                            "text": title.strip(),
                            "page": page - 1
                        })
                return toc_outline if toc_outline else None
        except Exception as e:
            logger.debug(f"No built-in TOC found: {e}")
        
        # Search for manual table of contents in first few pages
        toc_patterns = [
            r'table\s+of\s+contents',
            '''r'contents',
            #r'index','''
        ]
        
        max_search_pages = min(5, len(doc))  # Search first 5 pages
        
        for page_num in range(max_search_pages):
            page = doc[page_num]
            page_text = page.get_text()
            
            # Check if this page contains TOC keywords
            if any(re.search(pattern, page.get_text().lower()) for pattern in toc_patterns):
                logger.info(f"Potential TOC found on page {page_num + 1}")
                page_text_split = page_text.split('\n')
                for i in range(len(page_text_split)):
                    if "table of contents" in page_text_split[i].lower():
                        page_text = page_text_split[i + 1:]
                        break
                toc_entries = self.get_outline_from_toc(page_text)
                
                if toc_entries:
                    return toc_entries
        
        return None
    
    def get_outline_from_toc(self, page_text: list) -> List[Dict]:
        outline = []
        
        # Clean up the input - remove empty strings and strip whitespace
        entries = [entry.strip() for entry in page_text if entry.strip()]
        
        i = 0
        while i < len(entries):
            current_entry = entries[i]
            
            # Check if current entry is a section number (e.g., "1", "2", "2.1", "2.1.", etc.)
            if self._is_section_number(current_entry):
                # This is a numbered section
                section_num = current_entry
                
                # Determine level based on number of numeric parts
                level = self._get_heading_level(section_num)
                
                # Collect title parts until we find a page number
                title_parts = []
                i += 1
                
                while i < len(entries):
                    # Check if this looks like a page number
                    if entries[i].isdigit() and int(entries[i]) < 1000:
                        page_num = int(entries[i])
                        title = " ".join(title_parts).strip()
                        
                        if title:  # Only add if we have a title
                            outline.append({
                                "level": level,
                                "text": f"{section_num} {title}",  # Include section number
                                "page": page_num
                            })
                        break
                    else:
                        title_parts.append(entries[i])
                        i += 1
            
            # Handle non-numbered entries (like "Revision History")
            elif current_entry[0].isupper() and not current_entry.isdigit():
                title_parts = [current_entry]
                i += 1
                
                while i < len(entries):
                    next_entry = entries[i]
                    
                    if next_entry.isdigit() and int(next_entry) < 1000:
                        page_num = int(next_entry)
                        title = " ".join(title_parts).strip()
                        
                        outline.append({
                            "level": "H1",
                            "text": title,
                            "page": page_num - 1
                        })
                        break
                    elif self._is_section_number(next_entry):
                        i -= 1  # Back up one so we don't skip the next section
                        break
                    else:
                        title_parts.append(next_entry)
                        i += 1
            
            i += 1
        
        return outline

    def _is_section_number(self, text: str) -> bool:
        # Remove trailing dot if present
        clean_text = text.rstrip('.')
        
        # Handle simple numbers like "1", "2"
        if clean_text.isdigit():
            return True
        
        # Handle dotted numbers like "2.1", "2.1.1"
        if '.' in clean_text:
            parts = clean_text.split('.')
            return all(part.isdigit() for part in parts)
        
        return False

    def _get_heading_level(self, section_num: str) -> str:
        # Remove trailing dot if present
        clean_num = section_num.rstrip('.')
        
        # Count the number of numeric parts separated by dots
        if '.' in clean_num:
            parts = clean_num.split('.')
            num_parts = len(parts)
        else:
            num_parts = 1
        
        # Map number of parts to heading levels
        if num_parts == 1:  # "1" or "1."
            return "H1"
        elif num_parts == 2:  # "2.1" or "2.1."
            return "H2"
        else:  # "3.1.1" or "3.1.1." or more
            return "H3"

    def extract_outline(self, pdf_path: str) -> Dict[str, Any]:
        start_time = time.time()
        
        try:
            doc = fitz.open(pdf_path)
            
            # Extract title
            title = self.extract_title(doc)
            
            # First try to extract outline from table of contents
            toc_outline = self.detect_table_of_contents(doc)
            
            if toc_outline:
                logger.info("Using table of contents for outline extraction")
                outline = toc_outline
                
                doc.close()
                
                result = {
                    "title": title,
                    "outline": outline
                }
                
                result = self.validate_and_clean_result(result)
                
                processing_time = time.time() - start_time
                logger.info(f"Processed {pdf_path} using TOC in {processing_time:.2f}s, found {len(outline)} headings")
                
                return result
            
            # If no TOC found, fall back to original method
            logger.info("No table of contents found, using content analysis")
            
            # Calculate baseline font size
            avg_font_size = self.calculate_average_font_size(doc)
            
            # Collect all text elements with context
            all_elements = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                blocks = page.get_text("dict")["blocks"]
                page_height = page.rect.height
                page_width = page.rect.width
                
                for block_idx, block in enumerate(blocks):
                    if "lines" in block:
                        for line_idx, line in enumerate(block["lines"]):
                            for span_idx, span in enumerate(line["spans"]):
                                text = span["text"].strip()
                                if text:
                                    all_elements.append({
                                        'text': text,
                                        'font_size': span["size"],
                                        'font_flags': span["flags"],
                                        'y_position': block["bbox"][1] / page_height,
                                        'x_position': block["bbox"][0] / page_width,
                                        'page': page_num,
                                        'block_idx': block_idx,
                                        'line_idx': line_idx
                                    })
            
            # Add contextual information
            for i, element in enumerate(all_elements):
                # Previous and next font sizes for comparison
                prev_font = all_elements[i-1]['font_size'] if i > 0 else element['font_size']
                next_font = all_elements[i+1]['font_size'] if i < len(all_elements)-1 else element['font_size']
                
                element['font_larger_than_prev'] = element['font_size'] > prev_font
                element['font_larger_than_next'] = element['font_size'] > next_font
                
                # Isolation check (no text nearby)
                element['is_isolated'] = self.check_isolation(all_elements, i)
            
            # Detect headings with enhanced context
            outline = []
            seen_headings = set()
            
            for element in all_elements:
                level = self.detect_heading_level(
                    element['text'], 
                    element['font_size'], 
                    element['font_flags'], 
                    avg_font_size,
                    element['y_position'],
                    element['page']
                )
                
                if level and element['text']:
                    # Enhanced duplicate detection
                    text_normalized = re.sub(r'\s+', ' ', element['text'].lower().strip())
                    heading_key = f"{level}:{text_normalized}:{element['page']}"
                    
                    if heading_key not in seen_headings:
                        outline.append({
                            "level": level,
                            "text": element['text'],
                            "page": element['page']
                        })
                        seen_headings.add(heading_key)
            
            # Post-process outline for hierarchical consistency
            outline = self.validate_hierarchy(outline)
            
            doc.close()
            
            result = {
                "title": title,
                "outline": outline
            }
            
            # Enhanced validation
            result = self.validate_and_clean_result(result)
            
            processing_time = time.time() - start_time
            logger.info(f"Processed {pdf_path} in {processing_time:.2f}s, found {len(outline)} headings")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing {pdf_path}: {e}")
            return {
                "title": f"Error processing {Path(pdf_path).name}",
                "outline": []
            }

    def check_isolation(self, all_elements: List[Dict], current_idx: int) -> bool:
        """Check if current element is isolated (likely a heading)."""
        current = all_elements[current_idx]
        isolation_threshold = 0.05  # 5% of page height
        
        # Check elements before and after
        for i in range(max(0, current_idx - 2), min(len(all_elements), current_idx + 3)):
            if i == current_idx:
                continue
            element = all_elements[i]
            
            # Same page and close vertically
            if (element['page'] == current['page'] and 
                abs(element['y_position'] - current['y_position']) < isolation_threshold):
                return False
        
        return True

    def contains_date_or_time_reference(self, text: str) -> bool:
        text_lower = text.lower()
        
        # Year patterns (1900-2099)
        year_patterns = [
            r'\b(19|20)\d{2}\b',  # 1900-2099
            r'\b\d{4}\b',  # Any 4-digit number (conservative approach)
        ]
        
        # Month names (full and abbreviated)
        months = [
            'january', 'february', 'march', 'april', 'may', 'june',
            'july', 'august', 'september', 'october', 'november', 'december',
            'jan', 'feb', 'mar', 'apr', 'may', 'jun',
            'jul', 'aug', 'sep', 'oct', 'nov', 'dec'
        ]
        
        # Date patterns
        date_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # MM/DD/YYYY, DD/MM/YYYY, etc.
            r'\b\d{1,2}[/-]\d{1,2}\b',  # MM/DD, DD/MM
            r'\b\d{1,2}(st|nd|rd|th)\b',  # 1st, 2nd, 3rd, 4th, etc.
        ]
        
        # Time-related words
        time_words = [
            'today', 'tomorrow', 'yesterday', 'week', 'month', 'year',
        ]
        
        # Check for year patterns
        for pattern in year_patterns:
            if re.search(pattern, text):
                return True
        
        # Check for month names
        for month in months:
            if month in text_lower:
                return True
        
        # Check for date patterns
        for pattern in date_patterns:
            if re.search(pattern, text):
                return True
        
        # Check for time-related words
        for word in time_words:
            if re.search(r'\b' + word + r'\b', text_lower):
                return True
        
        return False

    def validate_hierarchy(self, outline: List[Dict]) -> List[Dict]:
        """Validate and fix hierarchical structure."""
        if not outline:
            return []
        
        validated = []
        level_counts = {"H1": 0, "H2": 0, "H3": 0}
        
        for item in outline:
            level = item["level"]
            
            # Hierarchical validation
            if level == "H1":
                level_counts = {"H1": 1, "H2": 0, "H3": 0}
                validated.append(item)
            elif level == "H2":
                if level_counts["H1"] > 0 or not validated:  # Can follow H1 or be first
                    level_counts["H2"] += 1
                    level_counts["H3"] = 0
                    validated.append(item)
            elif level == "H3" and level_counts["H2"] > 0:  # Must follow H2
                level_counts["H3"] += 1
                validated.append(item)
        
        return validated

    def validate_and_clean_result(self, result: Dict) -> Dict:
        """Final validation and cleaning of results with comprehensive duplicate elimination."""
        # Clean title
        title = ""
        if result["title"]:
            title = re.sub(r'\s+', ' ', result["title"].strip())
            result["title"] = title
        
        # Remove duplicate outline items with enhanced detection
        seen_items = set()
        seen_normalized_text = set()
        clean_outline = []
        title_normalized = title.lower().strip() if title else ""
        
        def normalize_text(text: str) -> str:
            """Normalize text for better duplicate detection."""
            # Convert to lowercase and normalize whitespace
            normalized = re.sub(r'\s+', ' ', text.lower().strip())
            # Remove common punctuation and numbers at start/end
            normalized = re.sub(r'^[\d\.\)\]\-\s]+', '', normalized)
            normalized = re.sub(r'[\d\.\)\]\-\s]+$', '', normalized)
            # Remove special characters
            normalized = re.sub(r'[^\w\s]', '', normalized)
            return normalized.strip()
        
        def texts_are_similar(text1: str, text2: str, threshold: float = 0.8) -> bool:
            norm1 = normalize_text(text1)
            norm2 = normalize_text(text2)
            
            if not norm1 or not norm2:
                return False
            
            # Exact match after normalization
            if norm1 == norm2:
                return True
            
            # Check if one is contained in the other
            if norm1 in norm2 or norm2 in norm1:
                return True
            
            # Check similarity ratio
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, norm1, norm2).ratio()
            return similarity >= threshold
        
        for item in result["outline"]:
            item_text = item['text'].strip()
            item_text_normalized = normalize_text(item_text)
            
            # Skip empty or very short headings
            if not item_text or len(item_text_normalized) < 2:
                continue
            
            # Skip if outline text matches title
            if title_normalized and texts_are_similar(item_text, title):
                continue
            
            # Skip headings that contain dates, years, or time references
            if self.contains_date_or_time_reference(item_text):
                continue
            
            # Check for duplicates against already added items
            is_duplicate = False
            for existing_text in seen_normalized_text:
                if texts_are_similar(item_text, existing_text):
                    is_duplicate = True
                    break
            
            # Create unique key for exact duplicate detection
            item_key = f"{item['level']}:{item_text_normalized}:{item['page']}"
            
            if not is_duplicate and item_key not in seen_items:
                clean_outline.append({
                    "level": item["level"],
                    "text": item_text,
                    "page": item["page"]
                })
                seen_items.add(item_key)
                seen_normalized_text.add(item_text)
        
        # Additional pass to remove duplicates that might have different levels
        final_outline = []
        final_seen_normalized = set()
        
        for item in clean_outline:
            item_text_normalized = normalize_text(item['text'])
            
            # Check against already added items in final list
            is_duplicate = False
            for existing_text in final_seen_normalized:
                if texts_are_similar(item['text'], existing_text):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                final_outline.append(item)
                final_seen_normalized.add(item['text'])
        
        result["outline"] = final_outline
        
        # Schema validation
        if self.schema:
            try:
                jsonschema.validate(result, self.schema)
            except jsonschema.ValidationError as e:
                logger.warning(f"Schema validation failed: {e}")
        
        return result


def process_pdfs():
    logger.info("Starting PDF processing for Challenge 1A")
    
    # Defining input and output Paths
    input_dir = Path("/app/input")

    output_dir = Path("/app/output")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize extractor
    extractor = PDFOutlineExtractor()
    
    # Get all PDF files
    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return
    
    logger.info(f"Found {len(pdf_files)} PDF files to process")
    
    total_start_time = time.time()
    successful_count = 0
    
    for pdf_file in pdf_files:
        file_start_time = time.time()
        
        try:
            # Extract outline
            result = extractor.extract_outline(str(pdf_file))
            # Create output JSON file
            output_file = output_dir / f"{pdf_file.stem}.json"
            with open(output_file, "w", encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            file_time = time.time() - file_start_time
            successful_count += 1
            
            logger.info(f"{pdf_file.name} -> {output_file.name} ({file_time:.2f}s)")
            
        except Exception as e:
            logger.error(f"Failed to process {pdf_file.name}: {e}")
            
            # Create error output to ensure file exists
            error_output = output_dir / f"{pdf_file.stem}.json"
            with open(error_output, "w", encoding='utf-8') as f:
                json.dump({
                    "title": f"Error processing {pdf_file.name}",
                    "outline": [],
                    "error": str(e)
                }, f, indent=2)
    
    total_time = time.time() - total_start_time
    logger.info(f"Completed: {successful_count}/{len(pdf_files)} files in {total_time:.2f}s")


if __name__ == "__main__":
    process_pdfs()