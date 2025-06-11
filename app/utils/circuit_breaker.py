import time
import asyncio
from typing import Callable, Any, Optional
from enum import Enum
from app.core.logging import get_logger
from app.core.redis import get_redis_client

logger = get_logger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker implementation with Redis persistence."""
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: int = 60,
                 service_name: str = "default"):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.service_name = service_name
        self.redis_client = get_redis_client()
        self.state_key = f"circuit_breaker:{service_name}:state"
        self.failure_count_key = f"circuit_breaker:{service_name}:failures"
        self.last_failure_key = f"circuit_breaker:{service_name}:last_failure"
        
    async def _get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state from Redis."""
        state = self.redis_client.get(self.state_key)
        if state:
            return CircuitBreakerState(state)
        return CircuitBreakerState.CLOSED
    
    async def _set_state(self, state: CircuitBreakerState):
        """Set circuit breaker state in Redis."""
        self.redis_client.set(self.state_key, state.value, ex=3600)  # 1 hour expiry
        
    async def _get_failure_count(self) -> int:
        """Get current failure count from Redis."""
        count = self.redis_client.get(self.failure_count_key)
        return int(count) if count else 0
    
    async def _increment_failure_count(self):
        """Increment failure count in Redis."""
        self.redis_client.incr(self.failure_count_key)
        self.redis_client.expire(self.failure_count_key, 3600)  # 1 hour expiry
        self.redis_client.set(self.last_failure_key, int(time.time()), ex=3600)
    
    async def _reset_failure_count(self):
        """Reset failure count in Redis."""
        self.redis_client.delete(self.failure_count_key)
        self.redis_client.delete(self.last_failure_key)
    
    async def _get_last_failure_time(self) -> Optional[float]:
        """Get last failure time from Redis."""
        timestamp = self.redis_client.get(self.last_failure_key)
        return float(timestamp) if timestamp else None
    
    async def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        last_failure = await self._get_last_failure_time()
        if not last_failure:
            return True
        
        return (time.time() - last_failure) >= self.recovery_timeout
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        state = await self._get_state()
        
        # Check if circuit is open
        if state == CircuitBreakerState.OPEN:
            if await self._should_attempt_reset():
                # Try to transition to half-open
                await self._set_state(CircuitBreakerState.HALF_OPEN)
                logger.info("Circuit breaker transitioning to half-open", 
                          service=self.service_name)
            else:
                # Circuit is still open, reject the call
                logger.warning("Circuit breaker is open, rejecting call", 
                             service=self.service_name)
                raise Exception(f"Circuit breaker is open for service: {self.service_name}")
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Success - reset failure count and close circuit if needed
            current_state = await self._get_state()
            if current_state in [CircuitBreakerState.HALF_OPEN, CircuitBreakerState.OPEN]:
                await self._set_state(CircuitBreakerState.CLOSED)
                await self._reset_failure_count()
                logger.info("Circuit breaker closed after successful call", 
                          service=self.service_name)
            
            return result
            
        except Exception as e:
            # Failure - increment count and potentially open circuit
            await self._increment_failure_count()
            failure_count = await self._get_failure_count()
            
            logger.warning("Circuit breaker recorded failure", 
                         service=self.service_name,
                         failure_count=failure_count,
                         error=str(e))
            
            if failure_count >= self.failure_threshold:
                await self._set_state(CircuitBreakerState.OPEN)
                logger.error("Circuit breaker opened due to failure threshold", 
                           service=self.service_name,
                           failure_count=failure_count)
            
            raise
    
    async def get_status(self) -> dict:
        """Get current circuit breaker status."""
        state = await self._get_state()
        failure_count = await self._get_failure_count()
        last_failure = await self._get_last_failure_time()
        
        return {
            "service_name": self.service_name,
            "state": state.value,
            "failure_count": failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": last_failure,
            "recovery_timeout": self.recovery_timeout
        }

