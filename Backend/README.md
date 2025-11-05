# Backend — Document Intelligence Engine (DocumInt)

This folder contains the DocumInt backend: a FastAPI-based document intelligence engine that ingests PDFs, extracts structure-aware chunks, builds a hybrid retrieval index (BM25 + sentence embeddings), and powers higher-level analysis and audio generation (Gemini + Azure TTS). It also serves the compiled frontend when available.

## What it does

- PDF understanding
  - Outline (table-of-contents) extraction from PDFs
  - Heading detection using font/position heuristics with PyMuPDF
  - Content chunking into heading-aligned sections
- Retrieval augmented reading
  - Hybrid search combining BM25 scoring and sentence-transformer embeddings
  - Domain-aware query expansion and weighting (travel, research, business, culinary, general)
  - Diverse top-k selection to avoid near-duplicates
- Projects and persistence
  - Multi-PDF projects cached to disk with dedup by file hash
  - Reuse cached chunks and rebuild indices only when new PDFs arrive
  - Persisted insights, including Gemini analysis, script, and generated audio
- Insights and storytelling
  - One-shot aggregated analysis of top chunks via Gemini API
  - Podcast-style script generation from analysis
  - Text-to-speech using Azure Cognitive Services (optional)
- Frontend integration
  - Serves a prebuilt SPA (if provided) and exposes REST endpoints

## Repository layout (Backend)

```
Backend/
  app.py                    # FastAPI app: APIs, caching, retrieval, Gemini, TTS, frontend serving
  pdf_extractor.py          # Standalone PDF outline/TOC extractor (Challenge 1A)
  server.py                 # (empty)
  requirements.txt          # Python dependencies
  src/
    run_pipeline.py         # CLI pipeline runner (Challenge 1B)
    extract/
      heading_extractor.py  # Heuristic heading detector (PyMuPDF)
      content_chunker.py    # Chunk PDF content by detected headings
    retrieval/
      hybrid_retriever.py   # BM25 + embeddings hybrid retriever
    output/
      formatter.py          # Formats hybrid results into the expected JSON schema
      output.json           # Example output
    utils/
      file_utils.py         # JSON IO, timestamp, mkdir helpers
```

## Architecture

```
PDFs -> HeadingExtractor -> ContentChunker -> HybridRetriever -> Top-k Sections
                                            |                      |
                                            |                      v
                                            |                 Gemini Analysis (single call)
                                            |                      |
                                            v                      v
                                   Project cache (meta/chunks)  Insights (analysis.json, script.txt, podcast.mp3)
```

- Chunking uses detected headings to create semantically meaningful sections with page references.
- Retrieval builds a BM25 index and optionally embeddings; if the embedding model cannot load, it gracefully falls back to BM25-only.
- Analysis aggregates the top N sections into one Gemini prompt to keep costs and latency down, then persists results per project insight.

## Data model (key shapes)

- Chunk
  - pdf_name: string
  - heading: string
  - content: string
  - page_number: int
- Top-k result (augmented chunk)
  - importance_rank: int
  - hybrid_score: float
  - bm25_score: float
  - embedding_score?: float
- Project persistence
  - <DOCUMINT_DATA_DIR>/<project>/
    - meta.json: { project_name, files: [{name, hash, size}], domain, updated_at }
    - chunks.json: [chunk, ...]
    - insights/<insight_id>/
      - analysis.json, script.txt, podcast.mp3

## Environment variables

- DOCUMINT_DATA_DIR: Base directory for persisted projects (default: ./data/projects)
- DOCUMINT_FRONTEND_DIST: Absolute path to built frontend dist (to serve /assets and /static)
- VITE_GEMINI_API_KEY: Google Generative Language API key used by Gemini analysis endpoints
- SPEECH_API_KEY: Azure Cognitive Services Speech key (for TTS)
- SPEECH_REGION: Azure Speech region (for TTS)

If you don’t need Gemini or TTS, you can leave those env vars unset; endpoints will return clear errors or fall back where possible.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r Backend/requirements.txt
```

Python 3.10+ is recommended.

## Run the API server

```bash
# Option A: run app directly (default port 8080)
python Backend/app.py

