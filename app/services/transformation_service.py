from typing import Dict, Any, List, Optional
import time
from datetime import datetime
from app.core.logging import get_logger
from app.models.schemas import (
    TixrOrderData, KlaviyoEventData, KlaviyoProfileData, 
    TransformationResult, TixrEndpointType
)

logger = get_logger(__name__)


class DataTransformationService:
    """Service for transforming data between TIXR and Klaviyo formats."""
    
    def __init__(self):
        self.endpoint_mappings = self._initialize_mappings()
    
    def _initialize_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Initialize data mapping configurations for different endpoints."""
        return {
            TixrEndpointType.EVENT_ORDERS: {
                "event": {
                    "name": "Ordered Ticket",
                    "properties": {
                        "$event_id": "order_id",
                        "$value": "total",
                        "OrderId": "order_id",
                        "EventId": "event_id",
                        "EventName": "event_name",
                        "OrderDate": "purchase_date",
                        "OrderStatus": "status",
                        "OrderTotal": "total",
                        "FulfillmentPath": "fulfillment_path",
                        "FulfillmentDate": "fulfillment_date",
                        "RefundAmount": "refund_amount",
                        "OptIn": "opt_in",
                        "RefId": "ref_id",
                        "RefType": "ref_type",
                        "Referrer": "referrer",
                        "UserAgentType": "user_agent_type",
                        "GeoCity": "geo_info.city",
                        "GeoState": "geo_info.state",
                        "GeoPostal": "geo_info.postal_code",
                        "GeoCountry": "geo_info.country_code",
                        "GeoLat": "geo_info.latitude",
                        "GeoLng": "geo_info.longitude",
                        "CardType": "card_type",
                        "Last4": "last_4"
                    },
                    "customer_properties": {
                        "$email": "email",
                        "$first_name": "first_name",
                        "$last_name": "lastname",
                        "$user_id": "user_id"
                    }
                },
                "profile": {
                    "$email": "email",
                    "$first_name": "first_name",
                    "$last_name": "lastname",
                    "$phone_number": None,  # Not available in TIXR
                    "UserId": "user_id",
                    "City": "geo_info.city",
                    "State": "geo_info.state",
                    "Postal": "geo_info.postal_code",
                    "Country": "geo_info.country_code"
                }
            },
            TixrEndpointType.EVENT_DETAILS: {
                "event": {
                    "name": "Viewed Event",
                    "properties": {
                        "$event_id": "id",
                        "EventId": "id",
                        "EventName": "name",
                        "EventDescription": "description",
                        "EventStartDate": "start_date",
                        "EventEndDate": "end_date",
                        "EventVenue": "venue.name",
                        "EventVenueAddress": "venue.address",
                        "EventStatus": "status",
                        "EventUrl": "url",
                        "EventImageUrl": "image_url"
                    }
                }
            },
            TixrEndpointType.FAN_INFORMATION: {
                "profile": {
                    "$email": "email",
                    "$first_name": "first_name",
                    "$last_name": "last_name",
                    "$phone_number": "phone",
                    "$address1": "address",
                    "$city": "city",
                    "$region": "state",
                    "$zip": "zip",
                    "$country": "country",
                    "TixrFanId": "id",
                    "TixrTotalOrders": "total_orders",
                    "TixrTotalTickets": "total_tickets",
                    "TixrTotalSpend": "total_spend",
                    "TixrLastOrderDate": "last_order_date"
                }
            },
            TixrEndpointType.FORM_SUBMISSIONS: {
                "event": {
                    "name": "Submitted Form",
                    "properties": {
                        "$event_id": "id",
                        "FormId": "form_id",
                        "FormName": "form_name",
                        "SubmissionDate": "created_date"
                    },
                    "customer_properties": {
                        "$email": "fan.email",
                        "$first_name": "fan.first_name",
                        "$last_name": "fan.last_name"
                    }
                },
                "profile": {
                    "$email": "fan.email",
                    "$first_name": "fan.first_name",
                    "$last_name": "fan.last_name",
                    "TixrFanId": "fan.id",
                    "FormSubmissionId": "id"
                }
            },
            TixrEndpointType.FAN_TRANSFERS: {
                "event": {
                    "name": "Transferred Ticket",
                    "properties": {
                        "$event_id": "id",
                        "TransferId": "id",
                        "TransferDate": "created_date",
                        "TransferStatus": "status",
                        "EventId": "event_id",
                        "EventName": "event_name"
                    },
                    "customer_properties": {
                        "$email": "sender.email",
                        "$first_name": "sender.first_name",
                        "$last_name": "sender.last_name"
                    }
                },
                "profile": {
                    "$email": "sender.email",
                    "$first_name": "sender.first_name",
                    "$last_name": "sender.last_name",
                    "TixrFanId": "sender.id"
                }
            },
            TixrEndpointType.GROUPS: {
                "event": {
                    "name": "Viewed Organization",
                    "properties": {
                        "$event_id": "id",
                        "GroupId": "id",
                        "GroupName": "name",
                        "GroupDescription": "description",
                        "GroupUrl": "url",
                        "GroupImageUrl": "image_url"
                    }
                }
            }
        }
    
    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dictionary using dot notation."""
        keys = path.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value
    
    def _validate_required_fields(self, data: Dict[str, Any], endpoint_type: TixrEndpointType) -> List[str]:
        """Validate that required fields are present in the data."""
        errors = []
        
        # Define required fields for each endpoint type
        required_fields = {
            TixrEndpointType.EVENT_ORDERS: ["order_id", "event_id", "email"],
            TixrEndpointType.EVENT_DETAILS: ["id", "name"],
            TixrEndpointType.FAN_INFORMATION: ["id", "email"],
            TixrEndpointType.FORM_SUBMISSIONS: ["id", "fan.email"],
            TixrEndpointType.FAN_TRANSFERS: ["id", "sender.email"],
            TixrEndpointType.GROUPS: ["id", "name"]
        }
        
        fields_to_check = required_fields.get(endpoint_type, [])
        
        for field in fields_to_check:
            value = self._get_nested_value(data, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"Missing required field: {field}")
        
        return errors
    
    def _clean_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and normalize data."""
        cleaned = {}
        
        for key, value in data.items():
            if value is not None:
                if isinstance(value, str):
                    # Strip whitespace and convert empty strings to None
                    cleaned_value = value.strip()
                    cleaned[key] = cleaned_value if cleaned_value else None
                elif isinstance(value, dict):
                    # Recursively clean nested dictionaries
                    cleaned[key] = self._clean_data(value)
                else:
                    cleaned[key] = value
        
        return cleaned
    
    def _map_properties(self, data: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """Map properties from source data to target format."""
        mapped = {}
        
        for target_field, source_field in mapping.items():
            if source_field is None:
                # Field not available in source
                continue
            
            value = self._get_nested_value(data, source_field)
            if value is not None:
                mapped[target_field] = value
        
        return mapped
    
    def _format_datetime(self, value: Any) -> Optional[str]:
        """Format datetime values to ISO format."""
        if value is None:
            return None
        
        if isinstance(value, str):
            try:
                # Try to parse and reformat
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.isoformat()
            except ValueError:
                # Return as-is if parsing fails
                return value
        elif isinstance(value, datetime):
            return value.isoformat()
        else:
            return str(value)
    
    def transform_to_klaviyo(self, 
                           tixr_data: Dict[str, Any], 
                           endpoint_type: TixrEndpointType,
                           correlation_id: str) -> TransformationResult:
        """Transform TIXR data to Klaviyo format."""
        start_time = time.time()
        
        logger.info("Starting data transformation", 
                   endpoint_type=endpoint_type,
                   correlation_id=correlation_id)
        
        try:
            # Clean the input data
            cleaned_data = self._clean_data(tixr_data)
            
            # Validate required fields
            validation_errors = self._validate_required_fields(cleaned_data, endpoint_type)
            
            if validation_errors:
                logger.warning("Data validation failed", 
                             errors=validation_errors,
                             correlation_id=correlation_id)
                return TransformationResult(
                    success=False,
                    validation_errors=validation_errors,
                    processing_time_ms=(time.time() - start_time) * 1000
                )
            
            # Get mapping configuration for endpoint type
            mapping_config = self.endpoint_mappings.get(endpoint_type)
            if not mapping_config:
                error_msg = f"No mapping configuration found for endpoint type: {endpoint_type}"
                logger.error(error_msg, correlation_id=correlation_id)
                return TransformationResult(
                    success=False,
                    validation_errors=[error_msg],
                    processing_time_ms=(time.time() - start_time) * 1000
                )
            
            result = TransformationResult(success=True)
            
            # Transform event data if mapping exists
            if "event" in mapping_config:
                event_mapping = mapping_config["event"]
                
                # Map event properties
                event_properties = self._map_properties(cleaned_data, event_mapping["properties"])
                
                # Map customer properties if they exist
                customer_properties = {}
                if "customer_properties" in event_mapping:
                    customer_properties = self._map_properties(cleaned_data, event_mapping["customer_properties"])
                
                # Format datetime fields
                for key, value in event_properties.items():
                    if key.endswith('Date') or key.endswith('_date'):
                        event_properties[key] = self._format_datetime(value)
                
                result.klaviyo_event = KlaviyoEventData(
                    event=event_mapping["name"],
                    properties=event_properties,
                    customer_properties=customer_properties,
                    timestamp=datetime.utcnow()
                )
            
            # Transform profile data if mapping exists
            if "profile" in mapping_config:
                profile_mapping = mapping_config["profile"]
                profile_data = self._map_properties(cleaned_data, profile_mapping)
                
                # Extract required fields for profile
                email = profile_data.get("$email")
                if email:
                    # Format datetime fields
                    properties = {}
                    for key, value in profile_data.items():
                        if not key.startswith("$"):
                            if key.endswith('Date') or key.endswith('_date'):
                                properties[key] = self._format_datetime(value)
                            else:
                                properties[key] = value
                    
                    result.klaviyo_profile = KlaviyoProfileData(
                        email=email,
                        first_name=profile_data.get("$first_name"),
                        last_name=profile_data.get("$last_name"),
                        phone_number=profile_data.get("$phone_number"),
                        properties=properties if properties else None
                    )
            
            processing_time = (time.time() - start_time) * 1000
            result.processing_time_ms = processing_time
            
            logger.info("Data transformation completed successfully", 
                       endpoint_type=endpoint_type,
                       has_event=result.klaviyo_event is not None,
                       has_profile=result.klaviyo_profile is not None,
                       processing_time_ms=processing_time,
                       correlation_id=correlation_id)
            
            return result
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            error_msg = f"Transformation failed: {str(e)}"
            
            logger.error("Data transformation failed", 
                        error=error_msg,
                        endpoint_type=endpoint_type,
                        processing_time_ms=processing_time,
                        correlation_id=correlation_id)
            
            return TransformationResult(
                success=False,
                validation_errors=[error_msg],
                processing_time_ms=processing_time
            )
    
    def batch_transform(self, 
                       tixr_data_list: List[Dict[str, Any]], 
                       endpoint_type: TixrEndpointType,
                       correlation_id: str) -> List[TransformationResult]:
        """Transform multiple TIXR data items to Klaviyo format."""
        logger.info("Starting batch data transformation", 
                   item_count=len(tixr_data_list),
                   endpoint_type=endpoint_type,
                   correlation_id=correlation_id)
        
        results = []
        successful_count = 0
        failed_count = 0
        
        for i, tixr_data in enumerate(tixr_data_list):
            try:
                result = self.transform_to_klaviyo(tixr_data, endpoint_type, f"{correlation_id}-{i}")
                results.append(result)
                
                if result.success:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error("Failed to transform item", 
                           item_index=i,
                           error=str(e),
                           correlation_id=correlation_id)
                
                results.append(TransformationResult(
                    success=False,
                    validation_errors=[f"Transformation error: {str(e)}"]
                ))
                failed_count += 1
        
        logger.info("Batch data transformation completed", 
                   total_items=len(tixr_data_list),
                   successful_items=successful_count,
                   failed_items=failed_count,
                   correlation_id=correlation_id)
        
        return results

