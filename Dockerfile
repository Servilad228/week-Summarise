FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if any are needed (none required for pure python, but useful to keep slim lightweight)
# Install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Ensure data directory exists
RUN mkdir -p /app/data

# Default command runs the main script in scheduling mode.
# By using ENTRYPOINT, we can append command line arguments like --login or --run-now when starting the container.
ENTRYPOINT ["python", "main.py"]
