import hmac
import hashlib
import time
from urllib.parse import urlencode
from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import TixrConfiguration, TixrOrderData, TixrEndpointType
from app.utils.circuit_breaker import CircuitBreaker
from app.utils.rate_limiter import RateLimiter

logger = get_logger(__name__)


class TixrService:
    """Service for interacting with TIXR API."""
    
    def __init__(self):
        self.base_url = settings.tixr_base_url
        self.cpk = settings.tixr_cpk
        self.private_key = settings.tixr_private_key
        self.timeout = settings.tixr_timeout
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout=settings.circuit_breaker_recovery_timeout,
            service_name="tixr_api"
        )
        self.rate_limiter = RateLimiter(
            max_requests=settings.tixr_rate_limit,
            time_window=60  # 1 minute
        )
        
    def _generate_hmac_hash(self, params: Dict[str, Any]) -> str:
        """Generate HMAC-SHA256 hash for TIXR authentication."""
        # Sort parameters alphabetically
        sorted_params = dict(sorted(params.items()))
        
        # Create parameter string with URL encoding
        param_string = urlencode(sorted_params)
        
        # Generate HMAC-SHA256 hash
        signature = hmac.new(
            self.private_key.encode('utf-8'),
            param_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        logger.info("Generated HMAC hash", 
                   param_count=len(params),
                   param_string_length=len(param_string))
        
        return signature
    
    def _build_auth_params(self, additional_params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build authentication parameters for TIXR API."""
        timestamp = int(time.time() * 1000)  # milliseconds
        
        params = {
            'cpk': self.cpk,
            'timestamp': timestamp
        }
        
        if additional_params:
            params.update(additional_params)
        
        # Generate hash with all parameters
        params['hash'] = self._generate_hmac_hash(params)
        
        return params
    
    def _build_endpoint_url(self, endpoint_type: TixrEndpointType, config: TixrConfiguration) -> str:
        """Build the appropriate endpoint URL based on type."""
        base_path = f"{self.base_url}/v1"
        
        if endpoint_type == TixrEndpointType.EVENT_ORDERS:
            return f"{base_path}/groups/{config.group_id}/events/{config.event_id}/orders"
        elif endpoint_type == TixrEndpointType.EVENT_DETAILS:
            return f"{base_path}/groups/{config.group_id}/events/{config.event_id}"
        elif endpoint_type == TixrEndpointType.FAN_INFORMATION:
            return f"{base_path}/groups/{config.group_id}/fans"
        elif endpoint_type == TixrEndpointType.FORM_SUBMISSIONS:
            return f"{base_path}/groups/{config.group_id}/forms/submissions"
        elif endpoint_type == TixrEndpointType.FAN_TRANSFERS:
            return f"{base_path}/groups/{config.group_id}/transfers"
        elif endpoint_type == TixrEndpointType.GROUPS:
            return f"{base_path}/groups/{config.group_id}"
        else:
            raise ValueError(f"Unsupported endpoint type: {endpoint_type}")
    
    async def _make_request(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make authenticated request to TIXR API with circuit breaker and rate limiting."""
        
        # Check rate limit
        await self.rate_limiter.acquire()
        
        # Use circuit breaker
        async def _request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info("Making TIXR API request", url=url, param_count=len(params))
                
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error("TIXR API error", 
                               status_code=response.status_code,
                               response_text=response.text)
                    raise httpx.HTTPStatusError(
                        f"TIXR API returned {response.status_code}",
                        request=response.request,
                        response=response
                    )
                
                data = response.json()
                logger.info("TIXR API request successful", 
                          response_size=len(response.content))
                
                return data
        
        return await self.circuit_breaker.call(_request)
    
    async def fetch_data(self, config: TixrConfiguration, correlation_id: str) -> List[Dict[str, Any]]:
        """Fetch data from TIXR API based on configuration."""
        logger.info("Starting TIXR data fetch", 
                   endpoint_type=config.endpoint_type,
                   correlation_id=correlation_id)
        
        url = self._build_endpoint_url(config.endpoint_type, config)
        
        # Build request parameters
        request_params = {
            'group_id': config.group_id,
            'page_size': config.page_size,
            'page_number': config.page_number
        }
        
        # Add endpoint-specific parameters
        if config.endpoint_type in [TixrEndpointType.EVENT_ORDERS, TixrEndpointType.EVENT_DETAILS]:
            if config.event_id:
                request_params['event_id'] = config.event_id
        
        if config.endpoint_type == TixrEndpointType.EVENT_ORDERS and config.start_date:
            request_params['start_date'] = config.start_date.isoformat()
        
        # Add authentication parameters
        auth_params = self._build_auth_params(request_params)
        
        try:
            # Make the API request
            response_data = await self._make_request(url, auth_params)
            
            # Extract data based on response structure
            if isinstance(response_data, dict):
                # Handle paginated responses
                if 'data' in response_data:
                    items = response_data['data']
                elif 'orders' in response_data:
                    items = response_data['orders']
                elif 'events' in response_data:
                    items = response_data['events']
                else:
                    items = [response_data]  # Single item response
            elif isinstance(response_data, list):
                items = response_data
            else:
                items = []
            
            logger.info("TIXR data fetch completed", 
                       item_count=len(items),
                       correlation_id=correlation_id)
            
            return items
            
        except Exception as e:
            logger.error("TIXR data fetch failed", 
                        error=str(e),
                        correlation_id=correlation_id)
            raise
    
    async def fetch_all_pages(self, config: TixrConfiguration, correlation_id: str) -> List[Dict[str, Any]]:
        """Fetch all pages of data from TIXR API."""
        all_items = []
        current_page = config.page_number
        
        logger.info("Starting multi-page TIXR data fetch", 
                   correlation_id=correlation_id)
        
        while True:
            # Update page number for current request
            page_config = config.copy()
            page_config.page_number = current_page
            
            try:
                items = await self.fetch_data(page_config, correlation_id)
                
                if not items:
                    # No more data
                    break
                
                all_items.extend(items)
                
                # Check if we got a full page (indicating more data might be available)
                if len(items) < config.page_size:
                    # Last page
                    break
                
                current_page += 1
                
                # Safety check to prevent infinite loops
                if current_page > 1000:  # Arbitrary large number
                    logger.warning("Reached maximum page limit", 
                                 current_page=current_page,
                                 correlation_id=correlation_id)
                    break
                    
            except Exception as e:
                logger.error("Failed to fetch page", 
                           page=current_page,
                           error=str(e),
                           correlation_id=correlation_id)
                # Don't fail the entire operation for a single page failure
                break
        
        logger.info("Multi-page TIXR data fetch completed", 
                   total_items=len(all_items),
                   pages_fetched=current_page - config.page_number + 1,
                   correlation_id=correlation_id)
        
        return all_items
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on TIXR API."""
        start_time = time.time()
        
        try:
            # Simple health check - try to access a basic endpoint
            url = f"{self.base_url}/v1/ping"  # Assuming TIXR has a ping endpoint
            
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url)
                
            response_time = (time.time() - start_time) * 1000
            
            return {
                'status': 'healthy' if response.status_code == 200 else 'unhealthy',
                'response_time_ms': response_time,
                'status_code': response.status_code
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return {
                'status': 'unhealthy',
                'response_time_ms': response_time,
                'error': str(e)
            }

