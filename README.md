# TIXR-Klaviyo Integration: Quick Start Guide

## Overview

This quick start guide provides step-by-step instructions for rapidly deploying the TIXR-Klaviyo integration system. Follow these instructions to have a fully functional integration environment running in under 30 minutes.

## Prerequisites

- Docker Engine 20.10+ and Docker Compose 2.0+
- TIXR API credentials (CPK and Private Key)
- Klaviyo API key
- 8GB RAM and 4 CPU cores minimum

## Step 1: Download and Setup

```bash
# Clone the repository
git clone <repository-url>
cd tixr-klaviyo-integration

# Copy environment template
cp .env.example .env
```

## Step 2: Configure Credentials

Edit the `.env` file with your actual credentials:

```bash
# Required TIXR credentials
TIXR_CPK=your_actual_tixr_client_partner_key
TIXR_PRIVATE_KEY=your_actual_tixr_private_key

# Required Klaviyo credentials
KLAVIYO_API_KEY=your_actual_klaviyo_api_key

# Optional: Change default passwords
POSTGRES_PASSWORD=your_secure_database_password
```

## Step 3: Deploy

```bash
# Make deployment script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

The deployment script will:
- Verify Docker installation
- Validate configuration
- Build Docker images
- Start all services
- Run health checks

## Step 4: Verify Installation

Once deployment completes, verify the installation:

```bash
# Check API health
curl http://localhost:8000/api/v1/health

# View API documentation
open http://localhost:8000/docs

# Access monitoring dashboard
open http://localhost:3000
```

## Step 5: Test Integration

Create a test integration:

```bash
curl -X POST http://localhost:8000/api/v1/integrations \
  -H "Content-Type: application/json" \
  -d '{
    "tixr_config": {
      "endpoint_type": "event_orders",
      "group_id": "your_group_id",
      "event_id": "your_event_id",
      "page_size": 50
    },
    "klaviyo_config": {
      "track_events": true,
      "update_profiles": true
    },
    "environment": "production",
    "priority": 5
  }'
```

## Service URLs

- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health
- **Grafana Dashboard**: http://localhost:3000 (admin/admin)
- **Prometheus Metrics**: http://localhost:9090

## Common Commands

```bash
# View logs
docker-compose logs -f api

# Restart services
docker-compose restart

# Stop all services
docker-compose down

# Clean installation
./deploy.sh clean
```

## Troubleshooting

If you encounter issues:

1. Check logs: `docker-compose logs -f`
2. Verify credentials in `.env` file
3. Ensure ports 8000, 3000, 9090 are available
4. Check Docker and Docker Compose versions

For detailed troubleshooting, see the complete documentation.

## Next Steps

- Review the complete documentation for advanced configuration
- Set up monitoring alerts in Grafana
- Configure backup procedures
- Plan for production deployment

## Support

For technical support and questions:
- Review the comprehensive documentation
- Check system logs and monitoring dashboards
- Verify configuration settings and credentials

