-- Supabase Database Initialization Script
-- Run this in your Supabase SQL editor to set up the database schema

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create the integration_runs table
CREATE TABLE IF NOT EXISTS integration_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    correlation_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    tixr_config JSONB NOT NULL,
    klaviyo_config JSONB NOT NULL,
    environment VARCHAR(50) NOT NULL DEFAULT 'production',
    priority INTEGER NOT NULL DEFAULT 5,
    total_items INTEGER DEFAULT 0,
    successful_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255) DEFAULT 'system'
);

-- Create the processing_queue table
CREATE TABLE IF NOT EXISTS processing_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    correlation_id VARCHAR(255) NOT NULL,
    queue_name VARCHAR(100) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the api_metrics table
CREATE TABLE IF NOT EXISTS api_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(100) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER NOT NULL,
    response_time_ms FLOAT NOT NULL,
    request_size_bytes INTEGER,
    response_size_bytes INTEGER,
    correlation_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the system_health table
CREATE TABLE IF NOT EXISTS system_health (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(100) NOT NULL,
    component VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    response_time_ms FLOAT,
    error_message TEXT,
    metadata JSONB,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the circuit_breaker_states table
CREATE TABLE IF NOT EXISTS circuit_breaker_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(100) UNIQUE NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'closed',
    failure_count INTEGER DEFAULT 0,
    last_failure_time TIMESTAMP WITH TIME ZONE,
    next_attempt_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create the configurations table
CREATE TABLE IF NOT EXISTS configurations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    description TEXT,
    environment VARCHAR(50) NOT NULL DEFAULT 'production',
    is_sensitive BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(255) DEFAULT 'system'
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_integration_runs_correlation_id ON integration_runs(correlation_id);
CREATE INDEX IF NOT EXISTS idx_integration_runs_status ON integration_runs(status);
CREATE INDEX IF NOT EXISTS idx_integration_runs_started_at ON integration_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_integration_runs_environment ON integration_runs(environment);

CREATE INDEX IF NOT EXISTS idx_processing_queue_status ON processing_queue(status);
CREATE INDEX IF NOT EXISTS idx_processing_queue_priority ON processing_queue(priority);
CREATE INDEX IF NOT EXISTS idx_processing_queue_scheduled_at ON processing_queue(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_processing_queue_correlation_id ON processing_queue(correlation_id);
CREATE INDEX IF NOT EXISTS idx_processing_queue_queue_name ON processing_queue(queue_name);

CREATE INDEX IF NOT EXISTS idx_api_metrics_service_name ON api_metrics(service_name);
CREATE INDEX IF NOT EXISTS idx_api_metrics_created_at ON api_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_api_metrics_endpoint ON api_metrics(endpoint);

CREATE INDEX IF NOT EXISTS idx_system_health_service_name ON system_health(service_name);
CREATE INDEX IF NOT EXISTS idx_system_health_checked_at ON system_health(checked_at);
CREATE INDEX IF NOT EXISTS idx_system_health_component ON system_health(component);

CREATE INDEX IF NOT EXISTS idx_circuit_breaker_states_service_name ON circuit_breaker_states(service_name);

CREATE INDEX IF NOT EXISTS idx_configurations_config_key ON configurations(config_key);
CREATE INDEX IF NOT EXISTS idx_configurations_environment ON configurations(environment);

-- Insert initial configuration data
INSERT INTO configurations (config_key, config_value, environment, description, created_by) VALUES
('default_batch_size', '100', 'production', 'Default batch size for processing operations', 'system'),
('default_retry_count', '3', 'production', 'Default number of retry attempts', 'system'),
('circuit_breaker_threshold', '5', 'production', 'Circuit breaker failure threshold', 'system'),
('rate_limit_requests_per_minute', '100', 'production', 'Rate limit for API requests per minute', 'system'),
('queue_cleanup_age_hours', '24', 'production', 'Age in hours after which completed queue items are cleaned up', 'system'),
('metrics_retention_days', '30', 'production', 'Number of days to retain API metrics', 'system')
ON CONFLICT (config_key) DO NOTHING;

-- Insert initial circuit breaker states
INSERT INTO circuit_breaker_states (service_name, state, failure_count) VALUES
('tixr_api', 'closed', 0),
('klaviyo_api', 'closed', 0)
ON CONFLICT (service_name) DO NOTHING;

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers to automatically update updated_at timestamps
CREATE TRIGGER update_integration_runs_updated_at BEFORE UPDATE ON integration_runs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_processing_queue_updated_at BEFORE UPDATE ON processing_queue FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_circuit_breaker_states_updated_at BEFORE UPDATE ON circuit_breaker_states FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_configurations_updated_at BEFORE UPDATE ON configurations FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create Row Level Security (RLS) policies for Supabase
ALTER TABLE integration_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE processing_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE circuit_breaker_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE configurations ENABLE ROW LEVEL SECURITY;

-- Create policies that allow service role to access all data
CREATE POLICY "Service role can access all integration_runs" ON integration_runs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all processing_queue" ON processing_queue FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all api_metrics" ON api_metrics FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all system_health" ON system_health FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all circuit_breaker_states" ON circuit_breaker_states FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role can access all configurations" ON configurations FOR ALL USING (auth.role() = 'service_role');

-- Grant necessary permissions to the service role
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

-- Create a view for monitoring dashboard
CREATE OR REPLACE VIEW integration_summary AS
SELECT 
    DATE_TRUNC('hour', created_at) as hour,
    environment,
    status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
    SUM(total_items) as total_items_processed,
    SUM(successful_items) as total_successful_items,
    SUM(failed_items) as total_failed_items
FROM integration_runs 
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', created_at), environment, status
ORDER BY hour DESC;

-- Grant access to the view
GRANT SELECT ON integration_summary TO service_role;

