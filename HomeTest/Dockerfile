FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/articles/new /app/articles/updated

# Set environment variables
ENV PYTHONUNBUFFERED=1
# Note: The following must be set in DigitalOcean App Platform settings:
# - OPENAI_API_KEY
# - MONGO_USERNAME
# - MONGO_PASSWORD
# - MONGO_HOST
# - MONGO_DATABASE

# Run the main job
ENTRYPOINT ["python", "main.py"]
