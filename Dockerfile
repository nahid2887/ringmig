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

# Expose port
EXPOSE 8005

# Run migrations and start server
CMD ["bash", "-c", "cd /app/core && python manage.py migrate && python manage.py runserver 0.0.0.0:8005"]
