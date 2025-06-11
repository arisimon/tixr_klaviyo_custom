import time
from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import KlaviyoEventData, KlaviyoProfileData, KlaviyoConfiguration
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.rate_limiter import RateLimiter

logger = get_logger(__name__)


class KlaviyoService:
    """Service for interacting with Klaviyo API."""
    
    def __init__(self):
        self.base_url = settings.klaviyo_base_url
        self.api_key = settings.klaviyo_api_key
        self.timeout = settings.klaviyo_timeout
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout=settings.circuit_breaker_recovery_timeout,
            service_name="klaviyo_api"
        )
        self.rate_limiter = RateLimiter(
            max_requests=settings.klaviyo_rate_limit,
            time_window=60  # 1 minute
        )
    
    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for Klaviyo API requests."""
        return {
            'Authorization': f'Klaviyo-API-Key {self.api_key}',
            'Content-Type': 'application/json',
            'revision': '2024-10-15'
        }
    
    async def _make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Klaviyo API with circuit breaker and rate limiting."""
        
        # Check rate limit
        await self.rate_limiter.acquire()
        
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_headers()
        
        async def _request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info("Making Klaviyo API request", 
                          method=method, 
                          endpoint=endpoint,
                          has_data=data is not None)
                
                if method.upper() == 'GET':
                    response = await client.get(url, headers=headers, params=data)
                elif method.upper() == 'POST':
                    response = await client.post(url, headers=headers, json=data)
                elif method.upper() == 'PUT':
                    response = await client.put(url, headers=headers, json=data)
                elif method.upper() == 'PATCH':
                    response = await client.patch(url, headers=headers, json=data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                if response.status_code not in [200, 201, 202]:
                    logger.error("Klaviyo API error", 
                               status_code=response.status_code,
                               response_text=response.text)
                    raise httpx.HTTPStatusError(
                        f"Klaviyo API returned {response.status_code}",
                        request=response.request,
                        response=response
                    )
                
                result = response.json() if response.content else {}
                logger.info("Klaviyo API request successful", 
                          status_code=response.status_code,
                          response_size=len(response.content))
                
                return result
        
        return await self.circuit_breaker.call(_request)
    
    async def track_event(self, event_data: KlaviyoEventData, correlation_id: str) -> Dict[str, Any]:
        """Track an event in Klaviyo."""
        logger.info("Tracking Klaviyo event", 
                   event_name=event_data.event,
                   correlation_id=correlation_id)
        
        # Build event payload according to Klaviyo V3 API format
        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {
                        "data": {
                            "type": "metric",
                            "attributes": {
                                "name": event_data.event
                            }
                        }
                    },
                    "properties": event_data.properties,
                    "profile": {
                        "data": {
                            "type": "profile",
                            "attributes": event_data.customer_properties
                        }
                    }
                }
            }
        }
        
        if event_data.timestamp:
            payload["data"]["attributes"]["time"] = event_data.timestamp.isoformat()
        
        try:
            result = await self._make_request('POST', 'events', payload)
            
            logger.info("Klaviyo event tracked successfully", 
                       event_name=event_data.event,
                       correlation_id=correlation_id)
            
            return result
            
        except Exception as e:
            logger.error("Failed to track Klaviyo event", 
                        event_name=event_data.event,
                        error=str(e),
                        correlation_id=correlation_id)
            raise
    
    async def update_profile(self, profile_data: KlaviyoProfileData, correlation_id: str) -> Dict[str, Any]:
        """Update or create a profile in Klaviyo."""
        logger.info("Updating Klaviyo profile", 
                   email=profile_data.email,
                   correlation_id=correlation_id)
        
        # Build profile payload according to Klaviyo V3 API format
        attributes = {
            "email": profile_data.email
        }
        
        if profile_data.first_name:
            attributes["first_name"] = profile_data.first_name
        
        if profile_data.last_name:
            attributes["last_name"] = profile_data.last_name
        
        if profile_data.phone_number:
            attributes["phone_number"] = profile_data.phone_number
        
        if profile_data.properties:
            attributes.update(profile_data.properties)
        
        payload = {
            "data": {
                "type": "profile",
                "attributes": attributes
            }
        }
        
        try:
            result = await self._make_request('POST', 'profiles', payload)
            
            logger.info("Klaviyo profile updated successfully", 
                       email=profile_data.email,
                       correlation_id=correlation_id)
            
            return result
            
        except Exception as e:
            logger.error("Failed to update Klaviyo profile", 
                        email=profile_data.email,
                        error=str(e),
                        correlation_id=correlation_id)
            raise
    
    async def add_to_list(self, email: str, list_id: str, correlation_id: str) -> Dict[str, Any]:
        """Add a profile to a Klaviyo list."""
        logger.info("Adding profile to Klaviyo list", 
                   email=email,
                   list_id=list_id,
                   correlation_id=correlation_id)
        
        # Build list subscription payload according to Klaviyo V3 API format
        payload = {
            "data": {
                "type": "profile-subscription-bulk-create-job",
                "attributes": {
                    "profiles": {
                        "data": [{
                            "type": "profile",
                            "attributes": {
                                "email": email
                            }
                        }]
                    },
                    "list": {
                        "data": {
                            "type": "list",
                            "id": list_id
                        }
                    }
                }
            }
        }
        
        try:
            result = await self._make_request('POST', 'profile-subscription-bulk-create-job', payload)
            
            logger.info("Profile added to Klaviyo list successfully", 
                       email=email,
                       list_id=list_id,
                       correlation_id=correlation_id)
            
            return result
            
        except Exception as e:
            logger.error("Failed to add profile to Klaviyo list", 
                        email=email,
                        list_id=list_id,
                        error=str(e),
                        correlation_id=correlation_id)
            raise
    
    async def bulk_track_events(self, events: List[KlaviyoEventData], correlation_id: str) -> Dict[str, Any]:
        """Track multiple events in Klaviyo using bulk API."""
        logger.info("Bulk tracking Klaviyo events", 
                   event_count=len(events),
                   correlation_id=correlation_id)
        
        # Build bulk events payload
        event_data = []
        for event in events:
            event_payload = {
                "type": "event",
                "attributes": {
                    "metric": {
                        "data": {
                            "type": "metric",
                            "attributes": {
                                "name": event.event
                            }
                        }
                    },
                    "properties": event.properties,
                    "profile": {
                        "data": {
                            "type": "profile",
                            "attributes": event.customer_properties
                        }
                    }
                }
            }
            
            if event.timestamp:
                event_payload["attributes"]["time"] = event.timestamp.isoformat()
            
            event_data.append(event_payload)
        
        payload = {
            "data": event_data
        }
        
        try:
            result = await self._make_request('POST', 'events', payload)
            
            logger.info("Klaviyo bulk events tracked successfully", 
                       event_count=len(events),
                       correlation_id=correlation_id)
            
            return result
            
        except Exception as e:
            logger.error("Failed to bulk track Klaviyo events", 
                        event_count=len(events),
                        error=str(e),
                        correlation_id=correlation_id)
            raise
    
    async def bulk_update_profiles(self, profiles: List[KlaviyoProfileData], correlation_id: str) -> Dict[str, Any]:
        """Update multiple profiles in Klaviyo using bulk API."""
        logger.info("Bulk updating Klaviyo profiles", 
                   profile_count=len(profiles),
                   correlation_id=correlation_id)
        
        # Build bulk profiles payload
        profile_data = []
        for profile in profiles:
            attributes = {
                "email": profile.email
            }
            
            if profile.first_name:
                attributes["first_name"] = profile.first_name
            
            if profile.last_name:
                attributes["last_name"] = profile.last_name
            
            if profile.phone_number:
                attributes["phone_number"] = profile.phone_number
            
            if profile.properties:
                attributes.update(profile.properties)
            
            profile_data.append({
                "type": "profile",
                "attributes": attributes
            })
        
        payload = {
            "data": profile_data
        }
        
        try:
            result = await self._make_request('POST', 'profiles', payload)
            
            logger.info("Klaviyo bulk profiles updated successfully", 
                       profile_count=len(profiles),
                       correlation_id=correlation_id)
            
            return result
            
        except Exception as e:
            logger.error("Failed to bulk update Klaviyo profiles", 
                        profile_count=len(profiles),
                        error=str(e),
                        correlation_id=correlation_id)
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Klaviyo API."""
        start_time = time.time()
        
        try:
            # Simple health check - try to access metrics endpoint
            result = await self._make_request('GET', 'metrics', {'page[size]': 1})
            
            response_time = (time.time() - start_time) * 1000
            
            return {
                'status': 'healthy',
                'response_time_ms': response_time,
                'api_accessible': True
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return {
                'status': 'unhealthy',
                'response_time_ms': response_time,
                'error': str(e)
            }

