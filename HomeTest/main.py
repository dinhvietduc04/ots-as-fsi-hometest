#!/usr/bin/env python3
"""
Main orchestrator for OptiSign daily scraper job.
Handles scraping, delta detection, and vector store uploads.
"""

import subprocess
import sys
import re
from datetime import datetime
from scripts.upload_logs_to_spaces import upload_logs_to_spaces

def extract_stats(output):
    """Extract crawl/upload statistics from script output."""
    stats = {}
    
    # Look for crawl stats
    crawled_match = re.search(r'Total crawled:\s*(\d+)', output)
    if crawled_match:
        stats['crawled'] = int(crawled_match.group(1))
    
    skipped_match = re.search(r'Skipped:\s*(\d+)', output)
    if skipped_match:
        stats['skipped'] = int(skipped_match.group(1))
    
    # Look for upload stats
    new_match = re.search(r'New articles:\s*(\d+)', output)
    if new_match:
        stats['added'] = int(new_match.group(1))
    
    updated_match = re.search(r'Updated articles:\s*(\d+)', output)
    if updated_match:
        stats['updated'] = int(updated_match.group(1))
    
    return stats

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
            return False, {}
        
        print(result.stdout)
        stats = extract_stats(result.stdout)
        return True, stats
    except subprocess.TimeoutExpired:
        print("[ERROR] Scraper timeout after 10 minutes")
        return False, {}
    except Exception as e:
        print(f"[ERROR] Scraper error: {e}")
        return False, {}

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
            return False, {}
        
        stats = extract_stats(result.stdout)
        return True, stats
    except subprocess.TimeoutExpired:
        print("[ERROR] Upload timeout after 10 minutes")
        return False, {}
    except Exception as e:
        print(f"[ERROR] Upload error: {e}")
        import traceback
        traceback.print_exc()
        return False, {}

def main():
    """Main orchestration function."""
    start_time = datetime.now()
    print(f"\n[START] OptiSign Daily Job Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_stats = {}
    error_message = ""
    
    # Step 1: Scrape
    success, crawl_stats = run_scraper()
    all_stats.update(crawl_stats)
    
    if not success:
        error_message = "Job failed at scraping step"
        print("\n❌ Job failed at scraping step")
        upload_logs_to_spaces('failed', stats=all_stats, error_message=error_message)
        return False
    
    # Step 2: Upload (new/updated articles are already categorized by data-crawl.py)
    success, upload_stats = run_uploader()
    all_stats.update(upload_stats)
    
    if not success:
        error_message = "Job failed at upload step"
        print("\n❌ Job failed at upload step")
        upload_logs_to_spaces('failed', stats=all_stats, error_message=error_message)
        return False
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "="*60)
    print("[SUCCESS] JOB COMPLETED SUCCESSFULLY")
    print("="*60)
    print(f"[TIME] Duration: {duration:.1f} seconds")
    print("="*60 + "\n")
    
    # Upload success logs to Spaces
    upload_logs_to_spaces('success', stats=all_stats, error_message="")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
