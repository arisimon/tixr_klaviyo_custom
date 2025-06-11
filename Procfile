# Procfile for Railway deployment
# This file tells Railway how to run different processes

# Main web application
web: python -m uvicorn app.api.main:app --host 0.0.0.0 --port $PORT --workers 1

# Background worker (if deploying as separate service)
worker: python -m celery worker -A app.workers.celery_app --loglevel=info --concurrency=2

# Celery beat scheduler (if deploying as separate service)
beat: python -m celery beat -A app.workers.celery_app --loglevel=info

