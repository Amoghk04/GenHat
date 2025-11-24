"""Lightweight per-project embedding persistence.

Stores chunk embeddings and their ordering (chunk_ids) so we can reload
without recomputing when a project is reused.

Format: NumPy .npz file with arrays:
  - embeddings: (N, D) float32
  - chunk_ids: (N,) object (stored as unicode)

Future extensions:
  - Support incremental append without recomputing old chunks
  - Store model metadata / versioning
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np

EMBED_FILENAME = "embeddings.npz"

def _project_emb_path(base_dir: Path, project_name: str) -> Path:
    return base_dir / project_name / EMBED_FILENAME

def save_embeddings(base_dir: Path, project_name: str, chunk_ids: List[str], embeddings: np.ndarray,
                    model_name: str) -> None:
    """Persist embeddings + ordering.

    Args:
        base_dir: Root data directory holding project folders.
        project_name: Safe project name.
        chunk_ids: Ordered list aligned with embeddings rows.
        embeddings: 2D array (N, D).
        model_name: For future metadata; stored inside file.
    """
    path = _project_emb_path(base_dir, project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, embeddings=embeddings.astype(np.float32), chunk_ids=np.array(chunk_ids), model=model_name)

def load_embeddings(base_dir: Path, project_name: str) -> Optional[Tuple[List[str], np.ndarray, str]]:
    """Load embeddings if present.

    Returns:
        (chunk_ids, embeddings_array, model_name) or None if missing/invalid.
    """
    path = _project_emb_path(base_dir, project_name)
    if not path.exists():
        return None
    try:
        data = np.load(path, allow_pickle=True)
        embeddings = data["embeddings"]
        chunk_ids_arr = data["chunk_ids"].tolist()
        model_name = str(data.get("model", "unknown"))
        return chunk_ids_arr, embeddings, model_name
    except Exception:
        return None
