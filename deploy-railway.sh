#!/bin/bash

# Railway Deployment Script for TIXR-Klaviyo Integration
# This script helps deploy the application to Railway

set -e

echo "🚀 TIXR-Klaviyo Integration - Railway Deployment"
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if Railway CLI is installed
check_railway_cli() {
    if ! command -v railway &> /dev/null; then
        echo -e "${RED}❌ Railway CLI is not installed${NC}"
        echo "Please install it from: https://docs.railway.app/develop/cli"
        echo "Run: npm install -g @railway/cli"
        exit 1
    fi
    echo -e "${GREEN}✅ Railway CLI found${NC}"
}

# Check if user is logged in to Railway
check_railway_auth() {
    if ! railway whoami &> /dev/null; then
        echo -e "${YELLOW}⚠️  Not logged in to Railway${NC}"
        echo "Please run: railway login"
        exit 1
    fi
    echo -e "${GREEN}✅ Railway authentication verified${NC}"
}

# Create or link Railway project
setup_railway_project() {
    echo -e "${BLUE}🔧 Setting up Railway project...${NC}"
    
    if [ ! -f ".railway" ]; then
        echo "No Railway project found. Creating new project..."
        railway init
    else
        echo "Railway project already configured"
    fi
}

# Set up required environment variables
setup_environment_variables() {
    echo -e "${BLUE}🔧 Setting up environment variables...${NC}"
    
    # Check if .env file exists
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}⚠️  No .env file found. Creating from template...${NC}"
        cp .env.example .env
        echo -e "${RED}❌ Please edit .env file with your actual credentials before continuing${NC}"
        exit 1
    fi
    
    # Read environment variables from .env file and set them in Railway
    echo "Setting environment variables in Railway..."
    
    # Required variables
    REQUIRED_VARS=(
        "DATABASE_URL"
        "REDIS_URL" 
        "TIXR_CPK"
        "TIXR_PRIVATE_KEY"
        "KLAVIYO_API_KEY"
        "SECRET_KEY"
    )
    
    # Source the .env file
    set -a
    source .env
    set +a
    
    # Set each required variable in Railway
    for var in "${REQUIRED_VARS[@]}"; do
        if [ -z "${!var}" ]; then
            echo -e "${RED}❌ Required variable $var is not set in .env file${NC}"
            exit 1
        fi
        
        echo "Setting $var..."
        railway variables set "$var=${!var}"
    done
    
    # Set optional variables with defaults
    railway variables set "APP_NAME=${APP_NAME:-TIXR-Klaviyo Integration}"
    railway variables set "APP_VERSION=${APP_VERSION:-1.0.0}"
    railway variables set "ENVIRONMENT=${ENVIRONMENT:-production}"
    railway variables set "DEBUG=${DEBUG:-false}"
    railway variables set "LOG_LEVEL=${LOG_LEVEL:-INFO}"
    
    echo -e "${GREEN}✅ Environment variables configured${NC}"
}

# Add Railway Redis service
setup_redis_service() {
    echo -e "${BLUE}🔧 Setting up Redis service...${NC}"
    
    # Check if Redis is already added
    if railway services | grep -q "redis"; then
        echo "Redis service already exists"
    else
        echo "Adding Redis service..."
        railway add redis
        echo -e "${GREEN}✅ Redis service added${NC}"
    fi
}

# Deploy to Railway
deploy_application() {
    echo -e "${BLUE}🚀 Deploying to Railway...${NC}"
    
    # Deploy the application
    railway up
    
    echo -e "${GREEN}✅ Deployment initiated${NC}"
    echo "Check deployment status with: railway status"
    echo "View logs with: railway logs"
}

# Get deployment information
get_deployment_info() {
    echo -e "${BLUE}📋 Deployment Information${NC}"
    echo "=========================="
    
    # Get the deployment URL
    DOMAIN=$(railway domain)
    if [ $? -eq 0 ] && [ -n "$DOMAIN" ]; then
        echo -e "${GREEN}🌐 Application URL: https://$DOMAIN${NC}"
        echo -e "${GREEN}📚 API Documentation: https://$DOMAIN/docs${NC}"
        echo -e "${GREEN}❤️  Health Check: https://$DOMAIN/api/v1/health${NC}"
    else
        echo -e "${YELLOW}⚠️  Domain not yet assigned. Check Railway dashboard.${NC}"
    fi
    
    echo ""
    echo "Railway Commands:"
    echo "  railway logs        - View application logs"
    echo "  railway status      - Check deployment status"
    echo "  railway variables   - Manage environment variables"
    echo "  railway domain      - Manage custom domains"
    echo "  railway restart     - Restart the service"
}

# Main deployment flow
main() {
    echo -e "${BLUE}Starting Railway deployment process...${NC}"
    
    check_railway_cli
    check_railway_auth
    setup_railway_project
    setup_redis_service
    setup_environment_variables
    deploy_application
    
    echo ""
    echo -e "${GREEN}🎉 Deployment process completed!${NC}"
    echo ""
    
    get_deployment_info
    
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Set up Supabase database and update DATABASE_URL"
    echo "2. Configure custom domain if needed"
    echo "3. Set up monitoring and alerts"
    echo "4. Test the integration endpoints"
}

# Handle command line arguments
case "${1:-}" in
    "setup")
        check_railway_cli
        check_railway_auth
        setup_railway_project
        setup_redis_service
        ;;
    "env")
        setup_environment_variables
        ;;
    "deploy")
        deploy_application
        ;;
    "info")
        get_deployment_info
        ;;
    "help"|"-h"|"--help")
        echo "Railway Deployment Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  setup   - Set up Railway project and services"
        echo "  env     - Configure environment variables"
        echo "  deploy  - Deploy the application"
        echo "  info    - Show deployment information"
        echo "  help    - Show this help message"
        echo ""
        echo "Run without arguments to perform full deployment"
        ;;
    *)
        main
        ;;
esac

