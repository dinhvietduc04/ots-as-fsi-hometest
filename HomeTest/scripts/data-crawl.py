import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
import re
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# MongoDB connection
MONGO_USERNAME = os.getenv("MONGO_USERNAME")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD")
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb+srv://db-mongodb-dailyjob-effc3b38.mongo.ondigitalocean.com")
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

def get_content_hash(content):
    """Get SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()

def should_crawl_article(article, is_first):
    """Determine if article should be crawled based on update time."""
    if is_first:
        # First run: crawl everything
        return True
    
    # Subsequent runs: only crawl if modified in last 24 hours
    updated_at = datetime.fromisoformat(article["updated_at"].replace("Z", "+00:00"))
    cutoff = datetime.now(updated_at.tzinfo) - timedelta(hours=24)
    
    return updated_at > cutoff

def is_article_new(article_id, metadata):
    """Check if article is new or updated."""
    if article_id not in metadata:
        return True  # New article
    
    old_updated_at = metadata[article_id].get("updated_at")
    new_updated_at = article["updated_at"]
    
    return old_updated_at != new_updated_at  # Updated if timestamp changed

def get_category(article_id, metadata, is_first, content_hash):
    """Determine if article should go to 'new' or 'updated' folder."""
    if is_first:
        return "new"
    
    if article_id not in metadata:
        return "new"
    
    # Check if content actually changed by comparing hash
    old_hash = metadata[article_id].get("content_hash")
    if old_hash and old_hash == content_hash:
        return "updated"  # No change, still mark as updated to preserve
    
    # If no old hash but article exists, mark as updated to add hash
    if not old_hash:
        return "updated"
    
    return "updated"

# Crawl articles
metadata = load_metadata()
is_first = is_first_run()
print(f"[CRAWL] First run: {is_first}")
print(f"[CRAWL] Existing articles in metadata: {len(metadata)}")

url = BASE
crawled_count = 0
new_count = 0
updated_count = 0
skipped_count = 0

while url and crawled_count < 40:
    res = requests.get(url).json()
    
    for article in res["articles"]:
        if article["draft"]:
            continue
        
        # Check if we should crawl this article
        if not should_crawl_article(article, is_first):
            # Only count as skipped if within first 40 articles encountered
            if crawled_count + skipped_count < 40:
                skipped_count += 1
            continue
        
        article_id = article["id"]
        
        # Process article
        html = article["body"]
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove navigation, ads, scripts, styles, and common unwanted elements
        for tag in soup(["nav", "aside", "script", "style", "noscript"]):
            tag.decompose()
        
        # Remove divs/sections commonly used for ads
        for tag in soup.find_all(class_=lambda x: x and any(ad in x.lower() for ad in ['ad', 'advertisement', 'banner', 'sidebar', 'related'])):
            tag.decompose()
        
        # Convert HTML to Markdown
        markdown_content = md(str(soup), heading_style="underlined")
        
        # Clean up excessive whitespace
        markdown_content = re.sub(r'\n{3,}', '\n\n', markdown_content).strip()
        
        # Calculate content hash
        content_hash = get_content_hash(markdown_content)
        
        # Determine category
        category = get_category(article_id, metadata, is_first, content_hash)
        
        # Save to category folder
        slug = slugify(article["title"])
        path = os.path.join(OUT, category, f"{slug}.md")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            # Write header and source URL at TOP (ensures it's preserved during chunking)
            f.write(f"# {article['title']}\n")
            f.write(f"**Source:** {article['html_url']}\n\n")
            f.write(markdown_content)
        
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
        
        print(f"  [SAVED] Article {article_id}: {article['title']}")
        
        if category == "new":
            new_count += 1
        else:
            updated_count += 1
        
        crawled_count += 1
        if crawled_count >= 40:
            break
    
    url = res.get("next_page") if crawled_count < 40 else None

# Save metadata
save_metadata(metadata)

print(f"\n[SUMMARY]")
print(f"  - New articles:     {new_count}")
print(f"  - Updated articles: {updated_count}")
print(f"  - Skipped:          {skipped_count}")
print(f"  - Total crawled:    {crawled_count}")
print(f"  - Total in metadata: {len(metadata)}")

