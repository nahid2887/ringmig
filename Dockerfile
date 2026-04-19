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
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project
COPY . .

# Expose port
EXPOSE 8006

# Run migrations and start Daphne ASGI server on container startup
CMD ["bash", "-c", "cd /app/core && echo '[startup] running migrations...' && python manage.py migrate && echo '[startup] collecting static files...' && python manage.py collectstatic --noinput && echo '[startup] starting daphne on 0.0.0.0:8006' && exec python -m daphne -b 0.0.0.0 -p 8006 core.asgi:application"]
