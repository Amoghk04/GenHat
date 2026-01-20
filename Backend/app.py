from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import html
import tempfile
import os
import sys
import uuid
import json
from pathlib import Path
import aiofiles
from pdf_extractor import PDFOutlineExtractor
from typing import List, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from src.extract import PDFHeadingExtractor
from src.extract.content_chunker import extract_chunks_with_headings
from src.retrieval.hybrid_retriever import build_hybrid_index, search_top_k_hybrid
from src.retrieval.vector_store import load_embeddings, save_embeddings
from src.output.formatter import format_bm25_output
from src.utils.file_utils import load_json, save_json, ensure_dir
from pydantic import BaseModel
from typing import Optional
from hashlib import sha256
from datetime import datetime, timezone
import re
import numpy as np
import shutil
from dotenv import load_dotenv
import platform
import logging
from prompt_cache import PromptCache
import random

load_dotenv()

app = FastAPI()

# --- OS-specific temp directory configuration ---
def get_os_temp_dir() -> Path:
    """Get OS-appropriate temporary directory"""
    system = platform.system()
    if system == "Linux":
        temp_base = Path("/var/tmp")
    elif system == "Windows":
        temp_base = Path(os.environ.get("TEMP", tempfile.gettempdir()))
    elif system == "Darwin":  # macOS
        temp_base = Path(tempfile.gettempdir())
    else:
        temp_base = Path(tempfile.gettempdir())
    
    # Create GenHat subdirectory in temp
    genhat_temp = temp_base / "genhat"
    genhat_temp.mkdir(parents=True, exist_ok=True)
    return genhat_temp

# Configure logging to temp directory
TEMP_DIR = get_os_temp_dir()
LOG_DIR = TEMP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"genhat_{datetime.now().strftime('%Y%m%d')}.log"

# Initialize Prompt Cache
CACHE_DIR = TEMP_DIR / "cache"
prompt_cache = PromptCache(CACHE_DIR)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logger.info("🚀 GenHat Backend starting...")
logger.info(f"📁 OS: {platform.system()}")
logger.info(f"📁 Temp directory: {TEMP_DIR}")
logger.info(f"📝 Log file: {LOG_FILE}")

# --- Frontend (SPA) static serving integration ---
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(os.environ.get("DOCUMINT_FRONTEND_DIST", "/app/web/dist")).resolve()
ASSETS_SUBDIR = FRONTEND_DIR / "assets"

if ASSETS_SUBDIR.exists():
    # Serve versioned asset files (JS/CSS/images)
    app.mount("/assets", StaticFiles(directory=ASSETS_SUBDIR), name="assets")

# Serve static files from the dist root (for public folder assets)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constant for missing heading label
NO_HEADING = 'No heading'
NO_CONTENT = 'No content'

# Global cache for PDF embeddings and indices
pdf_cache: Dict[str, Any] = {}
executor = ThreadPoolExecutor(max_workers=4)

# Persistence directories - now in temp directory
BASE_DATA_DIR = Path(os.environ.get("DOCUMINT_DATA_DIR", str(TEMP_DIR / "projects"))).resolve()
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"📦 Data directory: {BASE_DATA_DIR}")

# New insight path helpers
INSIGHTS_FOLDER_NAME = "insights"

def _insights_dir(project_name: str) -> Path:
    return _project_path(project_name) / INSIGHTS_FOLDER_NAME

def _insight_dir(project_name: str, insight_id: str) -> Path:
    return _insights_dir(project_name) / insight_id

META_FILENAME = "meta.json"
CHUNKS_FILENAME = "chunks.json"

# Constants
GEMINI_DEFAULT_MODEL = 'gemini-3-flash-preview'

# ---------------- Persistence Helpers -----------------

def _safe_project_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:100] if name else "project"

def _project_path(project_name: str) -> Path:
    return BASE_DATA_DIR / _safe_project_name(project_name)

def _meta_path(project_name: str) -> Path:
    return _project_path(project_name) / META_FILENAME

def _chunks_path(project_name: str) -> Path:
    return _project_path(project_name) / CHUNKS_FILENAME

def load_project_meta(project_name: str) -> Dict[str, Any] | None:
    p = _meta_path(project_name)
    if p.exists():
        try:
            return json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            return None
    return None

def load_project_chunks(project_name: str) -> List[Dict[str, Any]]:
    p = _chunks_path(project_name)
    if p.exists():
        try:
            return json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            return []
    return []

