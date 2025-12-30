import os
import json
import requests
import hashlib
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

# Load environment variables
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# MongoDB connection
MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_HOST = os.getenv("MONGO_HOST")
MONGO_DATABASE = os.getenv("MONGO_DATABASE")

def get_mongo_client():
    """Create MongoDB connection string and return client."""
    if not MONGO_USERNAME or not MONGO_PASSWORD or not MONGO_DATABASE:
        raise RuntimeError(
            "[ERROR] MongoDB credentials not set. "
            "Please set MONGO_USERNAME, MONGO_PASSWORD, and MONGO_DATABASE environment variables."
        )
    
    # Build connection string with TLS enabled for DigitalOcean MongoDB
    connection_string = f"mongodb+srv://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST.replace('mongodb+srv://', '')}/?retryWrites=true&w=majority&tls=true"
    client = MongoClient(connection_string)
    return client[MONGO_DATABASE]

# Initialize client (will validate at runtime)
def get_client():
    """Get OpenAI client, validating API key is set."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "[ERROR] OPENAI_API_KEY environment variable is not set. "
            "Please set it in DigitalOcean App Platform settings."
        )
    return OpenAI(api_key=OPENAI_API_KEY)

client = None  # Lazy initialized

# Configuration - use root-relative paths
ARTICLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "articles")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
VECTOR_STORE_NAME = "optisign-help-center"
CHUNK_SIZE = 1500  # Characters per chunk (larger to preserve URL with content)
CHUNK_OVERLAP = 300  # Increased overlap (20% of chunk) to ensure metadata appears in all chunks
CHUNKS_LOG_FILE = os.path.join(LOG_DIR, "chunks_metadata.json")

def load_metadata():
    """Load metadata about articles from MongoDB."""
    try:
        db = get_mongo_client()
        metadata_docs = db["articles_metadata"].find()
        metadata = {}
        for doc in metadata_docs:
            article_id = doc.get("_id")  # Keep as int
            metadata[article_id] = {k: v for k, v in doc.items() if k != "_id"}
        return metadata
    except Exception as e:
        print(f"[WARNING] Could not load metadata from MongoDB: {e}")
        return {}

def save_metadata(metadata):
    """Save updated metadata to MongoDB."""
    try:
        db = get_mongo_client()
        collection = db["articles_metadata"]
        
        for article_id, data in metadata.items():
            collection.update_one(
                {"_id": int(article_id)},  # Keep _id as int
                {"$set": data},
                upsert=True
            )
    except Exception as e:
        print(f"[ERROR] Failed to save metadata to MongoDB: {e}")
        raise

def get_content_hash(content):
    """Get SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()

def is_article_updated(article_id, content):
    """Check if article is truly new or updated by comparing content hash."""
    metadata = load_metadata()
    
    if article_id not in metadata:
        return True  # New article
    
    # If no content_hash is stored yet, consider it as needing upload
    stored_hash = metadata[article_id].get("content_hash")
    if not stored_hash:
        # But only if it doesn't have a file_id already (prevents re-upload of old articles)
        if metadata[article_id].get("openai_file_id"):
            # Article has been uploaded before but no hash stored - compare hashes
            current_hash = get_content_hash(content)
            return False  # Assume unchanged if file already exists without hash
        return True  # New article that hasn't been uploaded yet
    
    current_hash = get_content_hash(content)
    return current_hash != stored_hash

def delete_file_from_openai(file_id):
    """Delete a file from OpenAI."""
    try:
        response = requests.delete(
            f"https://api.openai.com/v1/files/{file_id}",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}
        )
        response.raise_for_status()
        print(f"  [+] Deleted old OpenAI file: {file_id}")
        return True
    except Exception as e:
        print(f"  [-] Error deleting file {file_id}: {e}")
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
        print(f"  [-] Error removing from vector store: {e}")
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
                print(f"[+] Found existing vector store: {vs['id']}")
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
        print(f"[+] Created new vector store: {vs_data['id']}")
        return vs_data
    except Exception as e:
        print(f"[-] Error with vector store: {e}")
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
        print(f"  [-] Error adding file to vector store: {e}")
        return None

