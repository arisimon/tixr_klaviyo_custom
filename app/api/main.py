from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import uuid

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logging import get_logger
from app.services.integration_service import IntegrationService
from app.services.queue_service import QueueManager
from app.services.monitoring_service import MonitoringService
from app.workers.integration_worker import process_integration
from app.models.schemas import (
    IntegrationRequest, IntegrationResponse, HealthCheckResponse, MetricsResponse
)

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="TIXR-Klaviyo Integration API",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
integration_service = IntegrationService()
queue_manager = QueueManager()
monitoring_service = MonitoringService()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "TIXR-Klaviyo Integration API",
        "version": settings.app_version,
        "status": "running"
    }


@app.post("/api/v1/integrations", response_model=IntegrationResponse)
async def start_integration(
    request: IntegrationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session)
):
    """Start a new integration run."""
    
    logger.info("Received integration request", 
               endpoint_type=request.tixr_config.endpoint_type,
               environment=request.environment)
    
    try:
        # Start the integration
        response = await integration_service.start_integration(request)
        
        # Queue the integration for background processing
        if response.status == "pending":
            background_tasks.add_task(
                process_integration.delay,
                response.correlation_id,
                request.dict()
            )
        
        return response
        
    except Exception as e:
        logger.error("Failed to start integration", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/integrations/{correlation_id}")
async def get_integration_status(
    correlation_id: str,
    db: Session = Depends(get_db_session)
):
    """Get the status of an integration run."""
    
    try:
        status = await integration_service.get_integration_status(correlation_id)
        return status
        
    except Exception as e:
        logger.error("Failed to get integration status", 
                   correlation_id=correlation_id,
                   error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/integrations")
async def list_integrations(
    limit: int = 50,
    offset: int = 0,
    status: str = None,
    db: Session = Depends(get_db_session)
):
    """List integration runs with optional filtering."""
    
    try:
        from app.models.database import IntegrationRun
        
        query = db.query(IntegrationRun)
        
        if status:
            query = query.filter(IntegrationRun.status == status)
        
        total = query.count()
        integrations = query.offset(offset).limit(limit).all()
        
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "integrations": [
                {
                    "correlation_id": run.correlation_id,
                    "status": run.status,
                    "endpoint_type": run.endpoint_type,
                    "environment": run.environment,
                    "started_at": run.started_at.isoformat(),
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "total_items": run.total_items,
                    "successful_items": run.successful_items,
                    "failed_items": run.failed_items
                }
                for run in integrations
            ]
        }
        
    except Exception as e:
        logger.error("Failed to list integrations", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/queue/stats")
async def get_queue_stats():
    """Get queue statistics."""
    
    try:
        stats = queue_manager.get_all_queue_stats()
        return stats
        
    except Exception as e:
        logger.error("Failed to get queue stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/queue/{queue_name}/stats")
async def get_queue_stats_by_name(queue_name: str):
    """Get statistics for a specific queue."""
    
    try:
        stats = queue_manager.get_queue_stats(queue_name)
        return stats
        
    except Exception as e:
        logger.error("Failed to get queue stats", 
                   queue_name=queue_name,
                   error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/queue/{queue_name}/requeue")
async def requeue_failed_items(queue_name: str, max_age_hours: int = 24):
    """Requeue failed items in a specific queue."""
    
    try:
        requeued_count = queue_manager.requeue_failed_items(queue_name, max_age_hours)
        
        return {
            "queue_name": queue_name,
            "requeued_count": requeued_count,
            "message": f"Requeued {requeued_count} failed items"
        }
        
    except Exception as e:
        logger.error("Failed to requeue items", 
                   queue_name=queue_name,
                   error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/queue/{queue_name}/cleanup")
async def cleanup_old_items(queue_name: str, max_age_days: int = 30):
    """Clean up old items in a specific queue."""
    
    try:
        deleted_count = queue_manager.cleanup_old_items(queue_name, max_age_days)
        
        return {
            "queue_name": queue_name,
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} old items"
        }
        
    except Exception as e:
        logger.error("Failed to cleanup items", 
                   queue_name=queue_name,
                   error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/health", response_model=HealthCheckResponse)
async def health_check():
    """Comprehensive health check."""
    
    try:
        health_result = await integration_service.health_check()
        
        return HealthCheckResponse(
            service="integration_api",
            status=health_result.get("status", "unhealthy"),
            response_time_ms=0,  # This would be calculated by middleware
            timestamp=health_result.get("timestamp"),
            details=health_result.get("components")
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return HealthCheckResponse(
            service="integration_api",
            status="unhealthy",
            response_time_ms=0,
            timestamp=None,
            details={"error": str(e)}
        )


@app.get("/api/v1/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get system metrics."""
    
    try:
        metrics = monitoring_service.collect_system_metrics()
        
        integration_metrics = metrics.get('integration_metrics', {})
        queue_metrics = metrics.get('queue_metrics', {})
        
        return MetricsResponse(
            total_runs=integration_metrics.get('total_runs', 0),
            successful_runs=integration_metrics.get('successful_runs', 0),
            failed_runs=integration_metrics.get('failed_runs', 0),
            average_processing_time=integration_metrics.get('average_processing_time_seconds', 0),
            queue_depth=queue_metrics.get('totals', {}).get('total_pending', 0),
            error_rate=100 - integration_metrics.get('success_rate', 100),
            uptime_percentage=95.0  # This would be calculated from actual uptime data
        )
        
    except Exception as e:
        logger.error("Failed to get metrics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    
    try:
        # Collect latest metrics
        monitoring_service.collect_system_metrics()
        
        # Return Prometheus format
        return monitoring_service.get_prometheus_metrics()
        
    except Exception as e:
        logger.error("Failed to get Prometheus metrics", error=str(e))
        return f"# Error collecting metrics: {str(e)}\n"


@app.get("/api/v1/dashboard")
async def get_dashboard_data():
    """Get data for monitoring dashboard."""
    
    try:
        dashboard_data = monitoring_service.get_dashboard_data()
        return dashboard_data
        
    except Exception as e:
        logger.error("Failed to get dashboard data", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/test/tixr")
async def test_tixr_connection():
    """Test TIXR API connection."""
    
    try:
        health_result = await integration_service.tixr_service.health_check()
        return {
            "service": "tixr",
            "status": health_result.get("status", "unhealthy"),
            "response_time_ms": health_result.get("response_time_ms", 0),
            "details": health_result
        }
        
    except Exception as e:
        logger.error("TIXR connection test failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/test/klaviyo")
async def test_klaviyo_connection():
    """Test Klaviyo API connection."""
    
    try:
        health_result = await integration_service.klaviyo_service.health_check()
        return {
            "service": "klaviyo",
            "status": health_result.get("status", "unhealthy"),
            "response_time_ms": health_result.get("response_time_ms", 0),
            "details": health_result
        }
        
    except Exception as e:
        logger.error("Klaviyo connection test failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/config")
async def get_configuration():
    """Get current system configuration (non-sensitive)."""
    
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "environment": settings.environment,
        "debug": settings.debug,
        "tixr_base_url": settings.tixr_base_url,
        "klaviyo_base_url": settings.klaviyo_base_url,
        "queue_batch_size": settings.queue_batch_size,
        "queue_max_retries": settings.queue_max_retries,
        "circuit_breaker_failure_threshold": settings.circuit_breaker_failure_threshold,
        "circuit_breaker_recovery_timeout": settings.circuit_breaker_recovery_timeout
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Not Found",
        "message": "The requested resource was not found",
        "status_code": 404
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error("Internal server error", error=str(exc))
    return {
        "error": "Internal Server Error",
        "message": "An unexpected error occurred",
        "status_code": 500
    }


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Application startup."""
    logger.info("Starting TIXR-Klaviyo Integration API", 
               version=settings.app_version,
               environment=settings.environment)


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown."""
    logger.info("Shutting down TIXR-Klaviyo Integration API")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )

