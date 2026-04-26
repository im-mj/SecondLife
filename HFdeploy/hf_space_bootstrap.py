"""Hugging Face Space startup helper.

The Flask app expects two local dataset folders. In the Space, those folders are
downloaded from a separate Hugging Face Dataset repo before importing app.py,
because app.py starts the pipeline boot thread at import time.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download


BASE_DIR = Path(__file__).resolve().parent
DATASET_REPO = os.environ.get("HF_DATASET_REPO", "MrNoOne07/second-life-data")

DATASET_ZIPS = [
    ("Final Clinical Trails Data.zip", "Final Clinical Trails Data"),
    ("Final Patients Synthea Data.zip", "Final Patients Synthea Data"),
]


def _ensure_dataset(zip_name: str, folder_name: str) -> None:
    folder_path = BASE_DIR / folder_name
    if folder_path.exists() and any(folder_path.iterdir()):
        print(f"[bootstrap] Found {folder_name}.")
        return

    print(f"[bootstrap] Downloading {zip_name} from {DATASET_REPO}...")
    zip_path = hf_hub_download(
        repo_id=DATASET_REPO,
        filename=zip_name,
        repo_type="dataset",
    )

    print(f"[bootstrap] Extracting {zip_name}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(BASE_DIR)

    if not folder_path.exists():
        raise RuntimeError(f"Expected extracted folder not found: {folder_path}")


def main() -> None:
    for zip_name, folder_name in DATASET_ZIPS:
        _ensure_dataset(zip_name, folder_name)

    from app import app

    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
