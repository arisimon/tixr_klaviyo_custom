from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # Application settings
    app_name: str = "TIXR-Klaviyo Integration"
    app_version: str = "1.0.0"
    environment: str = "production"
    debug: bool = False
    
    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = int(os.getenv("PORT", "8000"))  # Railway uses PORT env var
    
    # Supabase Database settings
    database_url: str = ""  # Will be set from Supabase connection string
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Redis settings (Railway Redis or Upstash)
    redis_url: str = ""  # Will be set from Railway Redis URL
    redis_max_connections: int = 20
    
    # TIXR API settings
    tixr_base_url: str = "https://studio.tixr.com"
    tixr_cpk: str = ""
    tixr_private_key: str = ""
    tixr_timeout: int = 30
    tixr_rate_limit: int = 100
    
    # Klaviyo API settings
    klaviyo_base_url: str = "https://a.klaviyo.com/api"
    klaviyo_api_key: str = ""
    klaviyo_timeout: int = 30
    klaviyo_rate_limit: int = 150
    
    # Celery settings (using Redis)
    celery_broker_url: str = ""  # Will use redis_url
    celery_result_backend: str = ""  # Will use redis_url
    
    # Queue settings
    queue_default_retry_delay: int = 60
    queue_max_retries: int = 3
    queue_batch_size: int = 100
    
    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    
    # Monitoring settings
    prometheus_port: int = 9090
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Security settings
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"
    
    # Railway specific settings
    railway_environment: str = os.getenv("RAILWAY_ENVIRONMENT", "production")
    railway_project_id: str = os.getenv("RAILWAY_PROJECT_ID", "")
    railway_service_id: str = os.getenv("RAILWAY_SERVICE_ID", "")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Auto-configure Celery URLs from Redis URL if not explicitly set
        if self.redis_url and not self.celery_broker_url:
            self.celery_broker_url = self.redis_url + "/1"
        if self.redis_url and not self.celery_result_backend:
            self.celery_result_backend = self.redis_url + "/2"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

