from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class TixrEndpointType(str, Enum):
    """TIXR endpoint types."""
    EVENT_ORDERS = "event_orders"
    EVENT_DETAILS = "event_details"
    FAN_INFORMATION = "fan_information"
    FORM_SUBMISSIONS = "form_submissions"
    FAN_TRANSFERS = "fan_transfers"
    GROUPS = "groups"


class IntegrationStatus(str, Enum):
    """Integration run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueStatus(str, Enum):
    """Queue item status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class TixrConfiguration(BaseModel):
    """TIXR API configuration."""
    endpoint_type: TixrEndpointType
    group_id: int
    event_id: Optional[int] = None
    start_date: Optional[datetime] = None
    page_size: int = Field(default=50, ge=1, le=100)
    page_number: int = Field(default=1, ge=1)
    
    @validator('page_size')
    def validate_page_size(cls, v):
        if v > 100:
            return 100
        return v


class KlaviyoConfiguration(BaseModel):
    """Klaviyo integration configuration."""
    track_events: bool = True
    update_profiles: bool = True
    add_to_list: bool = False
    list_id: Optional[str] = None
    
    @validator('list_id')
    def validate_list_id(cls, v, values):
        if values.get('add_to_list') and not v:
            raise ValueError('list_id is required when add_to_list is True')
        return v


class IntegrationRequest(BaseModel):
    """Request model for starting an integration."""
    tixr_config: TixrConfiguration
    klaviyo_config: KlaviyoConfiguration
    environment: str = "production"
    priority: int = Field(default=0, ge=0, le=10)


class IntegrationResponse(BaseModel):
    """Response model for integration requests."""
    correlation_id: str
    status: IntegrationStatus
    message: str
    estimated_completion: Optional[datetime] = None


class QueueItem(BaseModel):
    """Queue item model."""
    id: Optional[int] = None
    correlation_id: str
    queue_name: str
    priority: int = 0
    payload: Dict[str, Any]
    status: QueueStatus = QueueStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class TixrOrderData(BaseModel):
    """TIXR order data model."""
    order_id: str
    event_id: str
    event_name: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    lastname: Optional[str] = None
    user_id: Optional[str] = None
    purchase_date: Optional[datetime] = None
    status: Optional[str] = None
    total: Optional[float] = None
    fulfillment_path: Optional[str] = None
    fulfillment_date: Optional[datetime] = None
    refund_amount: Optional[float] = None
    opt_in: Optional[bool] = None
    ref_id: Optional[str] = None
    ref_type: Optional[str] = None
    referrer: Optional[str] = None
    user_agent_type: Optional[str] = None
    geo_info: Optional[Dict[str, Any]] = None
    card_type: Optional[str] = None
    last_4: Optional[str] = None


class KlaviyoEventData(BaseModel):
    """Klaviyo event data model."""
    event: str
    properties: Dict[str, Any]
    customer_properties: Dict[str, Any]
    timestamp: Optional[datetime] = None


class KlaviyoProfileData(BaseModel):
    """Klaviyo profile data model."""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None


class TransformationResult(BaseModel):
    """Data transformation result."""
    success: bool
    klaviyo_event: Optional[KlaviyoEventData] = None
    klaviyo_profile: Optional[KlaviyoProfileData] = None
    validation_errors: List[str] = []
    processing_time_ms: Optional[float] = None


class HealthCheckResponse(BaseModel):
    """Health check response model."""
    service: str
    status: str
    response_time_ms: float
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


class MetricsResponse(BaseModel):
    """Metrics response model."""
    total_runs: int
    successful_runs: int
    failed_runs: int
    average_processing_time: float
    queue_depth: int
    error_rate: float
    uptime_percentage: float

