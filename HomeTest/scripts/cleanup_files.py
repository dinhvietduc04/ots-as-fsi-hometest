import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def delete_all_openai_files():
    """Delete all files from OpenAI file storage."""
    if not OPENAI_API_KEY:
        print("[ERROR] OPENAI_API_KEY environment variable is not set.")
        return
    
    try:
        # Get list of all files
        response = requests.get(
            "https://api.openai.com/v1/files",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
        )
        response.raise_for_status()
        files = response.json().get("data", [])
        
        if not files:
            print("No files found in OpenAI storage.")
            return
        
        print(f"Found {len(files)} files. Deleting...")
        deleted_count = 0
        
        for file in files:
            file_id = file.get("id")
            filename = file.get("filename")
            try:
                response = requests.delete(
                    f"https://api.openai.com/v1/files/{file_id}",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
                )
                response.raise_for_status()
                print(f"  [+] Deleted: {filename} ({file_id})")
                deleted_count += 1
            except Exception as e:
                print(f"  [-] Error deleting {filename}: {e}")
        
        print(f"\nSuccessfully deleted {deleted_count}/{len(files)} files.")
        
    except Exception as e:
        print(f"Error listing files: {e}")

if __name__ == "__main__":
    delete_all_openai_files()
