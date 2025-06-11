import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.database import get_db
from app.core.redis import get_redis_client
from app.models.database import (
    IntegrationRun, ProcessingQueue, APIMetrics, SystemHealth,
    CircuitBreakerState as CircuitBreakerStateModel
)
from app.models.schemas import QueueStatus

logger = get_logger(__name__)


class MetricsCollector:
    """Prometheus metrics collector for the integration system."""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # Integration metrics
        self.integration_runs_total = Counter(
            'integration_runs_total',
            'Total number of integration runs',
            ['status', 'endpoint_type', 'environment'],
            registry=self.registry
        )
        
        self.integration_duration_seconds = Histogram(
            'integration_duration_seconds',
            'Duration of integration runs in seconds',
            ['endpoint_type', 'environment'],
            registry=self.registry
        )
        
        self.integration_items_processed = Counter(
            'integration_items_processed_total',
            'Total number of items processed',
            ['status', 'endpoint_type'],
            registry=self.registry
        )
        
        # API metrics
        self.api_requests_total = Counter(
            'api_requests_total',
            'Total number of API requests',
            ['service', 'endpoint', 'method', 'status_code'],
            registry=self.registry
        )
        
        self.api_request_duration_seconds = Histogram(
            'api_request_duration_seconds',
            'Duration of API requests in seconds',
            ['service', 'endpoint', 'method'],
            registry=self.registry
        )
        
        # Queue metrics
        self.queue_items_total = Gauge(
            'queue_items_total',
            'Total number of items in queue',
            ['queue_name', 'status'],
            registry=self.registry
        )
        
        self.queue_processing_duration_seconds = Histogram(
            'queue_processing_duration_seconds',
            'Duration of queue item processing in seconds',
            ['queue_name'],
            registry=self.registry
        )
        
        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            'circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=open, 2=half_open)',
            ['service_name'],
            registry=self.registry
        )
        
        self.circuit_breaker_failures = Counter(
            'circuit_breaker_failures_total',
            'Total number of circuit breaker failures',
            ['service_name'],
            registry=self.registry
        )
        
        # System health metrics
        self.system_health_status = Gauge(
            'system_health_status',
            'System health status (1=healthy, 0=unhealthy)',
            ['service_name'],
            registry=self.registry
        )
        
        self.system_response_time_seconds = Histogram(
            'system_response_time_seconds',
            'System response time in seconds',
            ['service_name'],
            registry=self.registry
        )
        
        # Data transformation metrics
        self.transformation_duration_seconds = Histogram(
            'transformation_duration_seconds',
            'Duration of data transformation in seconds',
            ['endpoint_type'],
            registry=self.registry
        )
        
        self.transformation_errors_total = Counter(
            'transformation_errors_total',
            'Total number of transformation errors',
            ['endpoint_type', 'error_type'],
            registry=self.registry
        )
    
    def record_integration_run(self, 
                              status: str,
                              endpoint_type: str,
                              environment: str,
                              duration_seconds: float,
                              total_items: int,
                              successful_items: int,
                              failed_items: int):
        """Record metrics for an integration run."""
        
        self.integration_runs_total.labels(
            status=status,
            endpoint_type=endpoint_type,
            environment=environment
        ).inc()
        
        self.integration_duration_seconds.labels(
            endpoint_type=endpoint_type,
            environment=environment
        ).observe(duration_seconds)
        
        self.integration_items_processed.labels(
            status='successful',
            endpoint_type=endpoint_type
        ).inc(successful_items)
        
        self.integration_items_processed.labels(
            status='failed',
            endpoint_type=endpoint_type
        ).inc(failed_items)
    
    def record_api_request(self,
                          service: str,
                          endpoint: str,
                          method: str,
                          status_code: int,
                          duration_seconds: float):
        """Record metrics for an API request."""
        
        self.api_requests_total.labels(
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code
        ).inc()
        
        self.api_request_duration_seconds.labels(
            service=service,
            endpoint=endpoint,
            method=method
        ).observe(duration_seconds)
    
    def update_queue_metrics(self, queue_stats: Dict[str, Any]):
        """Update queue metrics from queue statistics."""
        
        queue_name = queue_stats.get('queue_name', 'unknown')
        
        self.queue_items_total.labels(
            queue_name=queue_name,
            status='pending'
        ).set(queue_stats.get('pending_count', 0))
        
        self.queue_items_total.labels(
            queue_name=queue_name,
            status='processing'
        ).set(queue_stats.get('processing_count', 0))
        
        self.queue_items_total.labels(
            queue_name=queue_name,
            status='completed'
        ).set(queue_stats.get('completed_count', 0))
        
        self.queue_items_total.labels(
            queue_name=queue_name,
            status='failed'
        ).set(queue_stats.get('failed_count', 0))
        
        self.queue_items_total.labels(
            queue_name=queue_name,
            status='dead_letter'
        ).set(queue_stats.get('dead_letter_count', 0))
    
    def record_queue_processing(self, queue_name: str, duration_seconds: float):
        """Record queue processing duration."""
        
        self.queue_processing_duration_seconds.labels(
            queue_name=queue_name
        ).observe(duration_seconds)
    
    def update_circuit_breaker_metrics(self, service_name: str, state: str, failure_count: int):
        """Update circuit breaker metrics."""
        
        # Map state to numeric value
        state_value = {
            'closed': 0,
            'open': 1,
            'half_open': 2
        }.get(state, 0)
        
        self.circuit_breaker_state.labels(
            service_name=service_name
        ).set(state_value)
        
        self.circuit_breaker_failures.labels(
            service_name=service_name
        ).inc(failure_count)
    
    def record_system_health(self, service_name: str, is_healthy: bool, response_time_seconds: float):
        """Record system health metrics."""
        
        self.system_health_status.labels(
            service_name=service_name
        ).set(1 if is_healthy else 0)
        
        self.system_response_time_seconds.labels(
            service_name=service_name
        ).observe(response_time_seconds)
    
    def record_transformation(self, endpoint_type: str, duration_seconds: float, error_type: Optional[str] = None):
        """Record data transformation metrics."""
        
        self.transformation_duration_seconds.labels(
            endpoint_type=endpoint_type
        ).observe(duration_seconds)
        
        if error_type:
            self.transformation_errors_total.labels(
                endpoint_type=endpoint_type,
                error_type=error_type
            ).inc()
    
    def get_metrics(self) -> str:
        """Get Prometheus metrics in text format."""
        return generate_latest(self.registry).decode('utf-8')


