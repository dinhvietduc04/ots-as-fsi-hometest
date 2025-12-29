FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p log articles articles-jsonl

# Set environment variables
ENV PYTHONUNBUFFERED=1
# Note: OPENAI_API_KEY must be set in DigitalOcean App Platform settings

# Run the main job
ENTRYPOINT ["python", "main.py"]
