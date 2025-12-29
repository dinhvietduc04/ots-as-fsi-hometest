#!/usr/bin/env python3
"""
Main orchestrator for OptiSign daily scraper job.
Handles scraping, delta detection, and vector store uploads.
"""

import os
import json
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime

ARTICLES_DIR = "articles"
HASHES_FILE = "log/article_hashes.json"
DELTA_LOG_FILE = "log/delta_log.json"

def get_file_hash(filepath):
    """Calculate SHA256 hash of file content."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def load_hashes():
    """Load previous article hashes from disk."""
    if os.path.exists(HASHES_FILE):
        with open(HASHES_FILE, "r") as f:
            return json.load(f)
    return {}

def save_hashes(hashes):
    """Save current article hashes to disk."""
    os.makedirs(os.path.dirname(HASHES_FILE), exist_ok=True)
    with open(HASHES_FILE, "w") as f:
        json.dump(hashes, f, indent=2)

def detect_delta():
    """
    Detect new and updated articles.
    Returns: (added, updated, skipped, current_hashes)
    """
    old_hashes = load_hashes()
    current_hashes = {}
    added = []
    updated = []
    skipped = []
    
    # Get all markdown files
    md_files = sorted(Path(ARTICLES_DIR).glob("*.md"))
    
    if not md_files:
        print(f"⚠ No articles found in {ARTICLES_DIR}")
        return [], [], [], {}
    
    print(f"\n[DELTA] Detecting changes across {len(md_files)} articles...")
    
    for md_file in md_files:
        filename = md_file.name
        current_hash = get_file_hash(md_file)
        current_hashes[filename] = current_hash
        
        if filename not in old_hashes:
            added.append(filename)
            print(f"  [NEW] {filename}")
        elif old_hashes[filename] != current_hash:
            updated.append(filename)
            print(f"  [UPDATED] {filename}")
        else:
            skipped.append(filename)
    
    return added, updated, skipped, current_hashes

def run_scraper():
    """Execute data-crawl.py to fetch articles."""
    print("\n" + "="*60)
    print("STEP 1: Scraping articles from OptiSign Help Center...")
    print("="*60)
    
    try:
        result = subprocess.run(
            [sys.executable, "scripts/data-crawl.py"],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode != 0:
            print(f"[ERROR] Scraper failed: {result.stderr}")
            return False
        
        print(result.stdout)
        return True
    except subprocess.TimeoutExpired:
        print("[ERROR] Scraper timeout after 10 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Scraper error: {e}")
        return False

def run_uploader():
    """Execute upload_to_vector_store.py for new/updated files."""
    print("\n" + "="*60)
    print("STEP 2: Uploading to Vector Store...")
    print("="*60)
    
    try:
        result = subprocess.run(
            [sys.executable, "scripts/upload_to_vector_store.py"],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode != 0:
            print(f"[ERROR] Upload failed: {result.stderr}")
            return False
        
        print(result.stdout)
        return True
    except subprocess.TimeoutExpired:
        print("[ERROR] Upload timeout after 10 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Upload error: {e}")
        return False

def main():
    """Main orchestration function."""
    start_time = datetime.now()
    print(f"\n[START] OptiSign Daily Job Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Scrape
    if not run_scraper():
        print("\n❌ Job failed at scraping step")
        return False
    
    # Step 2: Upload (new/updated articles are already categorized by data-crawl.py)
    if not run_uploader():
        print("\n❌ Job failed at upload step")
        return False
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "="*60)
    print("[SUCCESS] JOB COMPLETED SUCCESSFULLY")
    print("="*60)
    print(f"[TIME] Duration: {duration:.1f} seconds")
    print(f"[LOG] Check log/upload_log.json for upload summary")
    print("="*60 + "\n")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
