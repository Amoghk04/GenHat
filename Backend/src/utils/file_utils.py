# utils/file_utils.py
from pathlib import Path

def ensure_dir(path: str):
    """Create directory if it does not exist."""
    Path(path).mkdir(parents=True, exist_ok=True)

def load_json(path):
    import json
    with open(path, 'r') as f:
        return json.load(f)

def save_json(data, path):
    import json
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def current_timestamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
