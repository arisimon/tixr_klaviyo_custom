import redis
from app.core.config import settings

# Redis connection pool
redis_pool = redis.ConnectionPool.from_url(
    settings.redis_url,
    max_connections=settings.redis_max_connections,
    decode_responses=True
)

# Redis client
redis_client = redis.Redis(connection_pool=redis_pool)


def get_redis_client():
    """Get Redis client."""
    return redis_client

