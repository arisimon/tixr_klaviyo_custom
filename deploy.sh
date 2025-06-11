#!/bin/bash

# TIXR-Klaviyo Integration Deployment Script
# This script sets up and deploys the complete integration system

set -e

echo "🚀 Starting TIXR-Klaviyo Integration Deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_success "Docker and Docker Compose are installed"
}

# Check if .env file exists
check_env_file() {
    if [ ! -f ".env" ]; then
        print_warning ".env file not found. Creating from template..."
        cp .env.example .env
        print_warning "Please edit .env file with your actual configuration before continuing."
        print_warning "Required variables: TIXR_CPK, TIXR_PRIVATE_KEY, KLAVIYO_API_KEY"
        read -p "Press Enter to continue after editing .env file..."
    fi
    
    # Check for required environment variables
    source .env
    
    if [ -z "$TIXR_CPK" ] || [ "$TIXR_CPK" = "your_tixr_client_partner_key" ]; then
        print_error "TIXR_CPK is not configured in .env file"
        exit 1
    fi
    
    if [ -z "$TIXR_PRIVATE_KEY" ] || [ "$TIXR_PRIVATE_KEY" = "your_tixr_private_key" ]; then
        print_error "TIXR_PRIVATE_KEY is not configured in .env file"
        exit 1
    fi
    
    if [ -z "$KLAVIYO_API_KEY" ] || [ "$KLAVIYO_API_KEY" = "your_klaviyo_api_key" ]; then
        print_error "KLAVIYO_API_KEY is not configured in .env file"
        exit 1
    fi
    
    print_success "Environment configuration validated"
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    mkdir -p logs
    mkdir -p monitoring/grafana/dashboards
    mkdir -p monitoring/grafana/datasources
    mkdir -p nginx/ssl
    
    print_success "Directories created"
}

# Generate SSL certificates (self-signed for development)
generate_ssl_certs() {
    if [ ! -f "nginx/ssl/cert.pem" ]; then
        print_status "Generating self-signed SSL certificates..."
        
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/key.pem \
            -out nginx/ssl/cert.pem \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
        
        print_success "SSL certificates generated"
    else
        print_status "SSL certificates already exist"
    fi
}

# Build Docker images
build_images() {
    print_status "Building Docker images..."
    
    docker-compose build --no-cache
    
    print_success "Docker images built successfully"
}

# Start services
start_services() {
    print_status "Starting services..."
    
    # Start infrastructure services first
    docker-compose up -d postgres redis
    
    print_status "Waiting for database to be ready..."
    sleep 10
    
    # Run database migrations
    print_status "Running database migrations..."
    docker-compose run --rm api alembic upgrade head
    
    # Start all services
    docker-compose up -d
    
    print_success "All services started"
}

# Wait for services to be healthy
wait_for_services() {
    print_status "Waiting for services to be healthy..."
    
    # Wait for API to be ready
    for i in {1..30}; do
        if curl -f http://localhost:8000/api/v1/health &> /dev/null; then
            print_success "API service is healthy"
            break
        fi
        
        if [ $i -eq 30 ]; then
            print_error "API service failed to start"
            docker-compose logs api
            exit 1
        fi
        
        sleep 2
    done
    
    # Wait for Grafana to be ready
    for i in {1..30}; do
        if curl -f http://localhost:3000/api/health &> /dev/null; then
            print_success "Grafana service is healthy"
            break
        fi
        
        if [ $i -eq 30 ]; then
            print_warning "Grafana service may not be ready"
            break
        fi
        
        sleep 2
    done
}

# Display service URLs
display_urls() {
    print_success "🎉 Deployment completed successfully!"
    echo ""
    echo "Service URLs:"
    echo "  📊 API Documentation: http://localhost:8000/docs"
    echo "  🔍 API Health Check: http://localhost:8000/api/v1/health"
    echo "  📈 Grafana Dashboard: http://localhost:3000 (admin/admin)"
    echo "  📊 Prometheus Metrics: http://localhost:9090"
    echo "  🔧 Nginx Proxy: http://localhost"
    echo ""
    echo "Useful commands:"
    echo "  📋 View logs: docker-compose logs -f [service_name]"
    echo "  🔄 Restart service: docker-compose restart [service_name]"
    echo "  🛑 Stop all services: docker-compose down"
    echo "  🗑️  Remove all data: docker-compose down -v"
    echo ""
}

# Run health checks
run_health_checks() {
    print_status "Running health checks..."
    
    # Test API endpoints
    if curl -f http://localhost:8000/api/v1/health &> /dev/null; then
        print_success "✅ API health check passed"
    else
        print_error "❌ API health check failed"
    fi
    
    # Test TIXR connection (if configured)
    if curl -f -X POST http://localhost:8000/api/v1/test/tixr &> /dev/null; then
        print_success "✅ TIXR connection test passed"
    else
        print_warning "⚠️  TIXR connection test failed (check credentials)"
    fi
    
    # Test Klaviyo connection (if configured)
    if curl -f -X POST http://localhost:8000/api/v1/test/klaviyo &> /dev/null; then
        print_success "✅ Klaviyo connection test passed"
    else
        print_warning "⚠️  Klaviyo connection test failed (check credentials)"
    fi
}

# Main deployment function
main() {
    echo "=================================================="
    echo "  TIXR-Klaviyo Integration Deployment Script"
    echo "=================================================="
    echo ""
    
    check_docker
    check_env_file
    create_directories
    generate_ssl_certs
    build_images
    start_services
    wait_for_services
    run_health_checks
    display_urls
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        print_status "Stopping all services..."
        docker-compose down
        print_success "All services stopped"
        ;;
    "restart")
        print_status "Restarting all services..."
        docker-compose restart
        print_success "All services restarted"
        ;;
    "logs")
        docker-compose logs -f "${2:-}"
        ;;
    "clean")
        print_warning "This will remove all containers, volumes, and data!"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose down -v --remove-orphans
            docker system prune -f
            print_success "Cleanup completed"
        fi
        ;;
    "help")
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  deploy    - Deploy the complete system (default)"
        echo "  stop      - Stop all services"
        echo "  restart   - Restart all services"
        echo "  logs      - View logs (optionally specify service name)"
        echo "  clean     - Remove all containers and data"
        echo "  help      - Show this help message"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac

