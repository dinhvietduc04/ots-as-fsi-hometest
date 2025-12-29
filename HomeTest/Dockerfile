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

# Run the main job
ENTRYPOINT ["python", "main.py"]