# Option B: via uvicorn
uvicorn Backend.app:app --host 0.0.0.0 --port 8080 --reload
```

If you have a prebuilt frontend, set DOCUMINT_FRONTEND_DIST to point at its dist folder to serve the SPA from the same server.

## Core endpoints

Base path: http://localhost:8080

- GET /api/
  - Health check: { "message": "DocumInt Backend API" }

- POST /extract-outline
  - Form-data: file=@your.pdf
  - Returns title + outline (H1/H2/H3) using TOC or content heuristics

- POST /cache-pdfs
  - Form-data: project_name?=MyProj, files=@a.pdf, files=@b.pdf, ...
  - Caches new PDFs (dedup by file hash), extracts chunks, builds/updates index
  - Returns { cache_key, project_name, reused, pdf_count }

- GET /cache-status/{cache_key}
  - Poll to see if the retriever and chunks are ready

- POST /append-pdf
  - Form-data: project_name=MyProj, file=@new.pdf
  - Appends a single PDF to an existing project and rebuilds as needed

- GET /project-cache/{project_name}
  - Returns persisted project summary without loading into memory

- POST /query-pdfs
  - Form-data: cache_key, persona, task, k? (default 5)
  - Performs hybrid search and returns top sections with scores

- POST /analyze-chunks-with-gemini
  - Form-data: cache_key, persona, task, k?, max_chunks_to_analyze?, analysis_prompt?, gemini_model?
  - Aggregates top sections and performs one Gemini API call (uses VITE_GEMINI_API_KEY)
  - Persists an insight under the project with an insight_id

- POST /podcastify-analysis
  - JSON: { analysis: <payload from analyze endpoint>, gemini_model?, style?, audience?, duration_hint?, host_name? }
  - Produces a podcast-style script using Gemini

- POST /generate-podcast
  - JSON: { project_name, insight_id, regenerate?, voice?, audio_format? }
  - Generates and caches TTS audio (Azure). Returns audio_url and script

- GET /insight-audio/{project_name}/{insight_id}.mp3
  - Streams generated audio if present

- GET /projects/{project_name}/insights
  - Lists insights for a project (metadata, summary, script presence)

- GET /projects/{project_name}/insights/{insight_id}
  - Returns full analysis JSON plus script and audio_url (if any)

- Frontend routes
  - GET /projects, /arena, /mindmap, and catch-all: serve the SPA index.html when DOCUMINT_FRONTEND_DIST is set

## Typical flow (API)

1) Upload PDFs and build cache

```bash
curl -F "project_name=MyProj" \
     -F "files=@/path/A.pdf" \
     -F "files=@/path/B.pdf" \
     http://localhost:8080/cache-pdfs
```

2) Poll cache status using cache_key

```bash
curl http://localhost:8080/cache-status/<cache_key>
```

3) Retrieve top sections for a persona + task

```bash
curl -F "cache_key=<cache_key>" \
     -F "persona=Food Contractor" \
     -F "task=Prepare a vegetarian buffet menu including gluten-free" \
     -F "k=5" \
     http://localhost:8080/query-pdfs
```

4) Analyze with Gemini (single aggregated call)

```bash
curl -F "cache_key=<cache_key>" \
     -F "persona=Food Contractor" \
     -F "task=Prepare a vegetarian buffet menu including gluten-free" \
     -F "k=5" \
     http://localhost:8080/analyze-chunks-with-gemini
```

Response includes an insight_id; you can later list or fetch it.

5) Generate a narrated podcast for an insight (Azure TTS)

```bash
curl -X POST http://localhost:8080/generate-podcast \
  -H "Content-Type: application/json" \
  -d '{
        "project_name": "MyProj",
        "insight_id": "<returned_id>",
        "voice": "en-US-AvaMultilingualNeural",
        "audio_format": "mp3"
      }'
```

## CLI pipeline (Challenge 1B)

`src/run_pipeline.py` provides a command-line runner to process a folder of PDFs relative to the input JSON (and a sibling `PDFs/` directory):

```bash
python Backend/src/run_pipeline.py \
  --input /app/input/challenge1b_input.json \
  --output /app/output/output.json
```

It will:
- extract headings and chunk from all PDFs in `.../PDFs/`
- build the hybrid index (domain auto-detected from persona + task)
- search top-k and format the output JSON

## Notes and behaviors

- Embeddings are optional. If the sentence-transformer model fails to load (e.g., no GPU or offline), the system continues in BM25-only mode.
- HTTP client for Gemini is optional. If `httpx` is missing, the analysis endpoints return a helpful placeholder instead of crashing.
- Deduplication uses a SHA-256 of file content to avoid reprocessing the same PDF.
- Domain detection adjusts BM25/embedding weights and query expansion to improve relevance per use case.

## Troubleshooting

- Missing Gemini key
  - Set `VITE_GEMINI_API_KEY`. Without it, analysis endpoints will respond with an error or a placeholder string.
- Azure TTS errors
  - Ensure `SPEECH_API_KEY` and `SPEECH_REGION` are set. Install `azure-cognitiveservices-speech` (already in requirements).
- Frontend not served
  - Provide a built frontend and set `DOCUMINT_FRONTEND_DIST` to its `dist` folder. Otherwise, SPA routes return 404.
- Slow embedding builds
  - Models like `paraphrase-MiniLM-L3-v2` are small and CPU-friendly, but first-time downloads take time. Consider pre-downloading or caching HF models.

## License

See the repository’s top-level `LICENSE` file.
