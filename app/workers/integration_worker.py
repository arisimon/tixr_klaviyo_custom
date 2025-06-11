import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from celery.signals import task_failure, task_success, task_retry, worker_ready
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.core.logging import get_logger
from app.core.database import get_db
from app.core.redis import get_redis_client
from app.services.integration_service import IntegrationService
from app.models.database import (
    IntegrationRun, ProcessingQueue, CircuitBreakerState as CircuitBreakerStateModel,
    SystemHealth
)
from app.models.schemas import (
    IntegrationRequest, QueueStatus, CircuitBreakerState
)

logger = get_logger(__name__)


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Handler for worker startup."""
    logger.info("Worker ready", hostname=kwargs.get("sender").hostname)
    
    # Initialize worker state
    redis_client = get_redis_client()
    redis_client.set("worker:status", "ready")
    redis_client.set("worker:startup_time", datetime.utcnow().isoformat())


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Handler for task failures."""
    logger.error("Task failed", 
               task_id=task_id,
               task_name=sender.name if sender else "unknown",
               error=str(exception))


@task_success.connect
def on_task_success(sender=None, result=None, **kwargs):
    """Handler for task success."""
    logger.info("Task completed successfully", 
              task_name=sender.name if sender else "unknown")


@task_retry.connect
def on_task_retry(sender=None, request=None, reason=None, **kwargs):
    """Handler for task retries."""
    logger.warning("Task being retried", 
                 task_name=sender.name if sender else "unknown",
                 reason=str(reason))


