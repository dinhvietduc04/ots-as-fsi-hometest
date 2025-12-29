import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize client (will validate at runtime)
def get_client():
    """Get OpenAI client, validating API key is set."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "❌ OPENAI_API_KEY environment variable is not set. "
            "Please set it in DigitalOcean App Platform settings."
        )
    return OpenAI(api_key=OPENAI_API_KEY)

client = None  # Lazy initialized

# Configuration - use root-relative paths
ARTICLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "articles")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
METADATA_FILE = os.path.join(ARTICLES_DIR, "metadata.json")
VECTOR_STORE_NAME = "optisign-help-center"
CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 150  # Overlap between chunks

def load_metadata():
    """Load metadata about articles."""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_metadata(metadata):
    """Save updated metadata."""
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

def delete_file_from_openai(file_id):
    """Delete a file from OpenAI."""
    try:
        response = requests.delete(
            f"https://api.openai.com/v1/files/{file_id}",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
        )
        response.raise_for_status()
        print(f"  ✓ Deleted old OpenAI file: {file_id}")
        return True
    except Exception as e:
        print(f"  ✗ Error deleting file {file_id}: {e}")
        return False

def delete_file_from_vector_store(vector_store_id, file_id):
    """Remove a file from vector store."""
    try:
        response = requests.delete(
            f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files/{file_id}",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "assistants=v2"
            }
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"  ✗ Error removing from vector store: {e}")
        return False

def create_or_get_vector_store(name):
    """Create or get existing vector store via OpenAI API."""
    try:
        # First, try to list existing vector stores
        response = requests.get(
            "https://api.openai.com/v1/vector_stores",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "assistants=v2"
            }
        )
        response.raise_for_status()
        vector_stores = response.json()
        
        # Look for existing vector store with matching name
        for vs in vector_stores.get("data", []):
            if vs.get("name") == name:
                print(f"✓ Found existing vector store: {vs['id']}")
                return vs
        
        # If not found, create a new one
        print(f"No existing vector store found, creating new one...")
        response = requests.post(
            "https://api.openai.com/v1/vector_stores",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "assistants=v2"
            },
            json={"name": name}
        )
        response.raise_for_status()
        vs_data = response.json()
        print(f"✓ Created new vector store: {vs_data['id']}")
        return vs_data
    except Exception as e:
        print(f"✗ Error with vector store: {e}")
        return None

def add_file_to_vector_store(vector_store_id, file_id):
    """Add a file to the vector store."""
    try:
        response = requests.post(
            f"https://api.openai.com/v1/vector_stores/{vector_store_id}/files",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "OpenAI-Beta": "assistants=v2"
            },
            json={"file_id": file_id}
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ✗ Error adding file to vector store: {e}")
        return None


def upload_articles():
    """Upload new and updated articles to vector store."""
    import glob
    import time
    
    # Initialize client
    global client
    if client is None:
        client = get_client()
    
    # Load metadata
    metadata = load_metadata()
    vector_store = create_or_get_vector_store(VECTOR_STORE_NAME)
    
    if not vector_store:
        print("Failed to create/get vector store")
        return False
    
    vector_store_id = vector_store['id']
    print(f"\nVector Store ID: {vector_store_id}\n")
    
    # Get files from new and updated folders
    new_files = sorted(glob.glob(os.path.join(ARTICLES_DIR, "new", "*.md")))
    updated_files = sorted(glob.glob(os.path.join(ARTICLES_DIR, "updated", "*.md")))
    
    print(f"[NEW] {len(new_files)} files to upload")
    print(f"[UPDATED] {len(updated_files)} files to upload")
    
    new_uploaded = 0
    updated_uploaded = 0
    
    # Handle updated files - delete old version first
    for idx, md_file in enumerate(updated_files, 1):
        filename = Path(md_file).name
        print(f"\n[UPDATED {idx}/{len(updated_files)}] {filename}")
        
        # Find article ID in metadata by slug
        article_id = None
        for aid, meta in metadata.items():
            if meta.get("slug") + ".md" == filename:
                article_id = aid
                break
        
        if not article_id:
            print(f"  ⚠ Could not find article ID in metadata")
            continue
        
        # Delete old file from OpenAI if it exists
        old_file_id = metadata[article_id].get("openai_file_id")
        if old_file_id:
            print(f"  ├─ Deleting old file: {old_file_id}")
            delete_file_from_openai(old_file_id)
            delete_file_from_vector_store(vector_store_id, old_file_id)
        
        # Upload new version
        try:
            with open(md_file, "rb") as f:
                response = client.files.create(
                    file=f,
                    purpose="assistants"
                )
                new_file_id = response.id
                print(f"  ├─ ✓ New OpenAI File ID: {new_file_id}")
                
                # Add to vector store
                add_file_to_vector_store(vector_store_id, new_file_id)
                print(f"  └─ ✓ Added to vector store")
                
                # Update metadata
                metadata[article_id]["openai_file_id"] = new_file_id
                updated_uploaded += 1
        except Exception as e:
            print(f"  ✗ Error uploading: {e}")
    
    # Handle new files
    for idx, md_file in enumerate(new_files, 1):
        filename = Path(md_file).name
        print(f"\n[NEW {idx}/{len(new_files)}] {filename}")
        
        # Find article ID in metadata
        article_id = None
        for aid, meta in metadata.items():
            if meta.get("slug") + ".md" == filename:
                article_id = aid
                break
        
        if not article_id:
            print(f"  ⚠ Could not find article ID in metadata")
            continue
        
        # Upload file
        try:
            with open(md_file, "rb") as f:
                response = client.files.create(
                    file=f,
                    purpose="assistants"
                )
                file_id = response.id
                print(f"  ├─ ✓ OpenAI File ID: {file_id}")
                
                # Add to vector store
                add_file_to_vector_store(vector_store_id, file_id)
                print(f"  └─ ✓ Added to vector store")
                
                # Update metadata
                metadata[article_id]["openai_file_id"] = file_id
                new_uploaded += 1
        except Exception as e:
            print(f"  ✗ Error uploading: {e}")
    
    # Wait for processing
    if new_uploaded > 0 or updated_uploaded > 0:
        print("\nWaiting for files to be processed...")
        time.sleep(2)
    
    # Save updated metadata
    save_metadata(metadata)
    
    # Log results
    os.makedirs(LOG_DIR, exist_ok=True)
    log_data = {
        "vector_store_id": vector_store_id,
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "new_uploaded": new_uploaded,
        "updated_uploaded": updated_uploaded,
        "total_uploaded": new_uploaded + updated_uploaded
    }
    
    log_path = os.path.join(LOG_DIR, "upload_log.json")
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"[UPLOAD SUMMARY]")
    print(f"{'='*50}")
    print(f"New articles:     {new_uploaded}")
    print(f"Updated articles: {updated_uploaded}")
    print(f"Total uploaded:   {new_uploaded + updated_uploaded}")
    print(f"{'='*50}")
    
    # Clean up new/updated folders for next run
    import shutil
    new_folder = os.path.join(ARTICLES_DIR, "new")
    updated_folder = os.path.join(ARTICLES_DIR, "updated")
    
    if os.path.exists(new_folder):
        shutil.rmtree(new_folder)
        print("\n[CLEANUP] Deleted articles/new/")
    
    if os.path.exists(updated_folder):
        shutil.rmtree(updated_folder)
        print("[CLEANUP] Deleted articles/updated/")
    
    print("[SUCCESS] Ready for next run\n")
    
    return True

if __name__ == "__main__":
    upload_articles()