def save_project_state(project_name: str, meta: Dict[str, Any], chunks: List[Dict[str, Any]]):
    proj_dir = _project_path(project_name)
    proj_dir.mkdir(parents=True, exist_ok=True)
    meta = {**meta, "updated_at": datetime.now(timezone.utc).isoformat()}
    with open(_meta_path(project_name), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    with open(_chunks_path(project_name), "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2)

# -------------- Hash Utilities -----------------

def hash_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()

# -------------- Existing endpoints --------------

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

@app.get("/api/")
async def root():
    return {"message": "DocumInt Backend API"}

@app.post("/extract-outline")
async def extract_pdf_outline(file: UploadFile = File(...)):
    """
    Extract outline/table of contents from uploaded PDF file
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    temp_file_path = None
    try:
        # Create unique temporary file path in OS temp directory
        temp_upload_dir = TEMP_DIR / "uploads"
        temp_upload_dir.mkdir(parents=True, exist_ok=True)
        unique_filename = f"pdf_{uuid.uuid4().hex}.pdf"
        temp_file_path = str(temp_upload_dir / unique_filename)
        logger.info(f"📄 Temporary file: {temp_file_path}")
        
        # Read uploaded file content
        content = await file.read()
        
        # Write to temporary file using aiofiles
        async with aiofiles.open(temp_file_path, 'wb') as temp_file:
            await temp_file.write(content)
        
        # Initialize PDF extractor
        extractor = PDFOutlineExtractor()
        
        # Extract outline from PDF
        result = extractor.extract_outline(temp_file_path)
        
        # Clean up temporary file
        os.unlink(temp_file_path)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        # Clean up temporary file in case of error
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError:
                pass
        
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.post("/cache-pdfs")
async def cache_pdfs(project_name: str = Form(""), files: List[UploadFile] = File(...)):
    """
    Cache PDF files and prepare embeddings for persona-based retrieval.
    Supports project-level persistence: if project_name is supplied, previously processed
    PDFs are reused and only new PDFs are processed. Cached chunks persisted on disk.
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No PDF files provided")

        safe_name = _safe_project_name(project_name) if project_name else "session_" + uuid.uuid4().hex[:8]
        existing_meta = load_project_meta(safe_name) or {"project_name": safe_name, "files": []}
        existing_files_meta: List[Dict[str, Any]] = existing_meta.get("files", [])
        existing_hashes = {f.get("hash") for f in existing_files_meta}
        existing_chunks: List[Dict[str, Any]] = load_project_chunks(safe_name)

        new_pdf_paths: List[str] = []
        new_files_meta: List[Dict[str, Any]] = []
        temp_dir: Optional[Path] = None

        # Collect truly new PDFs
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                continue
            content = await file.read()
            file_hash = hash_bytes(content)
            if file_hash in existing_hashes:
                continue  # already processed
            if temp_dir is None:
                # Create temp directory in OS-appropriate location
                temp_dir = TEMP_DIR / "uploads" / f"batch_{uuid.uuid4().hex[:8]}"
                temp_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 Created temp directory: {temp_dir}")
            file_path = str(temp_dir / file.filename)
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            new_pdf_paths.append(file_path)
            new_files_meta.append({
                "name": file.filename,
                "hash": file_hash,
                "size": len(content)
            })
            logger.info(f"📄 Cached PDF: {file.filename} ({len(content)} bytes)")

        cache_key = str(uuid.uuid4())
        pdf_cache[cache_key] = {"processing": True, "project_name": safe_name, "chunks": existing_chunks, "pdf_files": [f["name"] for f in existing_files_meta]}

        # Case 1: Reuse existing (have chunks, no new files)
        if not new_pdf_paths and existing_chunks:
            try:
                detected_domain = detect_domain("general", "general")
                # Attempt to load precomputed embeddings for this project
                loaded = load_embeddings(BASE_DATA_DIR, safe_name)
                if loaded:
                    chunk_ids_loaded, emb_array, model_name = loaded
                    # Reorder chunks to match stored embedding order
                    id_map = {c.get('chunk_id'): c for c in existing_chunks if c.get('chunk_id')}
                    ordered_chunks = [id_map[cid] for cid in chunk_ids_loaded if cid in id_map]
                    if len(ordered_chunks) == emb_array.shape[0]:
                        print(f"🔄 Reusing persisted embeddings for project '{safe_name}' (chunks: {len(ordered_chunks)})")
                        retriever = build_hybrid_index(ordered_chunks, domain=detected_domain, embedding_model=model_name, precomputed_embeddings=emb_array)
                        existing_chunks = ordered_chunks  # align cache ordering
                    else:
                        print("⚠️ Embedding file mismatch; falling back to rebuild.")
                        retriever = build_hybrid_index(existing_chunks, domain=detected_domain)
                else:
                    retriever = build_hybrid_index(existing_chunks, domain=detected_domain)
                pdf_cache[cache_key] = {
                    "retriever": retriever,
                    "chunks": existing_chunks,
                    "domain": detected_domain,
                    "pdf_files": [f["name"] for f in existing_files_meta],
                    "project_name": safe_name,
                    "reused": True
                }
                return {
                    "cache_key": cache_key,
                    "message": "Reused existing project cache",
                    "pdf_count": len(existing_files_meta),
                    "project_name": safe_name,
                    "reused": True
                }
            except Exception as e:
                # If index build fails (e.g. empty/invalid chunks) surface gracefully
                pdf_cache[cache_key] = {
                    "error": f"Index build failed: {e}",
                    "chunks": existing_chunks,
                    "project_name": safe_name
                }
                raise HTTPException(status_code=500, detail=f"Error rebuilding existing cache: {e}")

        # Case 2: Nothing to do (no existing chunks & no new files)
        if not new_pdf_paths and not existing_chunks:
            pdf_cache[cache_key] = {
                "empty": True,
                "project_name": safe_name,
                "chunks": [],
                "pdf_files": []
            }
            return {
                "cache_key": cache_key,
                "message": "No PDFs to process (no new files and no cached data)",
                "pdf_count": 0,
                "project_name": safe_name,
                "reused": False,
                "empty": True
            }

        # Case 3: Process new files (possibly with existing chunks)
        def run_bg():
            try:
                process_pdfs_background(cache_key, new_pdf_paths, temp_dir, safe_name, existing_chunks, existing_meta, new_files_meta)
            except Exception as e:
                pdf_cache[cache_key] = {"error": f"Processing failed: {e}", "project_name": safe_name}

        task = asyncio.create_task(asyncio.to_thread(run_bg))
        pdf_cache[cache_key]["task"] = task

        return {
            "cache_key": cache_key,
            "message": f"Processing {len(new_pdf_paths)} new PDF(s); {len(existing_chunks)} previously cached",
            "pdf_count": len(new_pdf_paths),
            "project_name": safe_name,
            "reused": False
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error caching PDFs: {str(e)}")

def process_single_pdf(pdf_file: str, project_name: str) -> List[Dict[str, Any]]:
    """Process a single PDF file and return its chunks."""
    try:
        extractor = PDFHeadingExtractor()
        logger.info(f"🔍 Processing {os.path.basename(pdf_file)} (project: {project_name})")
        headings = extractor.extract_headings(pdf_file)
        chunks = extract_chunks_with_headings(pdf_file, headings)
        logger.info(f"✅ Extracted {len(chunks)} chunks from {os.path.basename(pdf_file)}")
        return chunks
    except Exception as e:
        logger.error(f"❌ Error processing {pdf_file}: {e}")
        return []

def process_pdfs_background(cache_key: str, pdf_files: List[str], temp_dir: Optional[Path], project_name: str, existing_chunks: List[Dict[str, Any]], existing_meta: Dict[str, Any], new_files_meta: List[Dict[str, Any]]):
    """Synchronous processing run in background task with parallel PDF extraction."""
    try:
        logger.info(f"🔄 Processing {len(pdf_files)} PDFs in parallel for project '{project_name}'")
        # Separate existing vs new for potential incremental embedding update
        existing_chunks_original = list(existing_chunks)
        new_chunks: List[Dict[str, Any]] = []

        # Initialize progress tracking for each file
        total_files = len(pdf_files)
        file_progress = {}
        for i, pdf_file in enumerate(pdf_files):
            file_name = os.path.basename(pdf_file)
            file_progress[file_name] = {
                "index": i,
                "progress": 0,
                "status": "pending",
                "total_files": total_files
            }

        # Update cache with initial progress
        if cache_key in pdf_cache:
            pdf_cache[cache_key]["file_progress"] = file_progress
            pdf_cache[cache_key]["processing"] = True

        # Process PDFs in parallel using ThreadPoolExecutor
        max_workers = min(len(pdf_files), os.cpu_count() or 4)  # Use available CPUs, max 4 by default
        logger.info(f"🚀 Using {max_workers} parallel workers for PDF extraction")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all PDF processing tasks
            future_to_pdf = {
                executor.submit(process_single_pdf, pdf_file, project_name): pdf_file 
                for pdf_file in pdf_files
            }
            
            # Collect results as they complete
            for future in future_to_pdf:
                pdf_file = future_to_pdf[future]
                file_name = os.path.basename(pdf_file)
                try:
                    # Update progress to processing
                    file_progress[file_name]["status"] = "processing"
                    file_progress[file_name]["progress"] = 25
                    
                    chunks = future.result()
                    new_chunks.extend(chunks)
                    
                    # Update progress to completed
                    file_progress[file_name]["progress"] = 100
                    file_progress[file_name]["status"] = "completed"
                    
                    # Update cache with current progress
                    if cache_key in pdf_cache:
                        pdf_cache[cache_key]["file_progress"] = file_progress
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {pdf_file}: {e}")
                    file_progress[file_name]["status"] = "error"
                    file_progress[file_name]["error"] = str(e)
                    # Update cache with error status
                    if cache_key in pdf_cache:
                        pdf_cache[cache_key]["file_progress"] = file_progress

        if not new_chunks and not existing_chunks_original:
            # Nothing extracted – store placeholder
            save_project_state(project_name, {**existing_meta, "files": existing_meta.get("files", []) + new_files_meta, "domain": "general"}, [])
            pdf_cache[cache_key] = {
                "chunks": [],
                "domain": "general",
                "pdf_files": [f["name"] for f in (existing_meta.get("files", []) + new_files_meta)],
                "project_name": project_name,
                "empty": True,
                "file_progress": file_progress,
                "processing": False
            }
            print(f"⚠️ No chunks extracted for project '{project_name}'.")
            return

        detected_domain = detect_domain("general", "general")
        merged_files_meta = existing_meta.get("files", []) + new_files_meta

        incremental_used = False
        retriever = None
        all_chunks_ordered: List[Dict[str, Any]] = []
        try:
            # Attempt incremental only if we have both existing and new chunks
            if existing_chunks_original and new_chunks:
                loaded = load_embeddings(BASE_DATA_DIR, project_name)
                if loaded:
                    loaded_ids, loaded_embs, loaded_model = loaded
                    id_map_existing = {c.get('chunk_id'): c for c in existing_chunks_original if c.get('chunk_id')}
                    reordered_existing = [id_map_existing[cid] for cid in loaded_ids if cid in id_map_existing]
                    if len(reordered_existing) == loaded_embs.shape[0]:
                        from src.retrieval.hybrid_retriever import HybridRetriever
                        temp_retriever = HybridRetriever(domain=detected_domain, embedding_model=loaded_model)
                        new_weighted_texts = [temp_retriever.weighted_text_representation(c) for c in new_chunks]
                        if temp_retriever.embedding_model:
                            new_embs = temp_retriever.embedding_model.encode(new_weighted_texts, show_progress_bar=False)
                            merged_embs = np.vstack([loaded_embs, new_embs])
                            all_chunks_ordered = reordered_existing + new_chunks
                            retriever = build_hybrid_index(all_chunks_ordered, domain=detected_domain, embedding_model=loaded_model, precomputed_embeddings=merged_embs)
                            try:
                                merged_ids = [c.get('chunk_id') for c in all_chunks_ordered if c.get('chunk_id')]
                                if len(merged_ids) == merged_embs.shape[0]:
                                    save_embeddings(BASE_DATA_DIR, project_name, merged_ids, merged_embs, loaded_model)
                                    print(f"💾 Incrementally updated embeddings (old {loaded_embs.shape[0]} + new {new_embs.shape[0]}) for '{project_name}'")
                                else:
                                    print("⚠️ ID/embedding length mismatch after merge; skipping persistence.")
                            except Exception as persist_err:
                                print(f"⚠️ Failed incremental embedding persistence: {persist_err}")
                            incremental_used = True
                        else:
                            print("⚠️ Embedding model unavailable for incremental path; full rebuild.")
                    else:
                        print("⚠️ Persisted embeddings count mismatch with existing chunks; full rebuild.")
                else:
                    print("ℹ️ No persisted embeddings found; performing full rebuild.")
            # Fallback full rebuild
            if retriever is None:
                all_chunks_ordered = existing_chunks_original + new_chunks
                retriever = build_hybrid_index(all_chunks_ordered, domain=detected_domain)
                if retriever.chunk_embeddings is not None:
                    try:
                        chunk_ids = [c.get('chunk_id') for c in all_chunks_ordered if c.get('chunk_id')]
                        if len(chunk_ids) == retriever.chunk_embeddings.shape[0]:
                            save_embeddings(BASE_DATA_DIR, project_name, chunk_ids, retriever.chunk_embeddings, retriever.embedding_model_name)
                            print(f"💾 Saved embeddings after full rebuild for '{project_name}'")
                        else:
                            print("⚠️ Chunk IDs missing during full rebuild persistence.")
                    except Exception as persist_err:
                        print(f"⚠️ Failed to persist embeddings (full rebuild): {persist_err}")
        except Exception as e:
            print(f"❌ Index build failed for project {project_name}: {e}")
            retriever = None
            all_chunks_ordered = existing_chunks_original + new_chunks

        # Persist project state with new ordering
        save_project_state(project_name, {**existing_meta, "files": merged_files_meta, "domain": detected_domain}, all_chunks_ordered)

        pdf_cache[cache_key] = {
            "retriever": retriever,
            "chunks": all_chunks_ordered,
            "domain": detected_domain,
            "pdf_files": [f["name"] for f in merged_files_meta],
            "project_name": project_name,
            "index_error": retriever is None,
            "file_progress": file_progress,
            "processing": False,
            "incremental_embeddings": incremental_used
        }
        logger.info(f"✅ Cached {len(all_chunks_ordered)} total chunks for project '{project_name}' (cache key {cache_key}) incremental={incremental_used}")
    except Exception as e:
        logger.error(f"❌ Error processing PDFs for project {project_name}: {e}")
        # Mark all remaining files as error
        for file_name in file_progress:
            if file_progress[file_name]["status"] != "completed":
                file_progress[file_name]["status"] = "error"
                file_progress[file_name]["error"] = str(e)
        if cache_key in pdf_cache:
            pdf_cache[cache_key]["file_progress"] = file_progress
            pdf_cache[cache_key]["processing"] = False
    finally:
        if temp_dir:
            try:
                logger.info(f"🗑️ Cleaning up temp directory: {temp_dir}")
                shutil.rmtree(temp_dir)
            except Exception as cleanup_error:
                logger.warning(f"⚠️ Failed to cleanup temp directory: {cleanup_error}")

@app.post("/append-pdf")
async def append_pdf(
    project_name: str = Form(...),
    file: UploadFile = File(...)
):
    """Append a single new PDF to an existing project and rebuild embeddings.
    Returns a new cache_key whose status can be polled at /cache-status/{cache_key}.
    If the PDF hash already exists, it simply reuses existing cache (no rebuild)."""
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        safe_name = _safe_project_name(project_name)
        meta = load_project_meta(safe_name)
        if not meta:
            raise HTTPException(status_code=404, detail="Project not found")
        existing_chunks = load_project_chunks(safe_name)
        existing_hashes = {f.get("hash") for f in meta.get("files", [])}
        content = await file.read()
        file_hash = hash_bytes(content)
        if file_hash in existing_hashes:
            # No change; build retriever if missing and return reused status
            cache_key = str(uuid.uuid4())
            try:
                retriever = build_hybrid_index(existing_chunks, domain=meta.get("domain","general"))
            except Exception:
                retriever = None
            pdf_cache[cache_key] = {
                "retriever": retriever,
                "chunks": existing_chunks,
                "domain": meta.get("domain","general"),
                "pdf_files": [f.get("name") for f in meta.get("files", [])],
                "project_name": safe_name,
                "reused": True
            }
            return {"cache_key": cache_key, "message": "PDF already present; reused existing cache", "reused": True}
        # Write temp file to OS temp directory
        temp_dir = TEMP_DIR / "uploads" / f"append_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = str(temp_dir / file.filename)
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(content)
        logger.info(f"📄 Appending PDF: {file.filename} to temp: {temp_path}")
        cache_key = str(uuid.uuid4())
        pdf_cache[cache_key] = {"processing": True, "project_name": safe_name, "chunks": existing_chunks, "pdf_files": [f.get("name") for f in meta.get("files", [])]}
        new_files_meta = [{"name": file.filename, "hash": file_hash, "size": len(content)}]
        def run_bg():
            try:
                process_pdfs_background(cache_key, [temp_path], temp_dir, safe_name, existing_chunks, meta, new_files_meta)
            except Exception as e:
                pdf_cache[cache_key] = {"error": f"Processing failed: {e}", "project_name": safe_name}
        task = asyncio.create_task(asyncio.to_thread(run_bg))
        pdf_cache[cache_key]["task"] = task
        return {"cache_key": cache_key, "message": "Appending PDF and rebuilding embeddings", "reused": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error appending PDF: {e}")

@app.post("/remove-pdf")
async def remove_pdf(
    project_name: str = Form(...),
    filename: str = Form(...)
):
    """Remove a PDF from an existing project and rebuild embeddings without that PDF.
    Returns a new cache_key whose status can be polled at /cache-status/{cache_key}."""
    try:
        safe_name = _safe_project_name(project_name)
        meta = load_project_meta(safe_name)
        if not meta:
            raise HTTPException(status_code=404, detail="Project not found")
        
        existing_files = meta.get("files", [])
        existing_chunks = load_project_chunks(safe_name)
        
        # Find and remove the file from metadata
        file_to_remove = None
        new_files_meta = []
        for f in existing_files:
            if f.get("name") == filename:
                file_to_remove = f
            else:
                new_files_meta.append(f)
        
        if not file_to_remove:
            raise HTTPException(status_code=404, detail=f"PDF '{filename}' not found in project")
        
        # Filter out chunks that belong to the removed PDF
        filtered_chunks = [
            chunk for chunk in existing_chunks 
            if chunk.get('pdf_name') != filename
        ]
        
        print(f"🗑️ Removing '{filename}' from project '{safe_name}'")
        print(f"📊 Chunks before: {len(existing_chunks)}, after: {len(filtered_chunks)}")
        
        # Create new cache key for the updated project
        cache_key = str(uuid.uuid4())
        
        if not filtered_chunks:
            # No chunks left, save empty state
            save_project_state(safe_name, {**meta, "files": new_files_meta, "domain": "general"}, [])
            pdf_cache[cache_key] = {
                "chunks": [],
                "domain": "general",
                "pdf_files": [f["name"] for f in new_files_meta],
                "project_name": safe_name,
                "empty": True
            }
            return {
                "cache_key": cache_key,
                "message": f"Removed '{filename}'. No PDFs remaining in project.",
                "removed": True,
                "remaining_pdfs": 0
            }
        
        # Rebuild the index with remaining chunks
        detected_domain = detect_domain("general", "general")
        try:
            # Attempt to reuse stored embeddings only if full match (rare on removal -> prefer rebuild)
            retriever = build_hybrid_index(filtered_chunks, domain=detected_domain)
            print(f"✅ Rebuilt index with {len(filtered_chunks)} chunks")
            # Persist updated embeddings set
            if retriever.chunk_embeddings is not None:
                try:
                    chunk_ids = [c.get('chunk_id') for c in filtered_chunks if c.get('chunk_id')]
                    if len(chunk_ids) == retriever.chunk_embeddings.shape[0]:
                        save_embeddings(BASE_DATA_DIR, safe_name, chunk_ids, retriever.chunk_embeddings, retriever.embedding_model_name)
                        print(f"💾 Updated persisted embeddings after removal for '{safe_name}'")
                except Exception as persist_err:
                    print(f"⚠️ Failed to persist updated embeddings: {persist_err}")
        except Exception as e:
            print(f"❌ Index rebuild failed: {e}")
            retriever = None
        
        # Save updated project state
        save_project_state(safe_name, {**meta, "files": new_files_meta, "domain": detected_domain}, filtered_chunks)
        
        # Update cache
        pdf_cache[cache_key] = {
            "retriever": retriever,
            "chunks": filtered_chunks,
            "domain": detected_domain,
            "pdf_files": [f["name"] for f in new_files_meta],
            "project_name": safe_name,
            "removed_file": filename,
            "index_error": retriever is None
        }
        
        return {
            "cache_key": cache_key,
            "message": f"Removed '{filename}' and rebuilt embeddings successfully",
            "removed": True,
            "remaining_pdfs": len(new_files_meta),
            "remaining_chunks": len(filtered_chunks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error removing PDF: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error removing PDF: {e}")

@app.post("/query-pdfs")
async def query_pdfs(
    cache_key: str = Form(...),
    persona: str = Form(default="General User"),
    task: str = Form(...),
    k: int = Form(default=5)
):
    """
    Query cached PDFs using persona-based retrieval
    """
    try:
        if cache_key not in pdf_cache:
            raise HTTPException(status_code=404, detail="Cache key not found. Please upload PDFs first.")
        
        cached_data = pdf_cache[cache_key]
        retriever = cached_data["retriever"]
        chunks = cached_data["chunks"]
        
        print(f"🔍 Querying with persona: {persona}, task: {task}")
        print(f"📊 Found {len(chunks)} chunks in cache")
        
        # Detect domain for this specific query
        detected_domain = detect_domain(persona, task)
        print(f"🎯 Detected domain: {detected_domain}")
        
        # Search with hybrid retrieval
        query = f"{persona} {task}"
        print(f"🔍 Searching with query: '{query}'")
        
        try:
            top_chunks = search_top_k_hybrid(retriever, query, persona=persona, task=task, k=k)
            print(f"✅ Found {len(top_chunks)} top chunks")
        except Exception as search_error:
            print(f"❌ Search error: {str(search_error)}")
            raise HTTPException(status_code=500, detail=f"Search error: {str(search_error)}")
        
        # Format results for frontend
        results = []
        for i, chunk in enumerate(top_chunks):
            try:
                result = {
                    "document": chunk.get('pdf_name', 'Unknown'),
                    "section_title": chunk.get('heading', NO_HEADING),
                    "refined_text": chunk.get('content', chunk.get('text', NO_CONTENT)),
                    "page_number": chunk.get('page_number', 1),
                    "importance_rank": chunk.get('hybrid_score', 0),
                    "bm25_score": chunk.get('bm25_score', 0),
                    "embedding_score": chunk.get('embedding_score', 0),
                    "chunk_id": chunk.get('chunk_id'),
                    "chunk_hash": chunk.get('chunk_hash')
                }
                results.append(result)
                print(f"📄 Result {i+1}: {result['document']} - {result['section_title']}")
            except Exception as chunk_error:
                print(f"❌ Error processing chunk {i}: {str(chunk_error)}")
                continue
        
        print(f"✅ Returning {len(results)} results")
        
        return {
            "metadata": {
                "input_documents": cached_data["pdf_files"],
                "persona": persona,
                "job_to_be_done": task,
                "domain": detected_domain
            },
            "extracted_sections": results,
            "subsection_analysis": results  # Using same results for both for now
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error querying PDFs: {str(e)}")

@app.get("/project-cache/{project_name}")
async def get_project_cache(project_name: str):
    """Return project metadata if persisted (without loading into memory)."""
    meta = load_project_meta(project_name)
    if not meta:
        return {"exists": False}
    chunks = load_project_chunks(project_name)
    return {
        "exists": True,
        "project_name": project_name,
        "pdf_files": [f.get("name") for f in meta.get("files", [])],
        "file_count": len(meta.get("files", [])),
        "chunk_count": len(chunks),
        "updated_at": meta.get("updated_at"),
        "domain": meta.get("domain", "general")
    }

@app.get("/export-project-cache/{project_name}")
async def export_project_cache(project_name: str):
    """
    Export project cache including embeddings, chunks, meta, and prompt cache.
    This allows saving the full state to a .genhat file for later import without recomputation.
    """
    try:
        safe_name = _safe_project_name(project_name)
        meta = load_project_meta(safe_name)
        if not meta:
            raise HTTPException(status_code=404, detail="Project not found")
        
        chunks = load_project_chunks(safe_name)
        
        # Load embeddings if available
        embeddings_data = None
        loaded = load_embeddings(BASE_DATA_DIR, safe_name)
        if loaded:
            chunk_ids, emb_array, model_name = loaded
            # Convert numpy array to list for JSON serialization
            embeddings_data = {
                "chunk_ids": chunk_ids,
                "embeddings": emb_array.tolist(),
                "model_name": model_name
            }
            logger.info(f"📦 Exporting {len(chunk_ids)} embeddings for project '{safe_name}'")
        
        # Get relevant prompt cache entries for this project
        prompt_cache_entries = []
        for prompt_hash, entry in prompt_cache.cache_data.items():
            context = entry.get('context', {})
            # Include entries that belong to this project
            if context.get('project_name') == safe_name or context.get('project') == safe_name:
                prompt_cache_entries.append({
                    'hash': prompt_hash,
                    'prompt': entry.get('prompt', ''),
                    'response': entry.get('response', ''),
                    'context': context,
                    'metadata': entry.get('metadata', {}),
                    'created_at': entry.get('created_at', '')
                })
        
        logger.info(f"📦 Exporting {len(prompt_cache_entries)} cached prompts for project '{safe_name}'")
        
        return {
            "project_name": safe_name,
            "meta": meta,
            "chunks": chunks,
            "embeddings": embeddings_data,
            "prompt_cache": prompt_cache_entries,
            "export_timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error exporting project cache: {e}")
        raise HTTPException(status_code=500, detail=f"Error exporting project cache: {e}")


class ImportProjectCacheRequest(BaseModel):
    project_name: str
    meta: Dict[str, Any]
    chunks: List[Dict[str, Any]]
    embeddings: Optional[Dict[str, Any]] = None
    prompt_cache: Optional[List[Dict[str, Any]]] = None


@app.post("/import-project-cache")
async def import_project_cache(request: ImportProjectCacheRequest):
    """
    Import project cache including embeddings, chunks, meta, and prompt cache.
    This restores the full state from a .genhat file without requiring recomputation.
    """
    try:
        safe_name = _safe_project_name(request.project_name)
        
        # Save project state (meta + chunks)
        save_project_state(safe_name, request.meta, request.chunks)
        logger.info(f"📥 Imported meta and {len(request.chunks)} chunks for project '{safe_name}'")
        
        # Restore embeddings if provided
        if request.embeddings:
            try:
                chunk_ids = request.embeddings.get("chunk_ids", [])
                embeddings_list = request.embeddings.get("embeddings", [])
                model_name = request.embeddings.get("model_name", "all-MiniLM-L12-v2")
                
                if chunk_ids and embeddings_list:
                    # Convert list back to numpy array
                    emb_array = np.array(embeddings_list, dtype=np.float32)
                    save_embeddings(BASE_DATA_DIR, safe_name, chunk_ids, emb_array, model_name)
                    logger.info(f"📥 Imported {len(chunk_ids)} embeddings for project '{safe_name}'")
            except Exception as e:
                logger.warning(f"⚠️ Failed to import embeddings: {e}")
        
        # Restore prompt cache entries if provided
        if request.prompt_cache:
            try:
                for entry in request.prompt_cache:
                    prompt_hash = entry.get('hash')
                    if prompt_hash:
                        prompt_cache.cache_data[prompt_hash] = {
                            'prompt': entry.get('prompt', ''),
                            'response': entry.get('response', ''),
                            'context': entry.get('context', {}),
                            'metadata': entry.get('metadata', {}),
                            'created_at': entry.get('created_at', datetime.now().isoformat()),
                            'access_count': 0,
                            'last_accessed': None
                        }
                prompt_cache._save_cache()
                logger.info(f"📥 Imported {len(request.prompt_cache)} prompt cache entries for project '{safe_name}'")
            except Exception as e:
                logger.warning(f"⚠️ Failed to import prompt cache: {e}")
        
        # Build retriever and store in pdf_cache for immediate use
        cache_key = str(uuid.uuid4())
        detected_domain = request.meta.get("domain", "general")
        
        try:
            # Try to use imported embeddings
            loaded = load_embeddings(BASE_DATA_DIR, safe_name)
            if loaded:
                chunk_ids_loaded, emb_array, model_name = loaded
                id_map = {c.get('chunk_id'): c for c in request.chunks if c.get('chunk_id')}
                ordered_chunks = [id_map[cid] for cid in chunk_ids_loaded if cid in id_map]
                if len(ordered_chunks) == emb_array.shape[0]:
                    retriever = build_hybrid_index(
                        ordered_chunks, 
                        domain=detected_domain, 
                        embedding_model=model_name, 
                        precomputed_embeddings=emb_array
                    )
                    logger.info(f"✅ Built retriever using imported embeddings for '{safe_name}'")
                else:
                    retriever = build_hybrid_index(request.chunks, domain=detected_domain)
                    logger.info(f"⚠️ Embedding count mismatch, rebuilt index for '{safe_name}'")
            else:
                retriever = build_hybrid_index(request.chunks, domain=detected_domain)
                logger.info(f"ℹ️ No embeddings found, built fresh index for '{safe_name}'")
        except Exception as e:
            logger.warning(f"⚠️ Failed to build retriever: {e}")
            retriever = None
        
        pdf_cache[cache_key] = {
            "retriever": retriever,
            "chunks": request.chunks,
            "domain": detected_domain,
            "pdf_files": [f.get("name") for f in request.meta.get("files", [])],
            "project_name": safe_name,
            "imported": True
        }
        
        return {
            "cache_key": cache_key,
            "project_name": safe_name,
            "message": "Project cache imported successfully",
            "chunk_count": len(request.chunks),
            "embeddings_restored": request.embeddings is not None,
            "prompt_cache_restored": len(request.prompt_cache) if request.prompt_cache else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error importing project cache: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error importing project cache: {e}")


@app.get("/cache-status/{cache_key}")
async def get_cache_status(cache_key: str):
    """
    Check if PDF cache is ready
    """
    if cache_key in pdf_cache and 'retriever' in pdf_cache[cache_key]:
        cached_data = pdf_cache[cache_key]
        return {
            "ready": True,
            "chunk_count": len(cached_data["chunks"]),
            "pdf_files": cached_data["pdf_files"],
            "domain": cached_data["domain"],
            "project_name": cached_data.get("project_name")
        }
    elif cache_key in pdf_cache:
        entry = pdf_cache[cache_key]
        response = {"ready": False, "project_name": entry.get("project_name")}
        
        # Include progress information if available
        if "file_progress" in entry:
            response["file_progress"] = entry["file_progress"]
            response["processing"] = entry.get("processing", False)
        
        return response
    else:
        return {"ready": False}

@app.post("/analyze-chunks-with-gemini")
async def analyze_chunks_with_gemini(
    cache_key: str = Form(...),
    persona: str = Form(...),
    task: str = Form(...),
    k: int = Form(default=5),
    gemini_api_key: str = os.getenv("VITE_GEMINI_API_KEY"),
    analysis_prompt: str = Form(default="Analyze the combined document sections and provide: (1) Key Insights, (2) Actionable Recommendations, (3) 'Did you know?' concise interesting facts grounded ONLY in the provided text, (4) Potential Contradictions / Inconsistencies across the sections with source references (document + page), (5) Cross-connections relevant to the persona & task."),
    max_chunks_to_analyze: int = Form(default=5),
    gemini_model: str = Form(default=GEMINI_DEFAULT_MODEL)
):
    """
    Query cached PDFs, get top chunks, and analyze them with Gemini AI.
    Modified: combine the top 5 (or fewer) chunks into a SINGLE Gemini API call instead of per-chunk calls.
    """
    try:
        if cache_key not in pdf_cache:
            raise HTTPException(status_code=404, detail="Cache key not found. Please upload PDFs first.")

        cached_data = pdf_cache[cache_key]
        retriever = cached_data["retriever"]
        chunks = cached_data["chunks"]

        print(f"🔍 Querying with persona: {persona}, task: {task}")
        print(f"📊 Found {len(chunks)} chunks in cache")

        query = f"{persona} {task}"
        print(f"🔍 Searching with query: '{query}'")
        try:
            top_chunks = search_top_k_hybrid(retriever, query, persona=persona, task=task, k=k)
            print(f"✅ Found {len(top_chunks)} top chunks")
        except Exception as search_error:
            print(f"❌ Search error: {str(search_error)}")
            raise HTTPException(status_code=500, detail=f"Search error: {str(search_error)}")

        # Select up to 5 (or user-limited) chunks to aggregate
        use_n = min(5, max_chunks_to_analyze, len(top_chunks))
        combined = top_chunks[:use_n]

        if not combined:
            return {
                "metadata": {
                    "input_documents": cached_data["pdf_files"],
                    "persona": persona,
                    "job_to_be_done": task,
                    "domain": cached_data["domain"],
                    "total_chunks_found": 0,
                    "chunks_analyzed": 0,
                    "gemini_model": gemini_model,
                    "project_name": cached_data.get("project_name")
                },
                "retrieval_results": [],
                "gemini_analysis": [],
                "summary": {"top_insights": []},
                "insight_id": uuid.uuid4().hex
            }

        # Build aggregated contextual prompt
        sections_blob_parts = []
        for idx, ch in enumerate(combined, start=1):
            sections_blob_parts.append(
                f"Section {idx}:\nDocument: {ch.get('pdf_name','Unknown')}\nHeading: {ch.get('heading', NO_HEADING)}\nPage: {ch.get('page_number',1)}\nContent:\n{ch.get('content', ch.get('text',''))}\n---"
            )
        sections_blob = "\n".join(sections_blob_parts)

        contextual_prompt = f"""
You are an expert analyst system.
Persona: {persona}
User Task: {task}
Domain: {cached_data['domain']}

You will analyze the following aggregated document sections (each clearly delimited).

STRICT INSTRUCTIONS:
- Answer the user's task/question directly based on the provided sections.
- Use some external knowledge unless it is trivially common-sense.
- Cite the involved Section numbers and their document + page when relevant.
- Provide outputs in markdown format.

AGGREGATED SECTIONS START
{sections_blob}
AGGREGATED SECTIONS END
"""
        
        # Calculate chunk hashes for cache verification
        chunk_hashes = [ch.get('chunk_hash') or hash_bytes(ch.get('content', ch.get('text', '')).encode('utf-8')) for ch in combined]
        
        # Check cache
        project_name = cached_data.get("project_name", "project")
        cache_context = {
            "project_name": project_name,
            "persona": persona,
            "task": task,
            "model": gemini_model,
            "chunk_hashes": chunk_hashes
        }
        
        # Use user query + analysis prompt as the key, not the full contextual prompt
        # This allows semantic matching on the intent while context verifies the content
        user_query = f"{persona} {task}. {analysis_prompt}"
        
        cached_entry = await asyncio.to_thread(prompt_cache.get, user_query, cache_context)
        
        if cached_entry:
            print(f"✅ Using cached Gemini response (similarity: {cached_entry.get('similarity_score', 1.0):.2%})")
            gemini_text = cached_entry['response']
        else:
            print(f"🤖 Sending aggregated prompt with {use_n} sections to Gemini (single call)...")
            gemini_text = await call_gemini_api(
                prompt=contextual_prompt,
                api_key=os.getenv("VITE_GEMINI_API_KEY"),
                model=gemini_model
            )
            
            # Cache the response
            if not gemini_text.startswith("[Gemini"):
                await asyncio.to_thread(
                    prompt_cache.set, 
                    user_query, 
                    gemini_text, 
                    cache_context,
                    {"chunk_count": use_n}
                )

        # Single result structure
        insight_id = uuid.uuid4().hex
        gemini_results = [
            {
                "chunk_index": 0,
                "combined": True,
                "included_chunk_count": use_n,
                "included_sections": [
                    {
                        "index": i,
                        "document": ch.get('pdf_name','Unknown'),
                        "section_title": ch.get('heading', NO_HEADING),
                        "page_number": ch.get('page_number', 1),
                        "hybrid_score": ch.get('hybrid_score', 0),
                        "bm25_score": ch.get('bm25_score', 0),
                        "embedding_score": ch.get('embedding_score', 0),
                        "chunk_id": ch.get('chunk_id'),
                        "chunk_hash": ch.get('chunk_hash')
                    } for i, ch in enumerate(combined)
                ],
                "gemini_analysis": gemini_text,
                "analysis_timestamp": asyncio.get_event_loop().time()
            }
        ]

        print(f"✅ Gemini analysis complete. Processed {use_n} chunks in single call")
        # Persist analysis with insight_id
        project_name = cached_data.get("project_name", "project")
        insight_dir = _insight_dir(project_name, insight_id)
        try:
            insight_dir.mkdir(parents=True, exist_ok=True)
            import aiofiles
            async with aiofiles.open(insight_dir/"analysis.json", "w", encoding="utf-8") as f:
                # Prepare summary top insights cleanly
                summary_top_insights: list[str] = []
                if isinstance(gemini_text, str):
                    truncated = gemini_text
                    summary_top_insights = [truncated]
                await f.write(json.dumps({
                    "metadata": {
                        "input_documents": cached_data["pdf_files"],
                        "persona": persona,
                        "job_to_be_done": task,
                        "domain": cached_data["domain"],
                        "total_chunks_found": len(top_chunks),
                        "chunks_analyzed": use_n,
                        "gemini_model": gemini_model,
                        "project_name": project_name
                    },
                    "retrieval_results": [
                        {
                            "document": ch.get('pdf_name', 'Unknown'),
                            "section_title": ch.get('heading', NO_HEADING),
                            "content": ch.get('content', ch.get('text', NO_CONTENT)),
                            "page_number": ch.get('page_number', 1),
                            "hybrid_score": ch.get('hybrid_score', 0),
                            "bm25_score": ch.get('bm25_score', 0),
                            "embedding_score": ch.get('embedding_score', 0),
                            "chunk_id": ch.get('chunk_id'),
                            "chunk_hash": ch.get('chunk_hash')
                        }
                        for ch in top_chunks
                    ],
                    "gemini_analysis": gemini_results,
                    "summary": {
                        "top_insights": summary_top_insights
                    },
                    "insight_id": insight_id
                }, indent=2))
        except Exception as persist_err:
            print(f"⚠️ Failed to persist insight {insight_id}: {persist_err}")

        # Prepare response summary insights
        response_top_insights: list[str] = []
        if isinstance(gemini_text, str):
            truncated_resp = gemini_text
            response_top_insights = [truncated_resp]

        return {
            "metadata": {
                "input_documents": cached_data["pdf_files"],
                "persona": persona,
                "job_to_be_done": task,
                "domain": cached_data["domain"],
                "total_chunks_found": len(top_chunks),
                "chunks_analyzed": use_n,
                "gemini_model": gemini_model,
                "project_name": project_name
            },
            "retrieval_results": [
                {
                    "document": ch.get('pdf_name', 'Unknown'),
                    "section_title": ch.get('heading', NO_HEADING),
                    "content": ch.get('content', ch.get('text', NO_CONTENT)),
                    "page_number": ch.get('page_number', 1),
                    "hybrid_score": ch.get('hybrid_score', 0),
                    "bm25_score": ch.get('bm25_score', 0),
                    "embedding_score": ch.get('embedding_score', 0),
                    "chunk_id": ch.get('chunk_id'),
                    "chunk_hash": ch.get('chunk_hash')
                }
                for ch in top_chunks
            ],
            "gemini_analysis": gemini_results,
            "summary": {
                "top_insights": response_top_insights
            },
            "insight_id": insight_id
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error analyzing chunks with Gemini: {str(e)}")


async def call_gemini_api(prompt: str, api_key: str, model: str = "gemini-2.0-flash-exp") -> str:
    """Call the Gemini API to analyze text. Falls back gracefully if httpx is missing."""
    # Dynamic import so requirement is optional
    try:
        import httpx  # type: ignore
        has_httpx = True
    except ImportError:  # pragma: no cover
        httpx = None     # type: ignore
        has_httpx = False

    if not has_httpx:
        # Return a sentinel string instead of raising so callers can continue
        return "[Gemini unavailable: 'httpx' not installed on server]"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:  # type: ignore
            response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
            if not response.is_success:
                error_text = await response.aread()
                return f"[Gemini API error {response.status_code}: {error_text.decode(errors='ignore')[:300]}]"
            data = response.json()
    except Exception as e:  # Network / timeout / other
        return f"[Gemini request failed: {e}]"

    try:
        candidates = data.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            if parts and isinstance(parts, list):
                text = parts[0].get("text")
                if isinstance(text, str) and text.strip():
                    return text
        return "[No analysis generated by Gemini]"
    except Exception as e:
        return f"[Gemini parse error: {e}]"


# --- Mindmap JSON Generation Endpoint ---

class MindmapRequest(BaseModel):
    cache_key: str
    prompt: str
    persona: Optional[str] = "General User"
    k: int = 5
    gemini_model: Optional[str] = GEMINI_DEFAULT_MODEL


@app.post("/generate-mindmap")
async def generate_mindmap(request: MindmapRequest):
    """
    Generate a hierarchical mindmap JSON structure from document analysis.
    Returns a tree structure suitable for React Flow visualization.
    """
    try:
        if request.cache_key not in pdf_cache:
            raise HTTPException(status_code=404, detail="Cache key not found. Please upload PDFs first.")
        
        cached_data = pdf_cache[request.cache_key]
        if "retriever" not in cached_data:
            raise HTTPException(status_code=400, detail="Cache not ready. Please wait for processing to complete.")
        
        retriever = cached_data["retriever"]
        chunks = cached_data["chunks"]
        
        logger.info(f"🧠 Generating mindmap for prompt: {request.prompt}")
        
        # Retrieve relevant chunks
        query = f"{request.persona} {request.prompt}"
        try:
            top_chunks = search_top_k_hybrid(retriever, query, persona=request.persona, task=request.prompt, k=request.k)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")
        
        if not top_chunks:
            raise HTTPException(status_code=400, detail="No relevant sections found in documents")
        
        # Build context from chunks
        sections_parts = []
        for idx, ch in enumerate(top_chunks, start=1):
            sections_parts.append(
                f"Section {idx}:\nDocument: {ch.get('pdf_name','Unknown')}\nHeading: {ch.get('heading', 'No heading')}\nContent:\n{ch.get('content', ch.get('text',''))}\n---"
            )
        sections_blob = "\n".join(sections_parts)
        
        # Mindmap generation prompt
        mindmap_prompt = f"""You are an expert at creating hierarchical mind maps from document content.

Based on the following document sections, create a comprehensive mind map structure for the topic: "{request.prompt}"

DOCUMENT SECTIONS:
{sections_blob}

INSTRUCTIONS:
1. Create a hierarchical JSON structure representing a mind map
2. The root node should be the main topic/concept
3. Create 3-6 main branches representing key themes or categories
4. Each branch can have 2-4 sub-nodes with more specific details
5. Keep labels concise but descriptive (5-15 words max per label)
6. Ground all content in the provided document sections
7. Organize information logically from general to specific

OUTPUT FORMAT (strict JSON only, no markdown, no explanation):
{{
  "id": "root",
  "label": "Main Topic Title",
  "collapsed": false,
  "children": [
    {{
      "id": "unique-id-1",
      "label": "Branch 1 Label",
      "collapsed": false,
      "children": [
        {{
          "id": "unique-id-1-1",
          "label": "Sub-detail 1",
          "collapsed": false,
          "children": []
        }}
      ]
    }}
  ]
}}

IMPORTANT:
- Return ONLY valid JSON, no markdown code blocks, no explanation text
- Each node must have: id (unique string), label (string), collapsed (boolean), children (array)
- Generate unique IDs like "node-1", "node-1-1", "node-2", etc.
- Maximum depth: 3 levels (root -> branch -> detail)

Generate the mind map JSON now:"""

        # Call Gemini API
        gemini_response = await call_gemini_api(
            mindmap_prompt,
            os.getenv("VITE_GEMINI_API_KEY"),
            model=request.gemini_model or GEMINI_DEFAULT_MODEL
        )
        
        if gemini_response.startswith("[Gemini"):
            raise HTTPException(status_code=500, detail=f"Gemini API error: {gemini_response}")
        
        # Parse JSON response
        try:
            # Clean up response - remove markdown code blocks if present
            cleaned_response = gemini_response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            mindmap_data = json.loads(cleaned_response)
            
            # Validate structure
            if not isinstance(mindmap_data, dict):
                raise ValueError("Response is not a JSON object")
            if "id" not in mindmap_data or "label" not in mindmap_data:
                raise ValueError("Missing required fields: id, label")
            if "children" not in mindmap_data:
                mindmap_data["children"] = []
            if "collapsed" not in mindmap_data:
                mindmap_data["collapsed"] = False
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse mindmap JSON: {e}")
            logger.error(f"Raw response: {gemini_response[:500]}")
            # Return a fallback structure
            mindmap_data = {
                "id": "root",
                "label": request.prompt,
                "collapsed": False,
                "children": [
                    {
                        "id": "error-node",
                        "label": "Failed to generate detailed mindmap. Try rephrasing your prompt.",
                        "collapsed": False,
                        "children": []
                    }
                ]
            }
        
        logger.info(f"✅ Mindmap generated with {len(mindmap_data.get('children', []))} main branches")
        
        return {
            "success": True,
            "mindmap": mindmap_data,
            "prompt": request.prompt,
            "chunks_used": len(top_chunks),
            "project_name": cached_data.get("project_name")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating mindmap: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating mindmap: {e}")


def _build_multi_speaker_ssml(script_text: str, voice_a: str, voice_b: str, name_a: str, name_b: str, lang: str = "en-US") -> str:
    """Build SSML for two-speaker podcast dialogue.
    
    Expects script in format:
    Host A: text
    Host B: text
    Host A: text
    etc.
    
    Falls back to single-voice if format is not detected.
    """
    lines = script_text.strip().split('\n')
    ssml_parts = [f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang}">']
    
    # Track if we found any proper dialogue format
    found_dialogue = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Skip title lines
        if line.lower().startswith('title:'):
            continue
        
        # Detect speaker and extract dialogue
        if line.startswith(f'{name_a}:') or line.startswith(f'**{name_a}:**'):
            text = line.replace(f'{name_a}:', '').replace(f'**{name_a}:**', '').strip()
            if text:  # Only add if there's actual content
                safe_text = html.escape(text)
                # Break must be INSIDE the voice tag for multi-voice SSML
                ssml_parts.append(f'  <voice name="{voice_a}">{safe_text}<break time="500ms"/></voice>')
                found_dialogue = True
        elif line.startswith(f'{name_b}:') or line.startswith(f'**{name_b}:**'):
            text = line.replace(f'{name_b}:', '').replace(f'**{name_b}:**', '').strip()
            if text:  # Only add if there's actual content
                safe_text = html.escape(text)
                # Break must be INSIDE the voice tag for multi-voice SSML
                ssml_parts.append(f'  <voice name="{voice_b}">{safe_text}<break time="500ms"/></voice>')
                found_dialogue = True
    
    # If no dialogue format was found, fallback to single voice
    if not found_dialogue:
        print("⚠️ No dialogue format detected, falling back to single-voice SSML")
        ssml_parts = [f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang}">']
        safe_text = html.escape(script_text)
        ssml_parts.append(f'  <voice name="{voice_a}">{safe_text}</voice>')
    
    ssml_parts.append('</speak>')
    return '\n'.join(ssml_parts)

# --- Unified podcast creation from prompt (retrieval + analysis + script + TTS) ---
class PodcastFromPromptRequest(BaseModel):
    project_name: str
    prompt: str
    k: int = 5
    gemini_model: Optional[str] = GEMINI_DEFAULT_MODEL
    voice: Optional[str] = "en-US-AvaMultilingualNeural"
    audio_format: Optional[str] = "mp3"
    persona: Optional[str] = "Podcast Host"
    analysis_style: Optional[str] = "Provide: (1) Key Insights, (2) Actionable Recommendations, (3) Interesting Facts, (4) Potential Contradictions with sources, (5) Cross-connections."
    regenerate: Optional[bool] = False

def get_voices():
    voices = { "en-US-Andrew:DragonHDLatestNeural" : "Andy",
                    "en-US-Andrew2:DragonHDLatestNeural" : "Benjamin",
                    "en-US-Aria:DragonHDLatestNeural" : "Sansa",
                    "en-US-Ava:DragonHDLatestNeural" : "Eva", 
                    "en-US-Brian:DragonHDLatestNeural" : "Brian", 
                    "en-US-Davis:DragonHDLatestNeural" : "Dave",
                    "en-US-Emma:DragonHDLatestNeural" : "Amy", 
                    "en-US-Emma2:DragonHDLatestNeural" : "Maria", 
                    "en-US-Jenny:DragonHDLatestNeural" : "Jenny",
                    "en-US-Steffan:DragonHDLatestNeural" : "Stevie"
                    }

    voice_a = random.choice(list(voices.keys()))
    name_a = voices[voice_a]
    new_voices = [v for v in voices.keys() if v != voice_a]
    voice_b = random.choice(new_voices)
    name_b = voices[voice_b]

    return {voice_a: name_a, voice_b: name_b}

@app.post("/podcast-from-prompt")
async def podcast_from_prompt(req: PodcastFromPromptRequest):
    """End-to-end podcast generation from a single prompt.

    Steps:
        1. Load project chunks + (optional) persisted embeddings.
        2. Perform hybrid retrieval for prompt.
        3. Aggregate top-k sections into one Gemini analysis call.
        4. Generate podcast script (second Gemini call) using analysis + retrieval.
        5. Synthesize audio via Azure TTS (best-effort).
        6. Persist insight (analysis + script + audio) under new insight_id.
    """
    try:
        voices = get_voices()
        safe_project = _safe_project_name(req.project_name)
        meta = load_project_meta(safe_project)
        if not meta:
            raise HTTPException(status_code=404, detail="Project not found")
        chunks = load_project_chunks(safe_project)
        if not chunks:
            raise HTTPException(status_code=400, detail="Project has no chunks. Upload PDFs first.")

        # Attempt to load persisted embeddings for faster retriever build
        loaded = load_embeddings(BASE_DATA_DIR, safe_project)
        pre_embs = None
        emb_model_name = "all-MiniLM-L12-v2"
        if loaded:
            loaded_ids, emb_array, model_name = loaded
            id_map = {c.get('chunk_id'): c for c in chunks if c.get('chunk_id')}
            ordered_chunks = [id_map[cid] for cid in loaded_ids if cid in id_map]
            if len(ordered_chunks) == emb_array.shape[0]:
                chunks = ordered_chunks
                pre_embs = emb_array
                emb_model_name = model_name
                print(f"🔄 Reused persisted embeddings for podcast flow ({emb_array.shape[0]} vectors)")
            else:
                print("⚠️ Embedding mismatch; falling back to recompute.")

        detected_domain = meta.get("domain", "general")
        retriever = build_hybrid_index(chunks, domain=detected_domain, embedding_model=emb_model_name, precomputed_embeddings=pre_embs)

        # Retrieval
        query = f"{req.persona} {req.prompt}".strip()
        try:
            top_chunks = search_top_k_hybrid(retriever, query, persona=req.persona, task=req.prompt, k=req.k)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")
        if not top_chunks:
            raise HTTPException(status_code=400, detail="No relevant sections retrieved")

        use_n = min(req.k, len(top_chunks))
        combined = top_chunks[:use_n]

        sections_blob_parts = []
        for idx, ch in enumerate(combined, start=1):
            sections_blob_parts.append(
                f"Section {idx}:\nDocument: {ch.get('pdf_name','Unknown')}\nHeading: {ch.get('heading', NO_HEADING)}\nPage: {ch.get('page_number',1)}\nContent:\n{ch.get('content', ch.get('text',''))}\n---"
            )
        sections_blob = "\n".join(sections_blob_parts)

        analysis_prompt = f"""
You are a domain expert analyst.
Persona: {req.persona}
User Prompt: {req.prompt}
Domain: {detected_domain}
{req.analysis_style}
Strict: Ground ALL outputs ONLY in provided sections; cite Section number + (document p.page) when referencing.

SECTIONS START
{sections_blob}
SECTIONS END
"""

        # Cache context for analysis
        chunk_hashes = [ch.get('chunk_hash') or hash_bytes(ch.get('content', ch.get('text','')).encode('utf-8')) for ch in combined]
        analysis_cache_key = f"ANALYSIS:{req.prompt}"  # semantic intent key
        analysis_cache_context = {
            "type": "podcast_analysis",
            "project": safe_project,
            "model": req.gemini_model,
            "chunk_hashes": chunk_hashes
        }
        cached_analysis = await asyncio.to_thread(prompt_cache.get, analysis_cache_key, analysis_cache_context)
        if cached_analysis and not req.regenerate:
            analysis_text = cached_analysis['response']
        else:
            analysis_text = await call_gemini_api(analysis_prompt, os.getenv("VITE_GEMINI_API_KEY"), model=req.gemini_model or GEMINI_DEFAULT_MODEL)
            if not analysis_text.startswith("[Gemini"):
                await asyncio.to_thread(prompt_cache.set, analysis_cache_key, analysis_text, analysis_cache_context, {"chunk_count": use_n})

        # Extract voice keys and names for script generation
        voice_keys = list(voices.keys())
        voice_a = voice_keys[0]
        voice_b = voice_keys[1]
        name_a = voices[voice_a]
        name_b = voices[voice_b]

        # Script generation prompt - TWO SPEAKER CONVERSATION (strict, 3-4 min length)
        script_prompt = f"""
You are writing a conversational podcast dialogue between TWO hosts: {name_a} and {name_b}.

Prompt: {req.prompt}
Domain: {detected_domain}

Analysis Summary:
{analysis_text[:12000]}
---

Task: Create a natural, engaging, IN-DEPTH dialogue strictly between the two hosts named above.

TARGET LENGTH: 3-4 MINUTES OF SPOKEN AUDIO (approximately 500-650 words total, 25-35 speaker turns).

The conversation should:
- Have {name_a} introduce the topic warmly and guide the discussion with thoughtful questions
- Have {name_b} provide detailed insights, explanations, and examples
- Build on each other's points naturally with follow-up questions and elaborations
- Reference Section numbers casually when discussing findings (e.g., "As we saw in Section 2...")
- Include an engaging introduction, thorough exploration of 3-4 key points, and a memorable conclusion
- Each speaker turn should be 2-4 sentences (15-25 words per turn on average)
- Produce between 25 and 35 total speaker turns (lines)
- Include smooth transitions between topics
- End with both hosts summarizing 2-3 key takeaways and a friendly sign-off

STRUCTURE GUIDE:
1. Opening (3-4 turns): {name_a} welcomes listeners and introduces the topic; {name_b} shares initial excitement
2. Main Discussion (18-25 turns): Deep dive into 3-4 key insights from the analysis, with questions, examples, and elaboration
3. Closing (4-6 turns): Recap key takeaways, share final thoughts, thank listeners

CRITICAL FORMATTING RULES (MUST FOLLOW EXACTLY):
1. EVERY line must start with EXACTLY "{name_a}: " or "{name_b}: " (including the trailing space). Use these exact names only.
2. Use NO other speaker names, narrative lines, titles, headers, or descriptions — only dialogue lines prefixed with the two host names.
3. Both {name_a} and {name_b} must appear at least once in the output.
4. The first line MUST start with "{name_a}:"
5. Produce 25-35 total lines (each line is a single speaker turn). Do NOT produce fewer.
6. Do NOT use markdown, bold, italics, or quotation marks. Do NOT annotate with parentheses or stage directions.
7. Start immediately with dialogue — no preamble, no explanation.
8. If you cannot follow these rules exactly, output the single token: [FORMAT_ERROR]

CORRECT FORMAT EXAMPLE:
{name_a}: Welcome back to the show! Today we're diving into a fascinating topic that's been on everyone's mind lately. I'm really excited to explore this with you.
{name_b}: Absolutely! When I first looked at the analysis, Section 2 immediately caught my attention because it reveals some surprising patterns we don't usually consider.
{name_a}: That's interesting. Can you break down what makes those patterns so unexpected?
{name_b}: Sure! Essentially, the data shows that the conventional approach we've been using actually misses about 40 percent of the key factors. Section 3 elaborates on this with concrete examples.
"""

        # Version tag invalidates old cached short scripts when prompt template changes
        SCRIPT_PROMPT_VERSION = "v2_long_3to4min"
        script_cache_key = f"SCRIPT:{SCRIPT_PROMPT_VERSION}:{req.prompt}"  # semantic intent key for script
        script_cache_context = {
            "type": "podcast_script",
            "project": safe_project,
            "model": req.gemini_model,
            "analysis_hash": hash_bytes(analysis_text.encode('utf-8')),
            "prompt_version": SCRIPT_PROMPT_VERSION
        }
        cached_script = await asyncio.to_thread(prompt_cache.get, script_cache_key, script_cache_context)
        if cached_script and not req.regenerate:
            script_text = cached_script['response']
        else:
            script_text = await call_gemini_api(script_prompt, os.getenv("VITE_GEMINI_API_KEY"), model=req.gemini_model or GEMINI_DEFAULT_MODEL)
            if not script_text.startswith("[Gemini"):
                await asyncio.to_thread(prompt_cache.set, script_cache_key, script_text, script_cache_context)

        # Persist insight directory
        insight_id = uuid.uuid4().hex
        title = req.prompt[:50].strip()
        if len(req.prompt) > 50:
            title += "..."
        insight_dir = _insight_dir(safe_project, insight_id)
        insight_dir.mkdir(parents=True, exist_ok=True)
        try:
            import aiofiles
            async with aiofiles.open(insight_dir/"analysis.json", "w", encoding="utf-8") as f:
                await f.write(json.dumps({
                    "metadata": {
                        "title": title,
                        "input_documents": [f.get("name") for f in meta.get("files", [])],
                        "persona": req.persona,
                        "job_to_be_done": req.prompt,
                        "domain": detected_domain,
                        "gemini_model": req.gemini_model,
                        "project_name": safe_project,
                        "chunks_analyzed": use_n
                    },
                    "retrieval_results": [
                        {
                            "document": ch.get('pdf_name','Unknown'),
                            "section_title": ch.get('heading', NO_HEADING),
                            "content": ch.get('content', ch.get('text', NO_CONTENT)),
                            "page_number": ch.get('page_number',1),
                            "hybrid_score": ch.get('hybrid_score',0),
                            "bm25_score": ch.get('bm25_score',0),
                            "embedding_score": ch.get('embedding_score',0),
                            "chunk_id": ch.get('chunk_id'),
                            "chunk_hash": ch.get('chunk_hash')
                        } for ch in combined
                    ],
                    "analysis_text": analysis_text,
                    "script": script_text,
                    "insight_id": insight_id
                }, indent=2))
            (insight_dir/"script.txt").write_text(script_text, encoding='utf-8')
            try:
                # Save Gemini analysis output and the strict two-person script separately
                (insight_dir/"gemini_analysis.txt").write_text(analysis_text or "", encoding='utf-8')
                (insight_dir/"two_person_script.txt").write_text(script_text or "", encoding='utf-8')
            except Exception as save_txt_err:
                print(f"⚠️ Failed to write additional text files for podcast insight {insight_id}: {save_txt_err}")
        except Exception as persist_err:
            print(f"⚠️ Failed to persist podcast insight {insight_id}: {persist_err}")

        # Print the generated script to console for debugging and review
        try:
            print("----- PODCAST SCRIPT START -----")
            print(script_text)
            print("----- PODCAST SCRIPT END -----")
        except Exception as _:
            pass

        # TTS synthesis with TWO VOICES best-effort
        audio_url = None
        try:
            import azure.cognitiveservices.speech as speechsdk  # type: ignore
            speech_key = os.getenv("SPEECH_API_KEY")
            speech_region = os.getenv("SPEECH_REGION")
            if speech_key and speech_region and not script_text.startswith('[Gemini'):
                speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
                speech_config.set_speech_synthesis_output_format(
                    speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
                )
            
                voice_keys = list(voices.keys())
                voice_a = voice_keys[0]
                voice_b = voice_keys[1]
                name_a = voices[voice_a]
                name_b = voices[voice_b]
                ssml = _build_multi_speaker_ssml(script_text, voice_a, voice_b, name_a, name_b, "en-US")
                synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: synthesizer.speak_ssml_async(ssml).get())
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    audio_bytes = bytes(result.audio_data or b"")
                    (insight_dir/"podcast.mp3").write_bytes(audio_bytes)
                    audio_url = f"/insight-audio/{safe_project}/{insight_id}.mp3"
                    print(f"✅ Two-speaker podcast audio generated: {len(audio_bytes)} bytes")
                elif result.reason == speechsdk.ResultReason.Canceled:
                    try:
                        # CancellationDetails can sometimes raise when the underlying SDK
                        # returns an unexpected/invalid handle. Be defensive here.
                        cancellation = speechsdk.CancellationDetails(result)
                        reason = getattr(cancellation, 'reason', 'Unknown')
                        details = getattr(cancellation, 'error_details', None)
                        print(f"❌ TTS Canceled: {reason}. Error details: {details}")
                    except Exception as cd_exc:
                        # Fall back to best-effort logging without raising further
                        try:
                            # Some result objects expose an error_details attribute directly
                            details = getattr(result, 'error_details', None)
                        except Exception:
                            details = None
                        print(f"❌ TTS Canceled but CancellationDetails failed: {cd_exc}. Fallback details: {details}")
                else:
                    print(f"⚠️ TTS did not complete for podcast flow, reason: {result.reason}")
            else:
                print("ℹ️ Skipping TTS (missing credentials or script invalid).")
        except Exception as tts_err:
            print(f"⚠️ TTS failed for podcast flow: {tts_err}")
            import traceback
            traceback.print_exc()

        return {
            "insight_id": insight_id,
            "title": title,
            "script": script_text,
            "analysis": analysis_text[:1500],  # trimmed preview
            "audio_url": audio_url,
            "retrieved_chunk_count": use_n,
            "project_name": safe_project,
            "persona": req.persona,
            "prompt": req.prompt,
            "domain": detected_domain
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Podcast generation error: {e}")
@app.get("/insight-audio/{project_name}/{insight_id}.mp3")
async def get_insight_audio(project_name: str, insight_id: str):
    project = _safe_project_name(project_name)
    audio_path = _insight_dir(project, insight_id)/"podcast.mp3"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    # Enable range requests for proper audio playback in browsers
    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache"
        }
    )

@app.get("/projects/{project_name}/insights")
async def list_project_insights(project_name: str):
    """List all saved insights for a project"""
    try:
        project = _safe_project_name(project_name)
        insights_dir = _insights_dir(project)
        if not insights_dir.exists():
            return {"insights": []}
        
        insights = []
        for insight_dir in insights_dir.iterdir():
            if insight_dir.is_dir():
                analysis_file = insight_dir / "analysis.json"
                if analysis_file.exists():
                    try:
                        import aiofiles
                        async with aiofiles.open(analysis_file, 'r', encoding='utf-8') as f:
                            content = await f.read()
                        analysis = json.loads(content)
                        
                        # Check if audio exists
                        audio_path = insight_dir / "podcast.mp3"
                        has_audio = audio_path.exists()
                        
                        # Get script if available
                        script_path = insight_dir / "script.txt"
                        script = ""
                        if script_path.exists():
                            async with aiofiles.open(script_path, 'r', encoding='utf-8') as sf:
                                script = await sf.read()
                        
                        insights.append({
                            "insight_id": insight_dir.name,
                            "metadata": analysis.get("metadata", {}),
                            "summary": analysis.get("summary", {}),
                            "has_audio": has_audio,
                            "script": script,
                            "created_at": analysis_file.stat().st_ctime
                        })
                    except Exception as e:
                        print(f"Error reading insight {insight_dir.name}: {e}")
                        continue
        
        # Sort by creation time (newest first)
        insights.sort(key=lambda x: x["created_at"], reverse=True)
        return {"insights": insights}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing insights: {e}")

@app.get("/projects/{project_name}/insights/{insight_id}")
async def get_project_insight(project_name: str, insight_id: str):
    """Get a specific insight with full analysis data"""
    try:
        project = _safe_project_name(project_name)
        insight_dir = _insight_dir(project, insight_id)
        analysis_file = insight_dir / "analysis.json"
        
        if not analysis_file.exists():
            raise HTTPException(status_code=404, detail="Insight not found")
        
        import aiofiles
        async with aiofiles.open(analysis_file, 'r', encoding='utf-8') as f:
            content = await f.read()
        analysis = json.loads(content)
        
        # Check if audio exists
        audio_path = insight_dir / "podcast.mp3"
        audio_url = f"/insight-audio/{project}/{insight_id}.mp3" if audio_path.exists() else None
        
        # Get script if available
        script_path = insight_dir / "script.txt"
        script = ""
        if script_path.exists():
            async with aiofiles.open(script_path, 'r', encoding='utf-8') as sf:
                script = await sf.read()
        
        return {
            **analysis,
            "audio_url": audio_url,
            "script": script
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting insight: {e}")

@app.delete("/projects/{project_name}/insights/{insight_id}")
async def delete_project_insight(project_name: str, insight_id: str):
    """Delete an insight and all associated files (analysis, audio, script)"""
    try:
        project = _safe_project_name(project_name)
        insight_dir = _insight_dir(project, insight_id)
        
        if not insight_dir.exists():
            raise HTTPException(status_code=404, detail="Insight not found")
        
        # Remove all files in the insight directory
        import shutil
        shutil.rmtree(insight_dir)
        
        return {"message": f"Insight {insight_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting insight: {e}")

# Frontend routes - serve index.html for client-side routing
@app.on_event("startup")
async def startup_event():
    """Log configuration on startup"""
    logger.info("=" * 60)
    logger.info("🎩 GenHat Backend - Configuration")
    logger.info("=" * 60)
    logger.info(f"OS: {platform.system()} {platform.release()}")
    logger.info(f"Python: {sys.version.split()[0]}")
    logger.info(f"Temp Directory: {TEMP_DIR}")
    logger.info(f"Log Directory: {LOG_DIR}")
    logger.info(f"Data Directory: {BASE_DATA_DIR}")
    logger.info(f"Upload Directory: {TEMP_DIR / 'uploads'}")
    logger.info("=" * 60)
    
    # Create necessary directories
    (TEMP_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    logger.info("✅ All directories initialized")

@app.get("/api/info")
async def get_system_info():
    """Get system and configuration information"""
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "python_version": sys.version.split()[0],
        "temp_dir": str(TEMP_DIR),
        "log_dir": str(LOG_DIR),
        "data_dir": str(BASE_DATA_DIR),
        "upload_dir": str(TEMP_DIR / "uploads"),
        "log_file": str(LOG_FILE)
    }

@app.get("/projects")
@app.get("/arena") 
@app.get("/mindmap")
async def frontend_routes():
    """Serve index.html for frontend routes to enable client-side routing"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend not built")

@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    """Return index.html for any unmatched path (enables client-side routing).
    This executes AFTER all explicit API routes; only unknown paths fall through.
    """
    # Skip API routes and static assets
    if full_path.startswith(("api/", "assets/", "static/")):
        raise HTTPException(status_code=404, detail="Not found")
    
    # Serve index.html for all other paths (client-side routing)
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend not built")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)