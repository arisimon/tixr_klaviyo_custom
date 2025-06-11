from celery import Celery
from app.core.config import settings

# Create Celery instance
celery_app = Celery(
    "tixr_klaviyo_integration",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.integration_worker"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    task_routes={
        "app.workers.integration_worker.process_integration": {"queue": "integration"},
        "app.workers.integration_worker.process_batch": {"queue": "batch_processing"},
        "app.workers.integration_worker.cleanup_failed_items": {"queue": "cleanup"},
    },
    beat_schedule={
        "cleanup-failed-items": {
            "task": "app.workers.integration_worker.cleanup_failed_items",
            "schedule": 300.0,  # Every 5 minutes
        },
        "health-check": {
            "task": "app.workers.integration_worker.health_check_task",
            "schedule": 60.0,  # Every minute
        },
    },
)