@celery_app.task(bind=True, name="app.workers.integration_worker.process_integration")
def process_integration(self, correlation_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a complete integration run."""
    logger.info("Starting integration processing task", 
               correlation_id=correlation_id,
               task_id=self.request.id)
    
    # Create database session
    with get_db() as db:
        try:
            # Record integration run start
            integration_run = IntegrationRun(
                correlation_id=correlation_id,
                environment=request_data.get("environment", "production"),
                endpoint_type=request_data.get("tixr_config", {}).get("endpoint_type", "unknown"),
                status="running",
                configuration=request_data
            )
            db.add(integration_run)
            db.commit()
            
            # Process the integration
            integration_service = IntegrationService()
            result = integration_service.process_integration(correlation_id, request_data)
            
            # Update integration run record
            integration_run.status = result.get("status", "completed")
            integration_run.completed_at = datetime.utcnow()
            integration_run.total_items = result.get("total_items", 0)
            integration_run.successful_items = result.get("successful_items", 0)
            integration_run.failed_items = result.get("failed_items", 0)
            integration_run.error_message = result.get("error")
            integration_run.metrics = {
                "processing_time_seconds": result.get("processing_time_seconds", 0)
            }
            db.commit()
            
            logger.info("Integration processing completed", 
                       correlation_id=correlation_id,
                       status=result.get("status", "completed"))
            
            return result
            
        except Exception as e:
            db.rollback()
            
            # Record failure
            try:
                integration_run = db.query(IntegrationRun).filter_by(correlation_id=correlation_id).first()
                if integration_run:
                    integration_run.status = "failed"
                    integration_run.completed_at = datetime.utcnow()
                    integration_run.error_message = str(e)
                    db.commit()
            except Exception as db_error:
                logger.error("Failed to record integration failure", 
                           correlation_id=correlation_id,
                           error=str(db_error))
            
            logger.error("Integration processing failed", 
                        correlation_id=correlation_id,
                        error=str(e))
            
            # Retry the task if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                raise MaxRetriesExceededError(f"Integration processing failed after {self.max_retries} retries")


@celery_app.task(bind=True, name="app.workers.integration_worker.process_batch")
def process_batch(self, batch_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process a batch of items."""
    logger.info("Processing batch", 
               batch_id=batch_id,
               item_count=len(items))
    
    start_time = time.time()
    successful_items = 0
    failed_items = 0
    
    # Create database session
    with get_db() as db:
        try:
            # Process each item in the batch
            for item in items:
                item_id = item.get("id")
                
                try:
                    # Update item status to processing
                    queue_item = db.query(ProcessingQueue).filter_by(id=item_id).first()
                    if not queue_item:
                        logger.warning("Queue item not found", item_id=item_id)
                        failed_items += 1
                        continue
                    
                    queue_item.status = QueueStatus.PROCESSING.value
                    db.commit()
                    
                    # Process the item
                    result = process_queue_item(item, db)
                    
                    # Update item status based on result
                    queue_item.status = QueueStatus.COMPLETED.value if result.get("success") else QueueStatus.FAILED.value
                    queue_item.processed_at = datetime.utcnow()
                    queue_item.error_message = result.get("error")
                    db.commit()
                    
                    if result.get("success"):
                        successful_items += 1
                    else:
                        failed_items += 1
                        
                except Exception as e:
                    logger.error("Failed to process queue item", 
                               item_id=item_id,
                               error=str(e))
                    
                    # Update item status to failed
                    try:
                        queue_item = db.query(ProcessingQueue).filter_by(id=item_id).first()
                        if queue_item:
                            queue_item.status = QueueStatus.FAILED.value
                            queue_item.processed_at = datetime.utcnow()
                            queue_item.error_message = str(e)
                            queue_item.retry_count += 1
                            db.commit()
                    except Exception as db_error:
                        logger.error("Failed to update queue item status", 
                                   item_id=item_id,
                                   error=str(db_error))
                    
                    failed_items += 1
            
            processing_time = time.time() - start_time
            
            logger.info("Batch processing completed", 
                       batch_id=batch_id,
                       successful_items=successful_items,
                       failed_items=failed_items,
                       processing_time_seconds=processing_time)
            
            return {
                "batch_id": batch_id,
                "successful_items": successful_items,
                "failed_items": failed_items,
                "processing_time_seconds": processing_time
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            logger.error("Batch processing failed", 
                        batch_id=batch_id,
                        error=str(e),
                        processing_time_seconds=processing_time)
            
            # Retry the task if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                raise MaxRetriesExceededError(f"Batch processing failed after {self.max_retries} retries")


def process_queue_item(item: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Process a single queue item."""
    item_id = item.get("id")
    correlation_id = item.get("correlation_id")
    payload = item.get("payload", {})
    
    logger.info("Processing queue item", 
               item_id=item_id,
               correlation_id=correlation_id)
    
    try:
        # Process the item based on payload type
        if "event_data" in payload:
            # Process Klaviyo event
            integration_service = IntegrationService()
            klaviyo_service = integration_service.klaviyo_service
            
            result = klaviyo_service.track_event(
                payload["event_data"],
                correlation_id
            )
            
            return {
                "success": True,
                "result": result
            }
            
        elif "profile_data" in payload:
            # Process Klaviyo profile
            integration_service = IntegrationService()
            klaviyo_service = integration_service.klaviyo_service
            
            result = klaviyo_service.update_profile(
                payload["profile_data"],
                correlation_id
            )
            
            return {
                "success": True,
                "result": result
            }
            
        else:
            return {
                "success": False,
                "error": "Unknown payload type"
            }
            
    except Exception as e:
        logger.error("Failed to process queue item", 
                   item_id=item_id,
                   correlation_id=correlation_id,
                   error=str(e))
        
        return {
            "success": False,
            "error": str(e)
        }


@celery_app.task(name="app.workers.integration_worker.cleanup_failed_items")
def cleanup_failed_items() -> Dict[str, Any]:
    """Clean up failed items and retry if appropriate."""
    logger.info("Starting cleanup of failed items")
    
    start_time = time.time()
    retried_items = 0
    dead_letter_items = 0
    
    # Create database session
    with get_db() as db:
        try:
            # Find failed items that can be retried
            failed_items = db.query(ProcessingQueue).filter_by(
                status=QueueStatus.FAILED.value
            ).all()
            
            for item in failed_items:
                # Check if max retries exceeded
                if item.retry_count >= item.max_retries:
                    # Move to dead letter queue
                    item.status = QueueStatus.DEAD_LETTER.value
                    db.commit()
                    dead_letter_items += 1
                    
                    logger.info("Item moved to dead letter queue", 
                               item_id=item.id,
                               retry_count=item.retry_count,
                               max_retries=item.max_retries)
                else:
                    # Schedule for retry
                    item.status = QueueStatus.PENDING.value
                    item.retry_count += 1
                    item.scheduled_at = datetime.utcnow() + timedelta(
                        minutes=5 * (2 ** item.retry_count)  # Exponential backoff
                    )
                    db.commit()
                    retried_items += 1
                    
                    logger.info("Item scheduled for retry", 
                               item_id=item.id,
                               retry_count=item.retry_count,
                               scheduled_at=item.scheduled_at)
            
            processing_time = time.time() - start_time
            
            logger.info("Cleanup completed", 
                       retried_items=retried_items,
                       dead_letter_items=dead_letter_items,
                       processing_time_seconds=processing_time)
            
            return {
                "retried_items": retried_items,
                "dead_letter_items": dead_letter_items,
                "processing_time_seconds": processing_time
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            logger.error("Cleanup failed", 
                        error=str(e),
                        processing_time_seconds=processing_time)
            
            return {
                "error": str(e),
                "processing_time_seconds": processing_time
            }


@celery_app.task(name="app.workers.integration_worker.health_check_task")
def health_check_task() -> Dict[str, Any]:
    """Perform health check on all components."""
    logger.info("Starting health check task")
    
    start_time = time.time()
    
    # Create database session
    with get_db() as db:
        try:
            # Check integration service
            integration_service = IntegrationService()
            health_result = integration_service.health_check()
            
            # Record health check result
            system_health = SystemHealth(
                service_name="integration_service",
                health_status=health_result.get("status", "unhealthy"),
                response_time_ms=time.time() - start_time,
                additional_info=health_result
            )
            db.add(system_health)
            
            # Check circuit breaker states
            circuit_breakers = db.query(CircuitBreakerStateModel).all()
            for cb in circuit_breakers:
                # Check if open circuit breakers should transition to half-open
                if cb.state == CircuitBreakerState.OPEN.value:
                    last_failure = cb.last_failure_at
                    if last_failure and (datetime.utcnow() - last_failure).total_seconds() >= 60:
                        cb.state = CircuitBreakerState.HALF_OPEN.value
                        db.commit()
                        
                        logger.info("Circuit breaker transitioned to half-open", 
                                   service_name=cb.service_name)
            
            db.commit()
            
            processing_time = time.time() - start_time
            
            logger.info("Health check completed", 
                       status=health_result.get("status", "unhealthy"),
                       processing_time_seconds=processing_time)
            
            return {
                "status": health_result.get("status", "unhealthy"),
                "components": health_result.get("components", {}),
                "processing_time_seconds": processing_time
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            logger.error("Health check failed", 
                        error=str(e),
                        processing_time_seconds=processing_time)
            
            # Record failure
            try:
                system_health = SystemHealth(
                    service_name="integration_service",
                    health_status="unhealthy",
                    response_time_ms=processing_time * 1000,
                    error_message=str(e)
                )
                db.add(system_health)
                db.commit()
            except Exception as db_error:
                logger.error("Failed to record health check failure", 
                           error=str(db_error))
            
            return {
                "status": "unhealthy",
                "error": str(e),
                "processing_time_seconds": processing_time
            }


@celery_app.task(bind=True, name="app.workers.integration_worker.queue_processor")
def queue_processor(self) -> Dict[str, Any]:
    """Process items from the queue."""
    logger.info("Starting queue processor")
    
    start_time = time.time()
    processed_batches = 0
    total_items = 0
    
    # Create database session
    with get_db() as db:
        try:
            # Get pending items ordered by priority and scheduled time
            pending_items = db.query(ProcessingQueue).filter_by(
                status=QueueStatus.PENDING.value
            ).filter(
                ProcessingQueue.scheduled_at <= datetime.utcnow()
            ).order_by(
                ProcessingQueue.priority.desc(),
                ProcessingQueue.scheduled_at
            ).limit(1000).all()
            
            if not pending_items:
                logger.info("No pending items in queue")
                return {
                    "processed_batches": 0,
                    "total_items": 0,
                    "processing_time_seconds": time.time() - start_time
                }
            
            # Group items into batches
            batch_size = 100
            batches = []
            current_batch = []
            
            for item in pending_items:
                if len(current_batch) >= batch_size:
                    batches.append(current_batch)
                    current_batch = []
                
                current_batch.append({
                    "id": item.id,
                    "correlation_id": item.correlation_id,
                    "payload": item.payload
                })
            
            # Add the last batch if not empty
            if current_batch:
                batches.append(current_batch)
            
            # Process each batch
            for i, batch in enumerate(batches):
                batch_id = f"batch-{datetime.utcnow().isoformat()}-{i}"
                
                # Queue batch for processing
                process_batch.delay(batch_id, batch)
                
                processed_batches += 1
                total_items += len(batch)
            
            processing_time = time.time() - start_time
            
            logger.info("Queue processor completed", 
                       processed_batches=processed_batches,
                       total_items=total_items,
                       processing_time_seconds=processing_time)
            
            return {
                "processed_batches": processed_batches,
                "total_items": total_items,
                "processing_time_seconds": processing_time
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            logger.error("Queue processor failed", 
                        error=str(e),
                        processing_time_seconds=processing_time)
            
            # Retry the task if appropriate
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
            else:
                raise MaxRetriesExceededError(f"Queue processor failed after {self.max_retries} retries")

