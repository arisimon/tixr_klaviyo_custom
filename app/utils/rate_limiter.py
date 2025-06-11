import time
import asyncio
from typing import Optional
from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter with Redis backend."""
    
    def __init__(self, 
                 max_requests: int,
                 time_window: int = 60,
                 service_name: str = "default"):
        self.max_requests = max_requests
        self.time_window = time_window
        self.service_name = service_name
        self.redis_client = get_redis_client()
        self.bucket_key = f"rate_limiter:{service_name}:bucket"
        self.last_refill_key = f"rate_limiter:{service_name}:last_refill"
        
    async def _get_current_tokens(self) -> int:
        """Get current token count from Redis."""
        tokens = self.redis_client.get(self.bucket_key)
        return int(tokens) if tokens else self.max_requests
    
    async def _set_tokens(self, tokens: int):
        """Set token count in Redis."""
        self.redis_client.set(self.bucket_key, tokens, ex=self.time_window * 2)
    
    async def _get_last_refill(self) -> float:
        """Get last refill time from Redis."""
        timestamp = self.redis_client.get(self.last_refill_key)
        return float(timestamp) if timestamp else time.time()
    
    async def _set_last_refill(self, timestamp: float):
        """Set last refill time in Redis."""
        self.redis_client.set(self.last_refill_key, timestamp, ex=self.time_window * 2)
    
    async def _refill_tokens(self):
        """Refill tokens based on elapsed time."""
        current_time = time.time()
        last_refill = await self._get_last_refill()
        current_tokens = await self._get_current_tokens()
        
        # Calculate how many tokens to add based on elapsed time
        elapsed_time = current_time - last_refill
        tokens_to_add = int((elapsed_time / self.time_window) * self.max_requests)
        
        if tokens_to_add > 0:
            # Add tokens up to the maximum
            new_token_count = min(current_tokens + tokens_to_add, self.max_requests)
            await self._set_tokens(new_token_count)
            await self._set_last_refill(current_time)
            
            logger.debug("Refilled rate limiter tokens", 
                        service=self.service_name,
                        tokens_added=tokens_to_add,
                        new_count=new_token_count)
    
    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens from the bucket."""
        await self._refill_tokens()
        
        current_tokens = await self._get_current_tokens()
        
        if current_tokens >= tokens:
            # Consume tokens
            await self._set_tokens(current_tokens - tokens)
            
            logger.debug("Rate limiter tokens acquired", 
                        service=self.service_name,
                        tokens_requested=tokens,
                        tokens_remaining=current_tokens - tokens)
            
            return True
        else:
            # Not enough tokens available
            logger.warning("Rate limiter tokens exhausted", 
                         service=self.service_name,
                         tokens_requested=tokens,
                         tokens_available=current_tokens)
            
            return False
    
    async def wait_for_tokens(self, tokens: int = 1, max_wait: float = 60.0):
        """Wait until tokens are available or timeout."""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if await self.acquire(tokens):
                return
            
            # Wait a short time before trying again
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Rate limiter timeout after {max_wait} seconds for service: {self.service_name}")
    
    async def get_status(self) -> dict:
        """Get current rate limiter status."""
        await self._refill_tokens()
        
        current_tokens = await self._get_current_tokens()
        last_refill = await self._get_last_refill()
        
        return {
            "service_name": self.service_name,
            "current_tokens": current_tokens,
            "max_tokens": self.max_requests,
            "time_window": self.time_window,
            "last_refill": last_refill,
            "utilization_percentage": ((self.max_requests - current_tokens) / self.max_requests) * 100
        }

