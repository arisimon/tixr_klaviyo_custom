from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, JSON, Float
from sqlalchemy.sql import func
from app.core.database import Base


class IntegrationRun(Base):
    """Model for tracking integration runs."""
    __tablename__ = "integration_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    correlation_id = Column(String(255), unique=True, index=True)
    environment = Column(String(50), nullable=False)
    endpoint_type = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_items = Column(Integer, default=0)
    successful_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    configuration = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)


class ProcessingQueue(Base):
    """Model for queue management."""
    __tablename__ = "processing_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    correlation_id = Column(String(255), index=True)
    queue_name = Column(String(100), nullable=False, index=True)
    priority = Column(Integer, default=0, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)


class CircuitBreakerState(Base):
    """Model for circuit breaker state persistence."""
    __tablename__ = "circuit_breaker_states"
    
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(100), unique=True, nullable=False, index=True)
    state = Column(String(20), nullable=False, default="closed")  # closed, open, half_open
    failure_count = Column(Integer, default=0)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DataTransformation(Base):
    """Model for tracking data transformations."""
    __tablename__ = "data_transformations"
    
    id = Column(Integer, primary_key=True, index=True)
    correlation_id = Column(String(255), index=True)
    source_system = Column(String(50), nullable=False)
    destination_system = Column(String(50), nullable=False)
    transformation_type = Column(String(100), nullable=False)
    source_data = Column(JSON, nullable=False)
    transformed_data = Column(JSON, nullable=False)
    validation_errors = Column(JSON, nullable=True)
    processing_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class APIMetrics(Base):
    """Model for API performance metrics."""
    __tablename__ = "api_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=False)
    request_size_bytes = Column(Integer, nullable=True)
    response_size_bytes = Column(Integer, nullable=True)
    correlation_id = Column(String(255), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemHealth(Base):
    """Model for system health monitoring."""
    __tablename__ = "system_health"
    
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    health_status = Column(String(20), nullable=False)  # healthy, unhealthy, degraded
    response_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    additional_info = Column(JSON, nullable=True)
    checked_at = Column(DateTime(timezone=True), server_default=func.now())


class Configuration(Base):
    """Model for system configuration management."""
    __tablename__ = "configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(255), unique=True, nullable=False, index=True)
    config_value = Column(JSON, nullable=False)
    environment = Column(String(50), nullable=False, index=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

