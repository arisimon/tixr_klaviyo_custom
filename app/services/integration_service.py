import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.logging import get_logger
from app.core.config import settings
from app.services.tixr_service import TixrService
from app.services.klaviyo_service import KlaviyoService
from app.services.transformation_service import DataTransformationService
from app.models.schemas import (
    IntegrationRequest, IntegrationResponse, IntegrationStatus,
    TixrConfiguration, KlaviyoConfiguration
)

logger = get_logger(__name__)


class IntegrationService:
    """Main integration service orchestrating TIXR to Klaviyo data flow."""
    
    def __init__(self):
        self.tixr_service = TixrService()
        self.klaviyo_service = KlaviyoService()
        self.transformation_service = DataTransformationService()
    
    def _generate_correlation_id(self) -> str:
        """Generate unique correlation ID for tracking."""
        return str(uuid.uuid4())
    
    async def start_integration(self, request: IntegrationRequest) -> IntegrationResponse:
        """Start a new integration run."""
        correlation_id = self._generate_correlation_id()
        
        logger.info("Starting integration run", 
                   correlation_id=correlation_id,
                   endpoint_type=request.tixr_config.endpoint_type,
                   environment=request.environment)
        
        try:
            # Validate configuration
            await self._validate_configuration(request, correlation_id)
            
            # Estimate completion time based on configuration
            estimated_completion = self._estimate_completion_time(request)
            
            # Queue the integration for processing
            await self._queue_integration(request, correlation_id)
            
            logger.info("Integration queued successfully", 
                       correlation_id=correlation_id)
            
            return IntegrationResponse(
                correlation_id=correlation_id,
                status=IntegrationStatus.PENDING,
                message="Integration queued for processing",
                estimated_completion=estimated_completion
            )
            
        except Exception as e:
            logger.error("Failed to start integration", 
                        correlation_id=correlation_id,
                        error=str(e))
            
            return IntegrationResponse(
                correlation_id=correlation_id,
                status=IntegrationStatus.FAILED,
                message=f"Failed to start integration: {str(e)}"
            )
    
    async def _validate_configuration(self, request: IntegrationRequest, correlation_id: str):
        """Validate integration configuration."""
        logger.info("Validating integration configuration", 
                   correlation_id=correlation_id)
        
        # Validate TIXR configuration
        if not settings.tixr_cpk or not settings.tixr_private_key:
            raise ValueError("TIXR credentials not configured")
        
        # Validate Klaviyo configuration
        if not settings.klaviyo_api_key:
            raise ValueError("Klaviyo API key not configured")
        
        # Validate endpoint-specific requirements
        tixr_config = request.tixr_config
        if tixr_config.endpoint_type in ["event_orders", "event_details"] and not tixr_config.event_id:
            raise ValueError(f"Event ID required for endpoint type: {tixr_config.endpoint_type}")
        
        # Validate Klaviyo list configuration
        klaviyo_config = request.klaviyo_config
        if klaviyo_config.add_to_list and not klaviyo_config.list_id:
            raise ValueError("List ID required when add_to_list is enabled")
        
        logger.info("Configuration validation passed", 
                   correlation_id=correlation_id)
    
    def _estimate_completion_time(self, request: IntegrationRequest) -> datetime:
        """Estimate completion time based on configuration."""
        # Base processing time estimates (in minutes)
        base_times = {
            "event_orders": 5,
            "event_details": 1,
            "fan_information": 10,
            "form_submissions": 3,
            "fan_transfers": 2,
            "groups": 1
        }
        
        base_time = base_times.get(request.tixr_config.endpoint_type, 5)
        
        # Add time based on page size (larger pages take longer)
        page_factor = request.tixr_config.page_size / 50  # 50 is default
        estimated_minutes = base_time * page_factor
        
        # Add queue delay based on priority
        queue_delay = max(1, 10 - request.priority)  # Higher priority = less delay
        
        total_minutes = estimated_minutes + queue_delay
        
        return datetime.utcnow() + timedelta(minutes=total_minutes)
    
    async def _queue_integration(self, request: IntegrationRequest, correlation_id: str):
        """Queue integration for background processing."""
        # This would typically use Celery or similar queue system
        # For now, we'll implement a simple Redis-based queue
        
        from app.core.redis import get_redis_client
        import json
        
        redis_client = get_redis_client()
        
        queue_item = {
            "correlation_id": correlation_id,
            "request": request.dict(),
            "created_at": datetime.utcnow().isoformat(),
            "priority": request.priority
        }
        
        # Add to priority queue (higher priority = lower score)
        queue_name = "integration_queue"
        redis_client.zadd(queue_name, {json.dumps(queue_item): -request.priority})
        
        logger.info("Integration added to queue", 
                   correlation_id=correlation_id,
                   queue_name=queue_name,
                   priority=request.priority)
    
    async def process_integration(self, correlation_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single integration run."""
        logger.info("Processing integration", 
                   correlation_id=correlation_id)
        
        start_time = datetime.utcnow()
        
        try:
            # Parse request data
            request = IntegrationRequest(**request_data)
            
            # Fetch data from TIXR
            logger.info("Fetching data from TIXR", 
                       correlation_id=correlation_id)
            
            tixr_data = await self.tixr_service.fetch_all_pages(
                request.tixr_config, 
                correlation_id
            )
            
            if not tixr_data:
                logger.warning("No data retrieved from TIXR", 
                             correlation_id=correlation_id)
                return {
                    "status": "completed",
                    "total_items": 0,
                    "successful_items": 0,
                    "failed_items": 0,
                    "message": "No data found"
                }
            
            # Transform data
            logger.info("Transforming data", 
                       correlation_id=correlation_id,
                       item_count=len(tixr_data))
            
            transformation_results = self.transformation_service.batch_transform(
                tixr_data,
                request.tixr_config.endpoint_type,
                correlation_id
            )
            
            # Process transformed data
            successful_items = 0
            failed_items = 0
            
            for i, result in enumerate(transformation_results):
                if not result.success:
                    failed_items += 1
                    logger.warning("Transformation failed for item", 
                                 item_index=i,
                                 errors=result.validation_errors,
                                 correlation_id=correlation_id)
                    continue
                
                try:
                    # Send to Klaviyo
                    await self._send_to_klaviyo(result, request.klaviyo_config, f"{correlation_id}-{i}")
                    successful_items += 1
                    
                except Exception as e:
                    failed_items += 1
                    logger.error("Failed to send to Klaviyo", 
                               item_index=i,
                               error=str(e),
                               correlation_id=correlation_id)
            
            # Calculate processing time
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info("Integration processing completed", 
                       correlation_id=correlation_id,
                       total_items=len(tixr_data),
                       successful_items=successful_items,
                       failed_items=failed_items,
                       processing_time_seconds=processing_time)
            
            return {
                "status": "completed",
                "total_items": len(tixr_data),
                "successful_items": successful_items,
                "failed_items": failed_items,
                "processing_time_seconds": processing_time,
                "message": f"Processed {successful_items}/{len(tixr_data)} items successfully"
            }
            
        except Exception as e:
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.error("Integration processing failed", 
                        correlation_id=correlation_id,
                        error=str(e),
                        processing_time_seconds=processing_time)
            
            return {
                "status": "failed",
                "error": str(e),
                "processing_time_seconds": processing_time
            }
    
    async def _send_to_klaviyo(self, 
                              transformation_result, 
                              klaviyo_config: KlaviyoConfiguration, 
                              correlation_id: str):
        """Send transformed data to Klaviyo."""
        
        # Track event if configured and available
        if klaviyo_config.track_events and transformation_result.klaviyo_event:
            await self.klaviyo_service.track_event(
                transformation_result.klaviyo_event,
                correlation_id
            )
        
        # Update profile if configured and available
        if klaviyo_config.update_profiles and transformation_result.klaviyo_profile:
            await self.klaviyo_service.update_profile(
                transformation_result.klaviyo_profile,
                correlation_id
            )
        
        # Add to list if configured
        if (klaviyo_config.add_to_list and 
            klaviyo_config.list_id and 
            transformation_result.klaviyo_profile):
            
            await self.klaviyo_service.add_to_list(
                transformation_result.klaviyo_profile.email,
                klaviyo_config.list_id,
                correlation_id
            )
    
    async def get_integration_status(self, correlation_id: str) -> Dict[str, Any]:
        """Get status of an integration run."""
        # This would typically query the database for run status
        # For now, return a placeholder
        
        return {
            "correlation_id": correlation_id,
            "status": "running",
            "message": "Integration status tracking not yet implemented"
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        logger.info("Performing integration service health check")
        
        health_status = {
            "service": "integration",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {}
        }
        
        try:
            # Check TIXR service
            tixr_health = await self.tixr_service.health_check()
            health_status["components"]["tixr"] = tixr_health
            
            # Check Klaviyo service
            klaviyo_health = await self.klaviyo_service.health_check()
            health_status["components"]["klaviyo"] = klaviyo_health
            
            # Determine overall status
            component_statuses = [
                tixr_health.get("status", "unhealthy"),
                klaviyo_health.get("status", "unhealthy")
            ]
            
            if all(status == "healthy" for status in component_statuses):
                health_status["status"] = "healthy"
            elif any(status == "healthy" for status in component_statuses):
                health_status["status"] = "degraded"
            else:
                health_status["status"] = "unhealthy"
            
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["error"] = str(e)
            
            logger.error("Health check failed", error=str(e))
        
        return health_status