def create_chunks_with_metadata(md_file_path, article_id, metadata_dict):
    """Create semantic chunks with metadata tracking."""
    try:
        with open(md_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract article info (title and URL from first 2 lines)
        lines = content.split('\n')
        title = lines[0].replace('# ', '').strip() if lines[0].startswith('#') else "Unknown"
        source_url = None
        if len(lines) > 1 and lines[1].startswith('**Source:**'):
            source_url = lines[1].replace('**Source:**', '').strip()
        
        chunks = []
        start_pos = 0
        chunk_num = 0
        
        while start_pos < len(content):
            end_pos = min(start_pos + CHUNK_SIZE, len(content))
            
            # Try to break at sentence boundary
            if end_pos < len(content):
                last_period = content.rfind('. ', start_pos, end_pos)
                if last_period != -1 and last_period > start_pos:
                    end_pos = last_period + 2
            
            chunk_text = content[start_pos:end_pos].strip()
            
            if chunk_text:
                chunks.append({
                    "article_id": article_id,
                    "article_title": title,
                    "source_url": source_url,
                    "chunk_number": chunk_num,
                    "chunk_size": len(chunk_text)
                })
                chunk_num += 1
            
            # Calculate next position - ensure we always progress
            if end_pos >= len(content):
                # Reached the end
                break
            
            # Move forward by at least 1 character to avoid infinite loop
            next_start = max(start_pos + 1, end_pos - CHUNK_OVERLAP)
            start_pos = next_start
        
        return chunks
    except Exception as e:
        print(f"  [-] Error creating chunks: {e}")
        import traceback
        traceback.print_exc()
        return []

def save_chunks_metadata(chunks_data):
    """Save chunk metadata for tracking and debugging."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # Save current chunks (for immediate reference) - compact format for speed
        with open(CHUNKS_LOG_FILE, "w") as f:
            json.dump(chunks_data, f)  # No indent for faster I/O
        
        print(f"  [+] Saved chunks metadata: {len(chunks_data)} chunks tracked")
    except Exception as e:
        print(f"  [!] Error saving chunks metadata: {e}")


def upload_articles():
    """Upload new and updated articles to vector store."""
    import glob
    import time
    
    # Initialize client
    global client
    if client is None:
        try:
            client = get_client()
        except RuntimeError as e:
            print(f"[CRITICAL ERROR] {e}")
            print("[DEBUG] OPENAI_API_KEY value:", "SET" if OPENAI_API_KEY else "NOT SET")
            raise
    
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
    all_chunks_metadata = []
    
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
            print(f"  [!] Could not find article ID in metadata")

            continue
        
        # Read content to check if updated
        try:
            with open(md_file, "r") as f:
                content = f.read()
        except:
            with open(md_file, "rb") as f:
                content = f.read().decode("utf-8", errors="ignore")
        
        # Check if content actually changed
        if not is_article_updated(article_id, content):
            print(f"  [*] Article content unchanged, skipping")
            # Still save the content hash for future reference
            metadata[article_id]["content_hash"] = get_content_hash(content)
            continue
        
        # Delete old file from OpenAI if it exists
        old_file_id = metadata[article_id].get("openai_file_id")
        if old_file_id:
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
                print(f"  [+] Uploaded File ID: {new_file_id}")
                
                # Track chunks metadata
                chunks = create_chunks_with_metadata(md_file, article_id, metadata[article_id])
                all_chunks_metadata.extend(chunks)
                
                # Add to vector store
                add_file_to_vector_store(vector_store_id, new_file_id)
                
                # Update metadata with file ID and content hash
                metadata[article_id]["openai_file_id"] = new_file_id
                metadata[article_id]["content_hash"] = get_content_hash(content)
                updated_uploaded += 1
        except Exception as e:
            print(f"  [-] Error uploading: {e}")
            import traceback
            traceback.print_exc()
    
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
            print(f"  [!] Could not find article ID in metadata")
            continue
        
        # Read content to check if already uploaded
        try:
            with open(md_file, "r") as f:
                content = f.read()
        except:
            with open(md_file, "rb") as f:
                content = f.read().decode("utf-8", errors="ignore")
        
        # Check if content already exists
        if not is_article_updated(article_id, content):
            print(f"  [*] Article already uploaded with same content, skipping")
            # Still save the content hash for future reference
            metadata[article_id]["content_hash"] = get_content_hash(content)
            continue
        
        # Upload file
        try:
            with open(md_file, "rb") as f:
                response = client.files.create(
                    file=f,
                    purpose="assistants"
                )
                file_id = response.id
                print(f"  [+] Uploaded File ID: {file_id}")
                
                # Track chunks metadata
                chunks = create_chunks_with_metadata(md_file, article_id, metadata[article_id])
                all_chunks_metadata.extend(chunks)
                
                # Add to vector store
                add_file_to_vector_store(vector_store_id, file_id)
                
                # Update metadata with file ID and content hash
                metadata[article_id]["openai_file_id"] = file_id
                metadata[article_id]["content_hash"] = get_content_hash(content)
                new_uploaded += 1
        except Exception as e:
            print(f"  [-] Error uploading: {e}")
            import traceback
            traceback.print_exc()
    
    # Wait for processing
    if new_uploaded > 0 or updated_uploaded > 0:
        print("\nWaiting for files to be processed...")
        time.sleep(2)
    
    # Save updated metadata
    save_metadata(metadata)
    
    # Save chunks metadata
    if all_chunks_metadata:
        save_chunks_metadata(all_chunks_metadata)
    
    # Log results
    os.makedirs(LOG_DIR, exist_ok=True)
    log_data = {
        "vector_store_id": vector_store_id,
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "new_uploaded": new_uploaded,
        "updated_uploaded": updated_uploaded,
        "total_uploaded": new_uploaded + updated_uploaded
    }
    
    # Archive with timestamp for historical tracking
    timestamp = __import__('datetime').datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archived_log_path = os.path.join(LOG_DIR, f"upload_log_{timestamp}.json")
    with open(archived_log_path, "w") as f:
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
    try:
        upload_articles()
    except Exception as e:
        import traceback
        print("\n" + "="*60)
        print("[CRITICAL ERROR]")
        print("="*60)
        print(f"Error: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        print("="*60)
        exit(1)

