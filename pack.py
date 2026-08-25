#!/usr/bin/env python3
"""Offline packer for INTERNAL_RAG.

Creates a self-contained ZIP that can be installed on an air-gapped machine
(no internet required) including:
  - the full INTERNAL_RAG package (install.py, irag.py, etc.)
  - optional dependencies (sentence-transformers, numpy) as wheels
  - the embeddings model pre-downloaded

Usage (on a machine WITH internet):
  python pack.py --with-embeddings --model all-MiniLM-L6-v2
  -> internal-rag-offline-<version>.zip

Usage on the air-gapped machine (after copying the ZIP):
  unzip internal-rag-offline-*.zip -d internal-rag-offline
  cd internal-rag-offline
  pip install --no-index --find-links wheels/ -r requirements-optional.txt
  python install.py "D:\\path\\to\\project"
  # set IRAG_OFFLINE_MODEL_DIR to the pre-downloaded model path
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "1.6.0"
ROOT = Path(__file__).parent.resolve()


def pip_download_wheels(out_dir: Path, packages: list[str]) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "download", "--dest", str(out_dir),
           "--no-deps", "--only-binary=:all:", *packages]
    print(f"Running: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    if rc:
        print("Wheel download failed; trying with deps...")
        cmd = [sys.executable, "-m", "pip", "download", "--dest", str(out_dir), *packages]
        rc = subprocess.run(cmd).returncode
    return rc


def download_model(model_name: str, out_dir: Path) -> Path | None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("sentence-transformers not installed; skipping model download.")
        print("Install first: pip install sentence-transformers numpy")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / model_name.replace("/", "_")
    print(f"Downloading model: {model_name} -> {model_path}")
    model = SentenceTransformer(model_name)
    model.save(str(model_path))
    print(f"Model saved to: {model_path}")
    return model_path


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Pack INTERNAL_RAG v{VERSION} for offline use.")
    ap.add_argument("--with-embeddings", action="store_true", help="Include sentence-transformers + numpy wheels.")
    ap.add_argument("--model", default="", help="Model to pre-download (overrides profile).")
    ap.add_argument("--profile", default="english-fast", choices=["english-fast", "multilingual"],
                    help="Retrieval profile (default: english-fast).")
    ap.add_argument("--out", default="", help="Output ZIP path (default: internal-rag-offline-<version>.zip).")
    args = ap.parse_args()

    out_zip = Path(args.out) if args.out else ROOT / f"internal-rag-offline-{VERSION}.zip"
    staging = ROOT / ".offline-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # 1. Copy the package
    print("Copying package files...")
    for item in ROOT.rglob("*"):
        rel = item.relative_to(ROOT)
        if any(p in rel.parts for p in (".git", "__pycache__", ".offline-staging", ".venv", "venv", "node_modules")):
            continue
        if any(p.startswith(".venv") for p in rel.parts):
            continue
        if str(rel).startswith("internal-rag-offline-"):
            continue
        dst = staging / rel
        if item.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)

    # 2. Download wheels
    if args.with_embeddings:
        wheels_dir = staging / "wheels"
        print("\nDownloading wheels (sentence-transformers, numpy)...")
        rc = pip_download_wheels(wheels_dir, ["sentence-transformers", "numpy"])
        if rc:
            print("WARNING: some wheels could not be downloaded. The offline pack will use BM25 fallback.")
        else:
            print("Wheels downloaded successfully.")

        # 3. Pre-download model (resolve from profile or explicit --model)
        PROFILE_MODELS = {
            "english-fast": "all-MiniLM-L6-v2",
            "multilingual": "intfloat/multilingual-e5-small",
        }
        model_name = args.model or PROFILE_MODELS.get(args.profile, "all-MiniLM-L6-v2")
        model_dir = staging / "models"
        model_path = download_model(model_name, model_dir)
        if model_path:
            print(f"\nModel pre-downloaded: {model_name} -> {model_path}")
            print(f"Profile: {args.profile}")
            print("On the offline machine, set:")
            print(f'  IRAG_EMBED_MODEL="{model_path}"')
            print(f"  or set retrieval.profile: {args.profile} in .irag.yml")

    # 4. Write offline README
    offline_readme = staging / "OFFLINE-README.txt"
    offline_readme.write_text(f"""INTERNAL_RAG Offline Pack v{VERSION}
=====================================

This ZIP contains everything needed to install INTERNAL_RAG on an air-gapped machine.

Contents:
  - INTERNAL_RAG package (install.py, irag.py, SKILL.md, docs/, etc.)
  - wheels/ (optional: sentence-transformers + numpy, if --with-embeddings was used)
  - models/ (optional: pre-downloaded embeddings model, if --with-embeddings was used)

Installation on the air-gapped machine:
  1. Unzip this archive:
     unzip {out_zip.name} -d internal-rag-offline
  2. cd internal-rag-offline

  3. (Optional) Install embeddings dependencies from local wheels:
     pip install --no-index --find-links wheels/ -r requirements-optional.txt

  4. Install INTERNAL_RAG into your project:
     python install.py "D:\\path\\to\\project"

  5. (Optional) Point to the pre-downloaded model:
     Set environment variable IRAG_EMBED_MODEL to the model path, e.g.:
     set IRAG_EMBED_MODEL=C:\\path\\to\\internal-rag-offline\\models\\all-MiniLM-L6-v2

  6. Verify:
     python .agents\\skills\\internal-rag\\irag.py doctor
     python .agents\\skills\\internal-rag\\irag.py embeddings-info

Without embeddings (zero-dependency mode), INTERNAL_RAG uses BM25+MMR which works
fully offline with no additional packages.
""", encoding="utf-8")

    # 5. Create ZIP
    print(f"\nCreating ZIP: {out_zip}")
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in staging.rglob("*"):
            if item.is_file():
                arcname = item.relative_to(staging)
                zf.write(item, arcname)
    shutil.rmtree(staging)

    size_mb = out_zip.stat().st_size / (1024 * 1024)
    print(f"\nOffline pack created: {out_zip} ({size_mb:.1f} MB)")
    print("Copy this ZIP to the air-gapped machine and follow OFFLINE-README.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())