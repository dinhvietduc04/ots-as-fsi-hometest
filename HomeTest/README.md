# OptiSign Help Center Vector Store

Daily scraper + delta detector + vector store uploader.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure API key (copy from .env.sample)
cp .env.sample .env
# Edit .env and add your OpenAI API key
```

## Run Locally

```bash
python main.py
```

**Output:**
- Scrapes articles from OptiSign Help Center
- Detects new/updated articles (hash-based)
- Uploads only changed files to OpenAI Vector Store
- Logs results to `log/delta_log.json`

**Example output:**
```
[SUMMARY]
  - Added:   2 articles
  - Updated: 1 articles
  - Skipped: 37 articles
  - Uploaded: 3 files
```

## Docker

**Local testing (with volume mounts to see output):**
```bash
docker build -t optisign-scraper:latest .
docker run -e OPENAI_API_KEY=sk-xxx \
  -v $(pwd)/articles:/app/articles \
  -v $(pwd)/log:/app/log \
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

