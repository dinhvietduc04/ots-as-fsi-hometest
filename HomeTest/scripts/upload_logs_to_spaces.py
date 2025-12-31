"""
Upload job logs to DigitalOcean Spaces with public access.
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def upload_logs_to_spaces(job_status, stats=None, error_message=""):
    """
    Upload job logs to DigitalOcean Spaces.
    
    Args:
        job_status: 'success' or 'failed'
        stats: Dictionary with crawl/upload statistics (crawled, skipped, added, updated)
        error_message: Any error messages
    """
    try:
        import boto3
    except ImportError:
        print("[WARNING] boto3 not installed. Skipping Spaces upload.")
        return False
    
    # Get DigitalOcean Spaces credentials from environment
    space_name = os.getenv('DO_SPACE_NAME')
    space_region = os.getenv('DO_SPACE_REGION', 'nyc3')
    space_key = os.getenv('DO_SPACE_KEY')
    space_secret = os.getenv('DO_SPACE_SECRET')
    
    # Validate credentials
    if not all([space_name, space_key, space_secret]):
        print("[WARNING] DigitalOcean Spaces credentials not fully configured.")
        print("         Set: DO_SPACE_NAME, DO_SPACE_KEY, DO_SPACE_SECRET, DO_SPACE_REGION")
        return False
    
    try:
        # Initialize S3 client (Spaces is S3-compatible)
        client = boto3.client(
            's3',
            region_name=space_region,
            endpoint_url=f'https://{space_region}.digitaloceanspaces.com',
            aws_access_key_id=space_key,
            aws_secret_access_key=space_secret
        )
        
        # Prepare log data
        log_filename = 'job_logs_latest.json'  # Same filename every time (overwrites previous)
        
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'status': job_status,
            'error_message': error_message if error_message else None,
            'environment': 'digitalocean-app-platform'
        }
        
        # Add statistics if provided
        if stats:
            log_data['statistics'] = {
                'crawled': stats.get('crawled', 0),
                'skipped': stats.get('skipped', 0),
                'added': stats.get('added', 0),
                'updated': stats.get('updated', 0)
            }
        else:
            log_data['statistics'] = {
                'crawled': 0,
                'skipped': 0,
                'added': 0,
                'updated': 0
            }
        
        # Upload to Spaces with public access
        client.put_object(
            Bucket=space_name,
            Key=f'logs/{log_filename}',
            Body=json.dumps(log_data, indent=2),
            ContentType='application/json',
            ACL='public-read'  # Make file publicly readable
        )
        
        # Generate public URL
        public_url = f'https://{space_name}.{space_region}.digitaloceanspaces.com/logs/{log_filename}'
        
        print("\n" + "="*60)
        print("[SPACES] Job logs uploaded successfully!")
        print("="*60)
        print(f"Bucket: {space_name}")
        print(f"File: logs/{log_filename}")
        print(f"Public URL: {public_url}")
        if stats:
            print(f"\n[STATISTICS]")
            print(f"  Crawled: {stats.get('crawled', 0)}")
            print(f"  Skipped: {stats.get('skipped', 0)}")
            print(f"  Added:   {stats.get('added', 0)}")
            print(f"  Updated: {stats.get('updated', 0)}")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to upload logs to Spaces: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # For testing
    upload_logs_to_spaces(
        job_status='success',
        stats={'crawled': 5, 'skipped': 2, 'added': 3, 'updated': 1},
        error_message=''
    )
