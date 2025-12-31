#!/usr/bin/env python3
"""
Main orchestrator for OptiSign daily scraper job.
Handles scraping, delta detection, and vector store uploads.
"""

import subprocess
import sys
from datetime import datetime

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
        
        # Always print stdout (includes progress messages)
        print(result.stdout)
        
        if result.returncode != 0:
            print(f"[ERROR] Upload failed!")
            if result.stderr:
                print(f"[STDERR]:\n{result.stderr}")
            return False
        
        return True
    except subprocess.TimeoutExpired:
        print("[ERROR] Upload timeout after 10 minutes")
        return False
    except Exception as e:
        print(f"[ERROR] Upload error: {e}")
        import traceback
        traceback.print_exc()
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
    print("="*60 + "\n")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
