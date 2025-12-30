import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
import re
import hashlib
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

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

BASE = "https://optisignshelp.zendesk.com/api/v2/help_center/articles.json"
OUT = "articles"

# Create article directories
os.makedirs(os.path.join(OUT, "new"), exist_ok=True)
os.makedirs(os.path.join(OUT, "updated"), exist_ok=True)

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def get_content_hash(content):
    """Get SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()

def load_metadata():
    """Load metadata about previously crawled articles from MongoDB."""
    try:
        db = get_mongo_client()
        metadata_docs = db["articles_metadata"].find()
        metadata = {}
        for doc in metadata_docs:
            article_id = doc.get("_id")  # Keep as int, don't convert to string
            metadata[article_id] = {k: v for k, v in doc.items() if k != "_id"}
        return metadata
    except Exception as e:
        print(f"[WARNING] Could not load metadata from MongoDB: {e}")
        return {}

def save_metadata(metadata):
    """Save article metadata to MongoDB."""
    try:
        db = get_mongo_client()
        collection = db["articles_metadata"]
        
        for article_id, data in metadata.items():
            collection.update_one(
                {"_id": int(article_id)},  # Keep _id as int
                {"$set": data},
                upsert=True
            )
        print(f"[MONGODB] Saved {len(metadata)} articles to database")
    except Exception as e:
        print(f"[ERROR] Failed to save metadata to MongoDB: {e}")
        raise

def is_first_run():
    """Check if this is the first crawl (no metadata in MongoDB)."""
    try:
        metadata = load_metadata()
        return len(metadata) == 0
    except:
        return True

def should_crawl_article(updated_at, cutoff):
    return updated_at > cutoff

def get_category(article_id, metadata, is_first, content_hash):
    """Determine if article should go to 'new' or 'updated' folder."""
    if is_first:
        return "new"
    
    if article_id not in metadata:
        return "new"
    
    # Check if content actually changed by comparing hash
    old_hash = metadata[article_id].get("content_hash")
    if old_hash and old_hash == content_hash:
        return None  # No change, skip processing
    
    # Article have its content changed
    return "updated"

# ===================================================

# Crawl articles
metadata = load_metadata()
is_first = is_first_run()

print(f"[CRAWL] First run: {is_first}")
print(f"[CRAWL] Existing articles in metadata: {len(metadata)}")

cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
print(f"[CRAWL] Cutoff time (UTC): {cutoff.isoformat()}")
# Determine which endpoint to use

url = BASE if is_first else f"{BASE}?updated_since={cutoff.isoformat()}"

new_count = updated_count = skipped_count = crawled_count = 0
stop_crawl = False

while url and not stop_crawl:
    res = requests.get(url).json()
    
    # Debug: check response structure
    if "articles" not in res:
        print(f"[ERROR] Unexpected response format: {res}")
        break
    
    for article in res["articles"]:
        if article["draft"]:
            continue
        
        updated_at = datetime.fromisoformat(
            article["updated_at"].replace("Z", "+00:00")
        )

        if not is_first and updated_at <= cutoff or crawled_count >= 40:
            print(f"[STOP] Reached articles older than cutoff. Stopping crawl.")
            stop_crawl = True
            break

        # Check if we should crawl this article
        if not should_crawl_article(updated_at, cutoff) and not is_first:
            skipped_count += 1
            continue
        
        article_id = article["id"]
        
        # Process article content
        soup = BeautifulSoup(article["body"], "html.parser")
        
        # Remove navigation, ads, scripts, styles, noscript, and common unwanted elements
        for tag in soup(["nav", "aside", "script", "style", "noscript"]):
            tag.decompose()
        
        # Remove divs/sections commonly used for ads
        for tag in soup.find_all(
            class_=lambda x: x and any(
                ad in x.lower() for ad in 
                ['ad', 'advertisement', 'banner', 'sidebar', 'related']
            )
        ):
            tag.decompose()
        
        # Convert to markdown, normalize whitespace, and compute content hash
        markdown_content = md(str(soup), heading_style="underlined")
        normalized_content = re.sub(r'\s+', ' ', markdown_content).strip()
        content_hash = get_content_hash(normalized_content)
        
        # Determine category
        category = get_category(article_id, metadata, is_first, content_hash)
        
        # Skip if no changes detected
        if category is None:
            skipped_count += 1
            continue
        
        # Save to category folder
        slug = slugify(article["title"])
        path = os.path.join(OUT, category, f"{slug}.md")
        
        with open(path, "w", encoding="utf-8") as f:
            # Write header and source URL at TOP
            f.write(f"# {article['title']}\n")
            f.write(f"**Source:** {article['html_url']}\n\n")
            f.write(normalized_content)
        
    # Update metadata
        metadata[article_id] = {
            "title": article["title"],
            "slug": slug,
            "updated_at": article["updated_at"],
            "created_at": article["created_at"],
            "category": category,
            "content_hash": content_hash,
            "openai_file_id": metadata.get(article_id, {}).get("openai_file_id")  # Preserve existing file ID
        }
        
        crawled_count += 1
        if category == "new":
            new_count += 1
        else:
            updated_count += 1
    
        print(f"  [SAVED] Article {article_id}: {article['title']}")

    url = res.get("next_page")

# Save metadata
save_metadata(metadata)

print(f"\n[SUMMARY]")
print(f"  - New articles:     {new_count}")
print(f"  - Updated articles: {updated_count}")
print(f"  - Skipped:          {skipped_count}")
print(f"  - Total crawled:    {crawled_count}")
print(f"  - Total in metadata: {len(metadata)}")

