# Use official Python runtime as base image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project
COPY . .

# Create a script to run migrations and start server
RUN echo '#!/bin/bash\n\
    cd /app/core\n\
    echo "Running migrations..."\n\
    python manage.py migrate\n\
    echo "Starting Django server..."\n\
    python manage.py runserver 0.0.0.0:8005\n\
    ' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 8005

# Run entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
