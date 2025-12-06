# GenHat: GenAI Has Teeth

GenHat is a document intelligence workspace built in two halves: a FastAPI-powered backend (DocumInt) that ingests PDFs, extracts heading-aware chunks, builds hybrid search indexes, calls Gemini for analysis, and even produces podcast-style narratives; and an Electron renderer that turns that capability into a chat/mind-map/podcast console with persistent tabs, saved insights, and visual mind map launches.

This README provides a detailed description of the architecture, key components, APIs, and instructions to build, run, and extend the project.

## Repository Layout

```
GenHat/
├── Backend/            # PDF ingestion, retrieval, Gemini/TTS orchestration, REST API surface
├── Frontend/           # Electron + TypeScript renderer + assets for the desktop UI
├── README.md           # This file
├── IMPLEMENTATION_SUMMARY.md
├── QUICK_REFERENCE.md
└── LICENSE
```

## Backend (DocumInt)

The `Backend` folder is the document intelligence engine that powers every analysis and podcast available in the UI.

- **PDF intelligence**: `pdf_extractor.py`, `src/extract/content_chunker.py`, and `src/extract/heading_extractor.py` parse PDFs via PyMuPDF, detect heading structure, and break the file into heading-aligned chunks stored with page references.
- **Retrieval**: `src/retrieval/hybrid_retriever.py` combines BM25 scoring with sentence-transformer embeddings to produce a diverse top-k list. Aggregated chunks (score, page, heading) are formatted by `src/output/formatter.py` so the renderer knows how to highlight them.
- **Insights & storytelling**: Endpoints call Gemini (via `analyze_chunks_with_gemini`) for one-shot aggregated analysis, and `podcastify-analysis`/`generate-podcast` routes produce narratives + Azure TTS audio, persisting metadata per `project/<insight>/` folder.
- **Persistence**: Projects are cached in `<DOCUMINT_DATA_DIR>/<project>/` with `meta.json`, `chunks.json`, and `insights/` subfolders. File deduplication by SHA-256 avoids reprocessing.
- **Serving & utilities**: `app.py` wires FastAPI routes (see API overview below), optionally serves a built frontend when `DOCUMINT_FRONTEND_DIST` points to a `dist` directory, and exposes CLI tooling via `src/run_pipeline.py` for offline pipeline execution (Challenge 1B).

### Environment Variables

| Variable | Purpose |
| --- | --- |
| `DOCUMINT_DATA_DIR` | Base path for cached project data (default `./data/projects`). |
| `DOCUMINT_FRONTEND_DIST` | Absolute path to Electron/SPA build to serve from FastAPI. |
| `VITE_GEMINI_API_KEY` | Gemini/Generative Language API key for analysis endpoints. |
| `SPEECH_API_KEY` / `SPEECH_REGION` | Azure Cognitive Services settings for TTS. |

Leaving Gemini/TTS vars unset results in graceful fallbacks and clear error responses.

### Backend Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r Backend/requirements.txt
```

Run the backend:

```powershell
python Backend/app.py
# or
uvicorn Backend.app:app --host 0.0.0.0 --port 8080 --reload
```

The backend listens on port `8080` by default.

## System Architecture

High-level dataflow across the stack:

```
┌────────────────────┐        Upload PDFs         ┌─────────────────────────┐
│  Electron Frontend │  ───────────────────────▶  │  FastAPI Backend        │
│  (Renderer: Chat,  │                             │  (DocumInt)             │
│   Mind Map, Audio) │        Cache Status        │                         │
└─────────┬──────────┘  ◀───────────────────────  │  cache-pdfs,            │
		  │                                       │  cache-status           │
		  │ Query / Analyze / Generate            │                         │
		  └──────────────────────────────────────▶│  query-pdfs,            │
												 │  analyze-chunks-with-    │
												 │  gemini, podcastify,     │
												 │  generate-podcast        │
												 └──────────┬───────────────┘
															│
									  Persisted Project     │
									  Cache + Insights      │
															▼
								  ┌──────────────────────────────┐
								  │ DOCUMINT_DATA_DIR/projects   │
								  │  - meta.json                 │
								  │  - chunks.json               │
								  │  - insights/<id>/            │
								  │      analysis.json           │
								  │      script.txt              │
								  │      podcast.mp3             │
								  └──────────────────────────────┘

Frontend specifics:

┌───────────────────────────────────────────────────────────────────────────────┐
│ Renderer (TypeScript)                                                          │
│ - `src/renderer.ts` manages tabs, chat UI, file list, and mode switching       │
│ - `src/api.ts` talks to backend routes                                         │
│ - Saved items: `savedMindmaps`, `savedPodcasts` persisted via project save     │
│ - Mind maps open `src/mindmap/index.html` (React Flow + Dagre layout)          │
└───────────────────────────────────────────────────────────────────────────────┘

Backend specifics:

