# OptiSign Help Center Vector Store

Daily scraper + delta detector + vector store uploader.

![OptiSign Project AI Response](./assets/result.png)

## Setup

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment
.venv\Scripts\activate.bat    # Windows CMD
# or
.venv\Scripts\Activate.ps1    # Windows PowerShell

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# Copy and edit .env with:
# - OPENAI_API_KEY (from OpenAI)
# - MONGO_USERNAME (from DigitalOcean MongoDB)
# - MONGO_PASSWORD (from DigitalOcean MongoDB)
# - MONGO_HOST (mongodb+srv://...)
# - MONGO_DATABASE (your database name)
```

## Run Locally

**Step 1: Crawl articles from Zendesk**
```bash
python scripts/data-crawl.py
```
- Fetches articles from OptiSign Zendesk Help Center
- Detects new/updated articles (hash-based)
- Saves metadata to MongoDB

**Step 2: Upload to OpenAI Vector Store**
```bash
python scripts/upload_to_vector_store.py
```
- Reads metadata from MongoDB
- Uploads articles to OpenAI Vector Store
- Stores file IDs in MongoDB
- Logs results to `log/upload_log_*.json`

**Example output:**
```
[SUMMARY]
  - New articles:     2
  - Updated articles: 1
  - Total uploaded:   3
```

## Docker

**Local testing (with volume mounts to see output):**
```bash
docker build -t optisign-scraper:latest .

$env:OPENAI_API_KEY = (Get-Content .env | Select-String "OPENAI_API_KEY=").ToString().Split("=")[1]
docker run --rm `
  -v "${PWD}\articles:/app/articles" `
  -v "${PWD}\log:/app/log" `
  -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  optisign-scraper:latest
```

**Production (on DigitalOcean):**
```bash
docker run -e OPENAI_API_KEY=sk-xxx \
  -v /var/optisign-data/articles:/app/articles \
  -v /var/optisign-data/log:/app/log \
  registry.digitalocean.com/your-registry/scraper:latest
```

## Daily Job Logs

**Local:** Check `log/delta_log.json` after running `python main.py`

**Production (DigitalOcean):** See [DEPLOYMENT.md](DEPLOYMENT.md) for setup
```bash
# Last 20 runs
tail -20 /var/optisign-data/cron.log

# Latest delta summary
cat /var/optisign-data/log/delta_log.json
```

## How It Works

1. **Data Crawling** (`data-crawl.py`): Fetches ≤40 articles from OptiSign Zendesk API
2. **Delta Detection** (`main.py`): Compares hashes, identifies new/updated articles
3. **Vector Store Upload** (`upload_to_vector_store.py`): Uploads only changed files to OpenAI
4. **Daily Scheduling**: Runs automatically at **9:00 AM UTC+7 (Bangkok time)** once per day on DigitalOcean

## Using in OpenAI Playground

1. Go to [platform.openai.com/playground](https://platform.openai.com/playground)
2. Create new Assistant
3. In Files section, attach Vector Store ID from `log/upload_log.json`
4. Set system prompt and test with questions like "How do I add a YouTube video?"

## Configuration

- **Chunk Size:** 1000 characters (semantic boundaries)
- **Overlap:** 150 characters (maintains context)
- **Vector Store:** "optisign-help-center"
