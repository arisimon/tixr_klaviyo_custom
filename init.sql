-- Initialize database with required extensions and initial data

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_integration_runs_correlation_id ON integration_runs(correlation_id);
CREATE INDEX IF NOT EXISTS idx_integration_runs_status ON integration_runs(status);
CREATE INDEX IF NOT EXISTS idx_integration_runs_started_at ON integration_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_processing_queue_status ON processing_queue(status);
CREATE INDEX IF NOT EXISTS idx_processing_queue_priority ON processing_queue(priority);
CREATE INDEX IF NOT EXISTS idx_processing_queue_scheduled_at ON processing_queue(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_processing_queue_correlation_id ON processing_queue(correlation_id);

CREATE INDEX IF NOT EXISTS idx_api_metrics_service_name ON api_metrics(service_name);
CREATE INDEX IF NOT EXISTS idx_api_metrics_created_at ON api_metrics(created_at);

CREATE INDEX IF NOT EXISTS idx_system_health_service_name ON system_health(service_name);
CREATE INDEX IF NOT EXISTS idx_system_health_checked_at ON system_health(checked_at);

CREATE INDEX IF NOT EXISTS idx_circuit_breaker_states_service_name ON circuit_breaker_states(service_name);

-- Insert initial configuration data
INSERT INTO configurations (config_key, config_value, environment, created_by) VALUES
('default_batch_size', '100', 'production', 'system'),
('default_retry_count', '3', 'production', 'system'),
('circuit_breaker_threshold', '5', 'production', 'system'),
('rate_limit_requests_per_minute', '100', 'production', 'system')
ON CONFLICT (config_key) DO NOTHING;

-- Create initial circuit breaker states
INSERT INTO circuit_breaker_states (service_name, state, failure_count) VALUES
('tixr_api', 'closed', 0),
('klaviyo_api', 'closed', 0)
ON CONFLICT (service_name) DO NOTHING;