┌───────────────────────────────────────────────────────────────────────────────┐
│ FastAPI (`Backend/app.py`)                                                     │
│ - Ingest: `cache-pdfs`, `append-pdf`                                          │
│ - Status: `cache-status/{cache_key}`                                          │
│ - Retrieve: `query-pdfs` (hybrid BM25 + embeddings)                           │
│ - Analyze: `analyze-chunks-with-gemini`                                       │
│ - Storytelling: `podcastify-analysis`, `generate-podcast`                     │
│ - Serve SPA when `DOCUMINT_FRONTEND_DIST` is set                              │
└───────────────────────────────────────────────────────────────────────────────┘

## Frontend (Electron Chat + Mind Map)

The `Frontend` Electron app is a lightweight shell that talks to the backend via REST. It offers:

- **Persistent tabs** with automatic state syncing: each tab remembers its chat history, platform mode (`chat`, `mindmap`, or `podcast`), and typing indicator.
- **Mode switching** from the chat input bar (`+` button) to toggle between Gemini chat, mind maps, and podcast pipelines while keeping the same tab.
- **Chat rendering** that supports Markdown, copy/edit controls, and the generated `Open Mind Map` button that relaunches a dedicated React Flow mind map window.
- **Saved insights** in the sidebar (mind maps + podcasts) that persist between sessions, launching the visualization or transcript when clicked.
- **PDF management** with drag-and-drop file list, status overlays (`cachePDFs`, `waitForCacheReadyWithProgress`), and error handling.

The renderer is defined in `Frontend/src/renderer.ts` and communicates with `./api.js` wrappers for backend endpoints; it also includes local helpers for tab rendering, audio spectrum visualization, and Lucide icon initialization.

### Frontend Setup

```powershell
cd Frontend
npm install
npm start
```

This kicks off Electron, opening the renderer window (and devtools by default).

## Features

- Document ingestion and indexing with real-time progress overlays
- Hybrid retrieval combining BM25 with embeddings for robust top-k selection
- Gemini-powered analysis consolidating top sections into actionable insights
- Mind map generation and visualization (React Flow, Dagre layout, custom nodes)
- Podcast generation: script creation and Azure TTS audio playback with spectrum
- Persistent tabs and saved insights across sessions via project export/import
- Clean tab naming aligned to mode (`Chat`, `Mind Map`, `Podcast`)

## Running the Full Stack

1. Launch the backend as described above (ensure Gemini/Azure vars are set if needed).
2. Start the Electron frontend from `Frontend/` and upload PDFs via the sidebar.
3. Once documents are indexed (progress overlay shows status), use the chat input to ask questions, switch to mind map mode, or generate podcasts. The UI uses the backend’s `cache-pdfs`, `analyze`, `generate` endpoints behind the scenes.

## API Highlights

The backend exposes the following key endpoints (all assume `http://localhost:8080`):

- `POST /cache-pdfs`: ingest project PDFs and return a `cache_key`. Triggered when the frontend uploads files.
- `GET /cache-status/{cache_key}`: poll while indexing.
- `POST /query-pdfs`: retrieve the top-k hybrid search results.
- `POST /analyze-chunks-with-gemini`: perform Gemini analysis and persist an insight.
- `POST /podcastify-analysis` + `POST /generate-podcast`: turn insights into narrated scripts and MP3s.
- `GET /projects/{project_name}/insights/{insight_id}`: fetch saved analysis (scripts/audio URLs).

The frontend uses these endpoints transparently via `Frontend/src/api.js`, augmenting responses with local UI state.

## Development Notes

- **Mind map launching**: When Gemini returns a mind map tree (`generateMindmap`), the renderer saves `mindmapData` with the chat message and replays the bespoke button after tab switches. Clicking it opens `Frontend/src/mindmap/index.html`, which renders a React Flow visualization with Dagre layout, custom node styles, and controls for fit view.
- **Saved podcasts + transcripts**: Podcast UI elements include a play/pause button, spectrum animation (`initializeAudioSpectrum`), and transcript popups.
- **Project saves**: `saveCurrentProject` dumps app state, tabs, chatMessages, files, and backend cache so sessions can be restored with `importProject`. Exported caches reuse deduped chunks/podcast metadata.
- **Tab naming** recently switched to type-only (`Chat`, `Mind Map`, `Podcast`) so the UI stays clean.

- **Scrollbars in progress list**: The file progress overlay hides native scrollbars while remaining scrollable for a clean look.

## Troubleshooting & Tips

- If Gemini requests fail, confirm `VITE_GEMINI_API_KEY` is set and unrestricted (CORS/quotas). Backend returns a helpful string instead of crashing when the key is missing.
- Azure TTS errors resolve after setting `SPEECH_API_KEY` and `SPEECH_REGION` with a valid subscription.
- Slow indexing indicates long downloads for embedding models; prefetching sentence-transformers on a GPU machine helps.
- UI issues: renderer logs to the devtools console (opened automatically by Electron) and uses Lucide icons, so keep the CDN reachable.

## Licensing

See the top-level `LICENSE` for terms.