class MonitoringService:
    """Comprehensive monitoring and alerting service."""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.redis_client = get_redis_client()
        self.alert_thresholds = {
            'error_rate_threshold': 0.05,  # 5%
            'response_time_threshold': 30.0,  # 30 seconds
            'queue_depth_threshold': 1000,
            'circuit_breaker_open_threshold': 300,  # 5 minutes
        }
    
    def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect comprehensive system metrics."""
        
        logger.info("Collecting system metrics")
        
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'integration_metrics': self._collect_integration_metrics(),
            'queue_metrics': self._collect_queue_metrics(),
            'api_metrics': self._collect_api_metrics(),
            'circuit_breaker_metrics': self._collect_circuit_breaker_metrics(),
            'system_health_metrics': self._collect_system_health_metrics()
        }
        
        # Update Prometheus metrics
        self._update_prometheus_metrics(metrics)
        
        # Check for alerts
        alerts = self._check_alert_conditions(metrics)
        if alerts:
            metrics['alerts'] = alerts
        
        return metrics
    
    def _collect_integration_metrics(self) -> Dict[str, Any]:
        """Collect integration run metrics."""
        
        with get_db() as db:
            try:
                # Get metrics for the last 24 hours
                since = datetime.utcnow() - timedelta(hours=24)
                
                runs = db.query(IntegrationRun).filter(
                    IntegrationRun.started_at >= since
                ).all()
                
                total_runs = len(runs)
                successful_runs = len([r for r in runs if r.status == 'completed'])
                failed_runs = len([r for r in runs if r.status == 'failed'])
                running_runs = len([r for r in runs if r.status == 'running'])
                
                # Calculate average processing time
                completed_runs = [r for r in runs if r.status == 'completed' and r.completed_at]
                avg_processing_time = 0
                if completed_runs:
                    total_time = sum([
                        (r.completed_at - r.started_at).total_seconds()
                        for r in completed_runs
                    ])
                    avg_processing_time = total_time / len(completed_runs)
                
                # Calculate total items processed
                total_items = sum([r.total_items or 0 for r in runs])
                successful_items = sum([r.successful_items or 0 for r in runs])
                failed_items = sum([r.failed_items or 0 for r in runs])
                
                return {
                    'total_runs': total_runs,
                    'successful_runs': successful_runs,
                    'failed_runs': failed_runs,
                    'running_runs': running_runs,
                    'success_rate': (successful_runs / max(1, total_runs)) * 100,
                    'average_processing_time_seconds': avg_processing_time,
                    'total_items_processed': total_items,
                    'successful_items': successful_items,
                    'failed_items': failed_items,
                    'item_success_rate': (successful_items / max(1, total_items)) * 100
                }
                
            except Exception as e:
                logger.error("Failed to collect integration metrics", error=str(e))
                return {'error': str(e)}
    
    def _collect_queue_metrics(self) -> Dict[str, Any]:
        """Collect queue metrics."""
        
        from app.services.queue_service import QueueManager
        
        try:
            queue_manager = QueueManager()
            return queue_manager.get_all_queue_stats()
            
        except Exception as e:
            logger.error("Failed to collect queue metrics", error=str(e))
            return {'error': str(e)}
    
    def _collect_api_metrics(self) -> Dict[str, Any]:
        """Collect API performance metrics."""
        
        with get_db() as db:
            try:
                # Get metrics for the last hour
                since = datetime.utcnow() - timedelta(hours=1)
                
                api_metrics = db.query(APIMetrics).filter(
                    APIMetrics.created_at >= since
                ).all()
                
                if not api_metrics:
                    return {
                        'total_requests': 0,
                        'average_response_time_ms': 0,
                        'error_rate': 0,
                        'services': {}
                    }
                
                # Group by service
                services = {}
                total_requests = len(api_metrics)
                total_response_time = sum([m.response_time_ms for m in api_metrics])
                error_requests = len([m for m in api_metrics if m.status_code >= 400])
                
                for metric in api_metrics:
                    service = metric.service_name
                    if service not in services:
                        services[service] = {
                            'requests': 0,
                            'total_response_time': 0,
                            'errors': 0
                        }
                    
                    services[service]['requests'] += 1
                    services[service]['total_response_time'] += metric.response_time_ms
                    if metric.status_code >= 400:
                        services[service]['errors'] += 1
                
                # Calculate averages for each service
                for service_data in services.values():
                    service_data['average_response_time_ms'] = (
                        service_data['total_response_time'] / service_data['requests']
                    )
                    service_data['error_rate'] = (
                        service_data['errors'] / service_data['requests']
                    ) * 100
                
                return {
                    'total_requests': total_requests,
                    'average_response_time_ms': total_response_time / total_requests,
                    'error_rate': (error_requests / total_requests) * 100,
                    'services': services
                }
                
            except Exception as e:
                logger.error("Failed to collect API metrics", error=str(e))
                return {'error': str(e)}
    
    def _collect_circuit_breaker_metrics(self) -> Dict[str, Any]:
        """Collect circuit breaker metrics."""
        
        with get_db() as db:
            try:
                circuit_breakers = db.query(CircuitBreakerStateModel).all()
                
                metrics = {}
                for cb in circuit_breakers:
                    metrics[cb.service_name] = {
                        'state': cb.state,
                        'failure_count': cb.failure_count,
                        'last_failure_at': cb.last_failure_at.isoformat() if cb.last_failure_at else None,
                        'last_success_at': cb.last_success_at.isoformat() if cb.last_success_at else None,
                        'updated_at': cb.updated_at.isoformat()
                    }
                
                return metrics
                
            except Exception as e:
                logger.error("Failed to collect circuit breaker metrics", error=str(e))
                return {'error': str(e)}
    
    def _collect_system_health_metrics(self) -> Dict[str, Any]:
        """Collect system health metrics."""
        
        with get_db() as db:
            try:
                # Get latest health check for each service
                latest_health = {}
                
                health_records = db.query(SystemHealth).order_by(
                    SystemHealth.checked_at.desc()
                ).limit(100).all()
                
                for health in health_records:
                    service = health.service_name
                    if service not in latest_health:
                        latest_health[service] = {
                            'status': health.health_status,
                            'response_time_ms': health.response_time_ms,
                            'checked_at': health.checked_at.isoformat(),
                            'error_message': health.error_message
                        }
                
                return latest_health
                
            except Exception as e:
                logger.error("Failed to collect system health metrics", error=str(e))
                return {'error': str(e)}
    
    def _update_prometheus_metrics(self, metrics: Dict[str, Any]):
        """Update Prometheus metrics with collected data."""
        
        try:
            # Update integration metrics
            integration_metrics = metrics.get('integration_metrics', {})
            if 'error' not in integration_metrics:
                # Record integration runs
                self.metrics_collector.integration_runs_total.labels(
                    status='completed',
                    endpoint_type='all',
                    environment='production'
                ).inc(integration_metrics.get('successful_runs', 0))
                
                self.metrics_collector.integration_runs_total.labels(
                    status='failed',
                    endpoint_type='all',
                    environment='production'
                ).inc(integration_metrics.get('failed_runs', 0))
            
            # Update queue metrics
            queue_metrics = metrics.get('queue_metrics', {})
            if 'error' not in queue_metrics:
                queues = queue_metrics.get('queues', {})
                for queue_name, queue_stats in queues.items():
                    self.metrics_collector.update_queue_metrics(queue_stats)
            
            # Update circuit breaker metrics
            cb_metrics = metrics.get('circuit_breaker_metrics', {})
            if 'error' not in cb_metrics:
                for service_name, cb_data in cb_metrics.items():
                    self.metrics_collector.update_circuit_breaker_metrics(
                        service_name,
                        cb_data.get('state', 'closed'),
                        cb_data.get('failure_count', 0)
                    )
            
            # Update system health metrics
            health_metrics = metrics.get('system_health_metrics', {})
            if 'error' not in health_metrics:
                for service_name, health_data in health_metrics.items():
                    is_healthy = health_data.get('status') == 'healthy'
                    response_time = (health_data.get('response_time_ms', 0) or 0) / 1000
                    
                    self.metrics_collector.record_system_health(
                        service_name,
                        is_healthy,
                        response_time
                    )
            
        except Exception as e:
            logger.error("Failed to update Prometheus metrics", error=str(e))
    
    def _check_alert_conditions(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for alert conditions in the metrics."""
        
        alerts = []
        
        try:
            # Check integration error rate
            integration_metrics = metrics.get('integration_metrics', {})
            if 'error' not in integration_metrics:
                success_rate = integration_metrics.get('success_rate', 100)
                if success_rate < (100 - self.alert_thresholds['error_rate_threshold'] * 100):
                    alerts.append({
                        'type': 'integration_error_rate',
                        'severity': 'warning',
                        'message': f"Integration success rate is {success_rate:.2f}%",
                        'threshold': f"{(100 - self.alert_thresholds['error_rate_threshold'] * 100):.2f}%"
                    })
            
            # Check queue depth
            queue_metrics = metrics.get('queue_metrics', {})
            if 'error' not in queue_metrics:
                totals = queue_metrics.get('totals', {})
                pending_items = totals.get('total_pending', 0)
                if pending_items > self.alert_thresholds['queue_depth_threshold']:
                    alerts.append({
                        'type': 'queue_depth',
                        'severity': 'warning',
                        'message': f"Queue depth is {pending_items} items",
                        'threshold': self.alert_thresholds['queue_depth_threshold']
                    })
            
            # Check circuit breaker states
            cb_metrics = metrics.get('circuit_breaker_metrics', {})
            if 'error' not in cb_metrics:
                for service_name, cb_data in cb_metrics.items():
                    if cb_data.get('state') == 'open':
                        alerts.append({
                            'type': 'circuit_breaker_open',
                            'severity': 'critical',
                            'message': f"Circuit breaker is open for service: {service_name}",
                            'service': service_name
                        })
            
            # Check system health
            health_metrics = metrics.get('system_health_metrics', {})
            if 'error' not in health_metrics:
                for service_name, health_data in health_metrics.items():
                    if health_data.get('status') != 'healthy':
                        alerts.append({
                            'type': 'service_unhealthy',
                            'severity': 'critical',
                            'message': f"Service is unhealthy: {service_name}",
                            'service': service_name,
                            'error': health_data.get('error_message')
                        })
            
        except Exception as e:
            logger.error("Failed to check alert conditions", error=str(e))
            alerts.append({
                'type': 'monitoring_error',
                'severity': 'warning',
                'message': f"Failed to check alert conditions: {str(e)}"
            })
        
        return alerts
    
    def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics."""
        return self.metrics_collector.get_metrics()
    
    def record_api_call(self, service: str, endpoint: str, method: str, status_code: int, duration_seconds: float):
        """Record an API call for monitoring."""
        
        # Record in Prometheus
        self.metrics_collector.record_api_request(
            service, endpoint, method, status_code, duration_seconds
        )
        
        # Store in database for historical analysis
        with get_db() as db:
            try:
                api_metric = APIMetrics(
                    service_name=service,
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    response_time_ms=duration_seconds * 1000
                )
                db.add(api_metric)
                db.commit()
                
            except Exception as e:
                db.rollback()
                logger.error("Failed to record API metric", 
                           service=service,
                           endpoint=endpoint,
                           error=str(e))
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for monitoring dashboard."""
        
        return {
            'system_metrics': self.collect_system_metrics(),
            'prometheus_metrics_url': '/metrics',
            'last_updated': datetime.utcnow().isoformat()
        }

