# Ring Mig API - Django REST API

A Django REST API for Ring Mig - a platform connecting Talkers and Listeners with email-based OTP registration and JWT authentication.

## Features

- 🔐 Email-based OTP Registration
- 🔑 JWT Authentication with Token Blacklist
- 👥 User Types: Talker & Listener
- 📚 Swagger/OpenAPI Documentation
- 🌐 CORS Support
- 🐘 PostgreSQL Database Support
- 🐳 Docker & Docker Compose Ready

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose installed
- Port 8005 and 5432 available

### Run with Docker Compose

```bash
# Clone/navigate to project directory
cd ringmig

# Build and start services
docker-compose up --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

The API will be available at: **http://localhost:8005**

### API Endpoints

- **Swagger UI**: http://localhost:8005/swagger/
- **ReDoc**: http://localhost:8005/redoc/
- **Schema JSON**: http://localhost:8005/swagger.json

### Default PostgreSQL Credentials

- **Host**: localhost:5432
- **Database**: ringmig_db
- **User**: ringmig_user
- **Password**: ringmig_password_123

## Local Development Setup

### Create Virtual Environment

```bash
cd ringmig
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# Linux/Mac
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Migrations

```bash
cd core
python manage.py migrate
```

### Start Development Server

```bash
python manage.py runserver
```

Server runs on: http://localhost:8000

## Docker Commands

### Build Image

```bash
docker-compose build
```

### Run Services

```bash
docker-compose up
```

### Run with Production Server (Gunicorn)

Edit `docker-compose.yml` and change the web service command to:

```yaml
command: bash -c "cd /app/core && python manage.py migrate && gunicorn core.wsgi:application --bind 0.0.0.0:8005"
```

### Access PostgreSQL Database

```bash
docker exec -it ringmig_postgres psql -U ringmig_user -d ringmig_db
```

### View Logs

```bash
docker-compose logs web
docker-compose logs db
```

### Stop Containers

```bash
docker-compose down
```

### Remove Volumes

```bash
docker-compose down -v  # This will delete the database
```

## Environment Variables

For local development, create a `.env` file:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
DB_ENGINE=django.db.backends.postgresql
DB_NAME=ringmig_db
DB_USER=ringmig_user
DB_PASSWORD=ringmig_password_123
DB_HOST=localhost
DB_PORT=5432
```

## API Documentation

### Authentication

All protected endpoints require JWT token in Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

### Available Endpoints

- `POST /api/auth/otp-request/` - Request OTP for registration
- `POST /api/auth/otp-verify/` - Verify OTP and complete registration
- `POST /api/auth/login/` - User login
- `POST /api/auth/logout/` - User logout
- `POST /api/auth/token/refresh/` - Refresh JWT token
- `GET /api/auth/profile/` - Get user profile (authenticated)

## Project Structure

```
ringmig/
├── core/                      # Django project
│   ├── core/                  # Project settings
│   │   ├── settings.py        # Django settings
│   │   ├── urls.py            # URL routing
│   │   ├── wsgi.py            # WSGI config
│   │   └── asgi.py            # ASGI config
│   ├── users/                 # Users app
│   │   ├── models.py          # User & OTP models
│   │   ├── views.py           # API views
│   │   ├── serializers.py     # DRF serializers
│   │   ├── urls.py            # App URLs
│   │   └── migrations/        # Database migrations
│   ├── manage.py              # Django management
│   └── db.sqlite3             # SQLite (local dev)
├── Dockerfile                 # Docker image definition
├── docker-compose.yml         # Docker Compose config
├── requirements.txt           # Python dependencies
└── .env                       # Environment variables (create this)
```

## Requirements

- Python 3.13+
- Django 5.2.4
- PostgreSQL 15 (Docker)
- Docker & Docker Compose

## Installing psql Locally

### Windows

Download and install from: https://www.postgresql.org/download/windows/

### macOS

```bash
brew install postgresql
```

### Linux (Ubuntu/Debian)

```bash
sudo apt-get install postgresql-client
```

## Troubleshooting

### Port Already in Use

Change port in `docker-compose.yml`:

```yaml
ports:
  - "8006:8005"  # External:Internal
```

### Database Connection Error

Ensure PostgreSQL is running and credentials match `docker-compose.yml`

### Clear Docker Cache

```bash
docker system prune -a
```

### Rebuild Without Cache

```bash
docker-compose build --no-cache
```

## Production Deployment

1. Update `SECRET_KEY` in settings.py
2. Set `DEBUG=False`
3. Use Gunicorn instead of development server
4. Use environment variables for sensitive data
5. Set up proper CORS and ALLOWED_HOSTS
6. Use a production-grade database
7. Enable HTTPS/SSL

## Support

For issues, check Docker logs:

```bash
docker-compose logs -f web
docker-compose logs -f db
```

## License

See LICENSE file for details.
