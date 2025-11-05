from extract.heading_extractor import PDFHeadingExtractor
from extract.content_chunker import extract_chunks_with_headings
from retrieval.hybrid_retriever import build_hybrid_index, search_top_k_hybrid
from output.formatter import format_bm25_output
from src.utils.file_utils import load_json, save_json, ensure_dir
from pathlib import Path
import time
import argparse
import os

def detect_domain(persona: str, task: str) -> str:
    """Detect domain from persona and task for optimized parameters"""
    combined_text = f"{persona} {task}".lower()
    domain_keywords = {
        'travel': ['travel', 'trip', 'vacation', 'tourist', 'planner', 'itinerary', 'destination'],
        'research': ['research', 'study', 'analysis', 'investigation', 'academic', 'paper'],
        'business': ['business', 'professional', 'hr', 'compliance', 'management', 'form'],
        'culinary': ['food', 'cooking', 'recipe', 'chef', 'culinary', 'menu', 'ingredient']
    }
    for domain, keywords in domain_keywords.items():
        if any(keyword in combined_text for keyword in keywords):
            return domain
    return 'general'

def main():
    parser = argparse.ArgumentParser(description='Hybrid BM25 + Embeddings Document Retrieval System')
    parser.add_argument('--input', type=str, default='/app/input/challenge1b_input.json', help='Input JSON file path')
    parser.add_argument('--output', type=str, default='/app/output/output.json', help='Output JSON file path')
    args = parser.parse_args()

    input_path = args.input
    output_path = Path(args.output)
    pdf_dir = Path(os.path.join(os.path.dirname(input_path), "PDFs"))

    # Ensure output directory exists
    ensure_dir(output_path.parent)

    start_time = time.time()

    # Step 1: Extract chunks from PDFs
    extractor = PDFHeadingExtractor()
    all_chunks = []
    for pdf_file in pdf_dir.glob("*.pdf"):
        print(f"🔍 Processing {pdf_file.name}")
        headings = extractor.extract_headings(str(pdf_file))
        chunks = extract_chunks_with_headings(str(pdf_file), headings)
        all_chunks.extend(chunks)
    print(f"✅ Extracted {len(all_chunks)} chunks from PDFs")

    # Step 2: Load input data and filter relevant chunks
    input_data = load_json(input_path)
    persona = input_data['persona']['role']
    task = input_data['job_to_be_done']['task']
    input_docs = [doc['filename'] for doc in input_data['documents']]

    detected_domain = detect_domain(persona, task)
    print(f"🎯 Detected domain: {detected_domain}")

    relevant_chunks = [c for c in all_chunks if c['pdf_name'] in input_docs]
    print(f"✅ Filtered to {len(relevant_chunks)} relevant chunks")

    # Step 3: Build hybrid BM25 + embeddings index and search
    print("🔍 Building hybrid BM25 + embeddings index...")
    retriever = build_hybrid_index(relevant_chunks, domain=detected_domain)
    query = f"{persona} {task}"
    print(f"🔍 Searching with query: '{query}'")
    top_chunks = search_top_k_hybrid(retriever, query, persona=persona, task=task, k=5)
    print(f"✅ Found {len(top_chunks)} top relevant chunks")

    # Step 4: Format output
    output = format_bm25_output(top_chunks, input_docs, persona, task)
    scoring_breakdown = retriever.get_scoring_breakdown(query, persona, task, k=5)
    print(f"\n🚀 Hybrid Retrieval Results:")
    print(f"   - Domain: {detected_domain}")
    print(f"   - BM25 Weight: {scoring_breakdown['weights']['bm25']:.1f}")
    print(f"   - Embedding Weight: {scoring_breakdown['weights']['embedding']:.1f}")
    print(f"   - Embedding Model: {scoring_breakdown['embedding_model']}")
    print(f"   - Enhanced Tokenization: ✅")
    print(f"   - Query Expansion: ✅")
    print(f"   - Multi-field Scoring: ✅")
    print(f"   - Result Diversity: ✅")
    print(f"   - Hybrid Scoring: ✅")
    print(f"\n📋 Top Results with Scores:")
    for i, chunk in enumerate(top_chunks[:3], 1):
        print(f"   {i}. {chunk['pdf_name']} - {chunk.get('heading', 'No heading')}")
        print(f"      Hybrid Score: {chunk['hybrid_score']:.3f}")
        print(f"      BM25 Score: {chunk['bm25_score']:.3f}")
        if 'embedding_score' in chunk:
            print(f"      Embedding Score: {chunk['embedding_score']:.3f}")
        print()

    # Step 5: Save output
    save_json(output, output_path)
    print(f"✅ Output saved to {output_path}")
    print(f"Total time taken: {time.time() - start_time:.2f} seconds")

if __name__ == "__main__":
    main()