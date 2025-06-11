import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.logging import get_logger
from app.core.database import get_db
from app.core.redis import get_redis_client
from app.models.database import ProcessingQueue
from app.models.schemas import QueueItem, QueueStatus

logger = get_logger(__name__)


class QueueManager:
    """Advanced queue management with priority handling and batch optimization."""
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.default_queue = "default"
        self.priority_queues = ["high", "medium", "low"]
        
    def add_item(self, 
                 queue_name: str,
                 payload: Dict[str, Any],
                 priority: int = 0,
                 correlation_id: Optional[str] = None,
                 max_retries: int = 3,
                 scheduled_at: Optional[datetime] = None) -> str:
        """Add an item to the processing queue."""
        
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        if not scheduled_at:
            scheduled_at = datetime.utcnow()
        
        # Create database session
        with get_db() as db:
            try:
                # Create queue item
                queue_item = ProcessingQueue(
                    correlation_id=correlation_id,
                    queue_name=queue_name,
                    priority=priority,
                    payload=payload,
                    status=QueueStatus.PENDING.value,
                    max_retries=max_retries,
                    scheduled_at=scheduled_at
                )
                
                db.add(queue_item)
                db.commit()
                
                # Also add to Redis for real-time processing
                redis_key = f"queue:{queue_name}"
                redis_item = {
                    "id": queue_item.id,
                    "correlation_id": correlation_id,
                    "payload": payload,
                    "priority": priority,
                    "scheduled_at": scheduled_at.isoformat()
                }
                
                # Use priority as score (higher priority = lower score for ZRANGE)
                self.redis_client.zadd(redis_key, {json.dumps(redis_item): -priority})
                
                logger.info("Item added to queue", 
                           queue_name=queue_name,
                           item_id=queue_item.id,
                           correlation_id=correlation_id,
                           priority=priority)
                
                return str(queue_item.id)
                
            except Exception as e:
                db.rollback()
                logger.error("Failed to add item to queue", 
                           queue_name=queue_name,
                           correlation_id=correlation_id,
                           error=str(e))
                raise
    
    def add_batch(self, 
                  queue_name: str,
                  items: List[Dict[str, Any]],
                  correlation_id: Optional[str] = None) -> List[str]:
        """Add multiple items to the queue as a batch."""
        
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        item_ids = []
        
        # Create database session
        with get_db() as db:
            try:
                redis_items = []
                
                for i, item_data in enumerate(items):
                    payload = item_data.get("payload", {})
                    priority = item_data.get("priority", 0)
                    max_retries = item_data.get("max_retries", 3)
                    scheduled_at = item_data.get("scheduled_at", datetime.utcnow())
                    
                    # Create queue item
                    queue_item = ProcessingQueue(
                        correlation_id=f"{correlation_id}-{i}",
                        queue_name=queue_name,
                        priority=priority,
                        payload=payload,
                        status=QueueStatus.PENDING.value,
                        max_retries=max_retries,
                        scheduled_at=scheduled_at
                    )
                    
                    db.add(queue_item)
                    db.flush()  # Get the ID without committing
                    
                    item_ids.append(str(queue_item.id))
                    
                    # Prepare Redis item
                    redis_item = {
                        "id": queue_item.id,
                        "correlation_id": f"{correlation_id}-{i}",
                        "payload": payload,
                        "priority": priority,
                        "scheduled_at": scheduled_at.isoformat()
                    }
                    redis_items.append((json.dumps(redis_item), -priority))
                
                # Commit all database changes
                db.commit()
                
                # Add all items to Redis
                if redis_items:
                    redis_key = f"queue:{queue_name}"
                    self.redis_client.zadd(redis_key, dict(redis_items))
                
                logger.info("Batch added to queue", 
                           queue_name=queue_name,
                           item_count=len(items),
                           correlation_id=correlation_id)
                
                return item_ids
                
            except Exception as e:
                db.rollback()
                logger.error("Failed to add batch to queue", 
                           queue_name=queue_name,
                           correlation_id=correlation_id,
                           error=str(e))
                raise
    
    def get_next_items(self, 
                       queue_name: str,
                       limit: int = 10,
                       priority_threshold: int = 0) -> List[Dict[str, Any]]:
        """Get next items from the queue for processing."""
        
        redis_key = f"queue:{queue_name}"
        
        # Get items from Redis (ordered by priority)
        redis_items = self.redis_client.zrange(
            redis_key, 0, limit - 1, withscores=True
        )
        
        items = []
        item_keys_to_remove = []
        
        for item_data, score in redis_items:
            try:
                item = json.loads(item_data)
                
                # Check if item meets priority threshold
                if item.get("priority", 0) >= priority_threshold:
                    # Check if item is scheduled for processing
                    scheduled_at = datetime.fromisoformat(item["scheduled_at"])
                    if scheduled_at <= datetime.utcnow():
                        items.append(item)
                        item_keys_to_remove.append(item_data)
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Invalid item in queue", 
                             queue_name=queue_name,
                             item_data=item_data,
                             error=str(e))
                item_keys_to_remove.append(item_data)
        
        # Remove processed items from Redis
        if item_keys_to_remove:
            self.redis_client.zrem(redis_key, *item_keys_to_remove)
        
        logger.info("Retrieved items from queue", 
                   queue_name=queue_name,
                   item_count=len(items))
        
        return items
    
    def get_queue_stats(self, queue_name: str) -> Dict[str, Any]:
        """Get statistics for a queue."""
        
        # Create database session
        with get_db() as db:
            try:
                # Get counts by status
                pending_count = db.query(ProcessingQueue).filter_by(
                    queue_name=queue_name,
                    status=QueueStatus.PENDING.value
                ).count()
                
                processing_count = db.query(ProcessingQueue).filter_by(
                    queue_name=queue_name,
                    status=QueueStatus.PROCESSING.value
                ).count()
                
                completed_count = db.query(ProcessingQueue).filter_by(
                    queue_name=queue_name,
                    status=QueueStatus.COMPLETED.value
                ).count()
                
                failed_count = db.query(ProcessingQueue).filter_by(
                    queue_name=queue_name,
                    status=QueueStatus.FAILED.value
                ).count()
                
                dead_letter_count = db.query(ProcessingQueue).filter_by(
                    queue_name=queue_name,
                    status=QueueStatus.DEAD_LETTER.value
                ).count()
                
                # Get Redis queue size
                redis_key = f"queue:{queue_name}"
                redis_size = self.redis_client.zcard(redis_key)
                
                # Calculate average processing time for completed items
                completed_items = db.query(ProcessingQueue).filter(
                    and_(
                        ProcessingQueue.queue_name == queue_name,
                        ProcessingQueue.status == QueueStatus.COMPLETED.value,
                        ProcessingQueue.processed_at.isnot(None),
                        ProcessingQueue.created_at.isnot(None)
                    )
                ).limit(100).all()
                
                avg_processing_time = 0
                if completed_items:
                    total_time = sum([
                        (item.processed_at - item.created_at).total_seconds()
                        for item in completed_items
                    ])
                    avg_processing_time = total_time / len(completed_items)
                
                return {
                    "queue_name": queue_name,
                    "pending_count": pending_count,
                    "processing_count": processing_count,
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "dead_letter_count": dead_letter_count,
                    "redis_size": redis_size,
                    "total_items": pending_count + processing_count + completed_count + failed_count + dead_letter_count,
                    "average_processing_time_seconds": avg_processing_time,
                    "success_rate": (completed_count / max(1, completed_count + failed_count)) * 100
                }
                
            except Exception as e:
                logger.error("Failed to get queue stats", 
                           queue_name=queue_name,
                           error=str(e))
                return {
                    "queue_name": queue_name,
                    "error": str(e)
                }
    
    def update_item_status(self, 
                          item_id: int,
                          status: QueueStatus,
                          error_message: Optional[str] = None) -> bool:
        """Update the status of a queue item."""
        
        # Create database session
        with get_db() as db:
            try:
                queue_item = db.query(ProcessingQueue).filter_by(id=item_id).first()
                
                if not queue_item:
                    logger.warning("Queue item not found", item_id=item_id)
                    return False
                
                queue_item.status = status.value
                
                if status in [QueueStatus.COMPLETED, QueueStatus.FAILED, QueueStatus.DEAD_LETTER]:
                    queue_item.processed_at = datetime.utcnow()
                
                if error_message:
                    queue_item.error_message = error_message
                
                if status == QueueStatus.FAILED:
                    queue_item.retry_count += 1
                
                db.commit()
                
                logger.info("Queue item status updated", 
                           item_id=item_id,
                           status=status.value)
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error("Failed to update queue item status", 
                           item_id=item_id,
                           status=status.value,
                           error=str(e))
                return False
    
    def requeue_failed_items(self, 
                            queue_name: str,
                            max_age_hours: int = 24) -> int:
        """Requeue failed items that are eligible for retry."""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        requeued_count = 0
        
        # Create database session
        with get_db() as db:
            try:
                # Find failed items that can be retried
                failed_items = db.query(ProcessingQueue).filter(
                    and_(
                        ProcessingQueue.queue_name == queue_name,
                        ProcessingQueue.status == QueueStatus.FAILED.value,
                        ProcessingQueue.retry_count < ProcessingQueue.max_retries,
                        ProcessingQueue.created_at >= cutoff_time
                    )
                ).all()
                
                redis_items = []
                
                for item in failed_items:
                    # Update status and schedule for retry
                    item.status = QueueStatus.PENDING.value
                    item.retry_count += 1
                    item.scheduled_at = datetime.utcnow() + timedelta(
                        minutes=5 * (2 ** item.retry_count)  # Exponential backoff
                    )
                    
                    # Prepare for Redis
                    redis_item = {
                        "id": item.id,
                        "correlation_id": item.correlation_id,
                        "payload": item.payload,
                        "priority": item.priority,
                        "scheduled_at": item.scheduled_at.isoformat()
                    }
                    redis_items.append((json.dumps(redis_item), -item.priority))
                    
                    requeued_count += 1
                
                # Commit database changes
                db.commit()
                
                # Add items back to Redis
                if redis_items:
                    redis_key = f"queue:{queue_name}"
                    self.redis_client.zadd(redis_key, dict(redis_items))
                
                logger.info("Failed items requeued", 
                           queue_name=queue_name,
                           requeued_count=requeued_count)
                
                return requeued_count
                
            except Exception as e:
                db.rollback()
                logger.error("Failed to requeue items", 
                           queue_name=queue_name,
                           error=str(e))
                return 0
    
    def cleanup_old_items(self, 
                         queue_name: str,
                         max_age_days: int = 30) -> int:
        """Clean up old completed and failed items."""
        
        cutoff_time = datetime.utcnow() - timedelta(days=max_age_days)
        deleted_count = 0
        
        # Create database session
        with get_db() as db:
            try:
                # Delete old completed and dead letter items
                deleted_count = db.query(ProcessingQueue).filter(
                    and_(
                        ProcessingQueue.queue_name == queue_name,
                        or_(
                            ProcessingQueue.status == QueueStatus.COMPLETED.value,
                            ProcessingQueue.status == QueueStatus.DEAD_LETTER.value
                        ),
                        ProcessingQueue.created_at < cutoff_time
                    )
                ).delete()
                
                db.commit()
                
                logger.info("Old queue items cleaned up", 
                           queue_name=queue_name,
                           deleted_count=deleted_count)
                
                return deleted_count
                
            except Exception as e:
                db.rollback()
                logger.error("Failed to cleanup old items", 
                           queue_name=queue_name,
                           error=str(e))
                return 0
    
    def get_all_queue_stats(self) -> Dict[str, Any]:
        """Get statistics for all queues."""
        
        # Create database session
        with get_db() as db:
            try:
                # Get all unique queue names
                queue_names = db.query(ProcessingQueue.queue_name).distinct().all()
                queue_names = [name[0] for name in queue_names]
                
                stats = {}
                total_stats = {
                    "total_pending": 0,
                    "total_processing": 0,
                    "total_completed": 0,
                    "total_failed": 0,
                    "total_dead_letter": 0,
                    "total_items": 0
                }
                
                for queue_name in queue_names:
                    queue_stats = self.get_queue_stats(queue_name)
                    stats[queue_name] = queue_stats
                    
                    # Add to totals
                    total_stats["total_pending"] += queue_stats.get("pending_count", 0)
                    total_stats["total_processing"] += queue_stats.get("processing_count", 0)
                    total_stats["total_completed"] += queue_stats.get("completed_count", 0)
                    total_stats["total_failed"] += queue_stats.get("failed_count", 0)
                    total_stats["total_dead_letter"] += queue_stats.get("dead_letter_count", 0)
                    total_stats["total_items"] += queue_stats.get("total_items", 0)
                
                # Calculate overall success rate
                total_processed = total_stats["total_completed"] + total_stats["total_failed"]
                total_stats["overall_success_rate"] = (
                    (total_stats["total_completed"] / max(1, total_processed)) * 100
                )
                
                return {
                    "queues": stats,
                    "totals": total_stats,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                logger.error("Failed to get all queue stats", error=str(e))
                return {
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }

