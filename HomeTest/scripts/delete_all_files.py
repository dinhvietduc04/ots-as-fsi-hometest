#!/usr/bin/env python3
"""
Delete all files from OpenAI file storage.
Useful for cleanup before restarting tests.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY not found in .env")
    exit(1)

print("[INFO] Fetching all files from OpenAI...")
response = requests.get(
    "https://api.openai.com/v1/files",
    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
)

if response.status_code != 200:
    print(f"❌ Error fetching files: {response.text}")
    exit(1)

files = response.json().get("data", [])
print(f"[INFO] Found {len(files)} file(s)\n")

if not files:
    print("[OK] No files to delete")
    exit(0)

deleted_count = 0
failed_count = 0

for idx, file in enumerate(files, 1):
    file_id = file['id']
    filename = file.get('filename', 'unknown')
    
    print(f"[{idx}/{len(files)}] Deleting: {filename} ({file_id})")
    
    delete_response = requests.delete(
        f"https://api.openai.com/v1/files/{file_id}",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
    )
    
    if delete_response.status_code == 200:
        print(f"  ✅ Deleted")
        deleted_count += 1
    else:
        print(f"  ❌ Error: {delete_response.text}")
        failed_count += 1

print(f"\n{'='*50}")
print(f"[SUMMARY]")
print(f"{'='*50}")
print(f"Deleted:  {deleted_count}")
print(f"Failed:   {failed_count}")
print(f"{'='*50}")

if failed_count == 0:
    print("\n✅ All files deleted successfully!")
else:
    print(f"\n⚠️  {failed_count} file(s) failed to delete")
