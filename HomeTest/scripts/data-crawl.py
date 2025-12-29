import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import os
import re
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE = "https://optisignshelp.zendesk.com/api/v2/help_center/articles.json"
OUT = "articles"
METADATA_FILE = os.path.join(OUT, "metadata.json")

# Create article directories
os.makedirs(os.path.join(OUT, "new"), exist_ok=True)
os.makedirs(os.path.join(OUT, "updated"), exist_ok=True)

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def load_metadata():
    """Load metadata about previously crawled articles."""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_metadata(metadata):
    """Save article metadata."""
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

def is_first_run():
    """Check if this is the first crawl (no metadata file)."""
    return not os.path.exists(METADATA_FILE)

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

def get_category(article_id, metadata, is_first):
    """Determine if article should go to 'new' or 'updated' folder."""
    if is_first:
        return "new"
    
    if article_id not in metadata:
        return "new"
    
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
            continue
        
        article_id = article["id"]
        
        # Determine category
        category = get_category(article_id, metadata, is_first)
        
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
        
        # Save to category folder
        slug = slugify(article["title"])
        path = os.path.join(OUT, category, f"{slug}.md")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {article['title']}\n\n")
            f.write(markdown_content)
            f.write(f"\n\n---\n**Source:** {article['html_url']}")
        
        # Update metadata
        metadata[article_id] = {
            "title": article["title"],
            "slug": slug,
            "updated_at": article["updated_at"],
            "created_at": article["created_at"],
            "category": category,
            "openai_file_id": metadata.get(article_id, {}).get("openai_file_id")  # Preserve existing file ID
        }
        
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
print(f"[METADATA] Saved: {METADATA_FILE}")

