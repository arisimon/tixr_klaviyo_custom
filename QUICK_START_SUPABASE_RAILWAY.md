# TIXR-Klaviyo Integration: Supabase + Railway Quick Start

## Overview

This quick start guide gets you up and running with the TIXR-Klaviyo integration using Supabase for database and Railway for hosting in under 30 minutes.

## Prerequisites

- Supabase account (free tier works)
- Railway account (free tier works)
- TIXR API credentials (CPK and Private Key)
- Klaviyo API key
- GitHub account for code repository

## Step 1: Set Up Supabase Database

### Create Supabase Project
1. Go to [supabase.com](https://supabase.com) and sign up/login
2. Click "New Project"
3. Choose organization and enter project details:
   - **Name**: `tixr-klaviyo-integration`
   - **Database Password**: Generate a strong password (save it!)
   - **Region**: Choose closest to your users
4. Wait for project creation (2-3 minutes)

### Initialize Database Schema
1. Go to your Supabase dashboard
2. Click "SQL Editor" in the sidebar
3. Copy the contents of `supabase-init.sql` from this repository
4. Paste into the SQL Editor and click "Run"
5. Verify tables were created in the "Table Editor"

### Get Database Credentials
1. Go to Settings > Database
2. Copy the connection string under "Connection string"
3. Save this for later - you'll need it for Railway

## Step 2: Set Up Railway Hosting

### Create Railway Project
1. Go to [railway.app](https://railway.app) and sign up/login with GitHub
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Connect your GitHub account and select your repository
5. Railway will automatically detect it's a Python app

### Add Redis Service
1. In your Railway project dashboard, click "Add Service"
2. Select "Redis" from the database options
3. Railway will automatically provision Redis and provide connection details

### Configure Environment Variables
1. Click on your main service (not Redis)
2. Go to the "Variables" tab
3. Add these environment variables:

```bash
# Database (from Supabase)
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require
SUPABASE_URL=https://[PROJECT-REF].supabase.co
SUPABASE_ANON_KEY=[YOUR-ANON-KEY]
SUPABASE_SERVICE_ROLE_KEY=[YOUR-SERVICE-ROLE-KEY]

# TIXR Credentials
TIXR_CPK=your_tixr_client_partner_key
TIXR_PRIVATE_KEY=your_tixr_private_key

# Klaviyo Credentials  
KLAVIYO_API_KEY=your_klaviyo_api_key

# Security
SECRET_KEY=your_super_secure_random_string_here

# Optional Settings
APP_NAME=TIXR-Klaviyo Integration
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
```

**Note**: Replace the bracketed placeholders with your actual values from Supabase dashboard.

## Step 3: Deploy to Railway

### Automatic Deployment
1. Railway automatically deploys when you push to your connected GitHub branch
2. Monitor the deployment in the "Deployments" tab
3. Wait for deployment to complete (usually 2-3 minutes)

### Get Your Application URL
1. Go to the "Settings" tab of your service
2. Click "Generate Domain" to get a public URL
3. Your app will be available at: `https://your-app-name.railway.app`

## Step 4: Verify Deployment

### Test Health Check
1. Visit: `https://your-app-name.railway.app/api/v1/health`
2. You should see a JSON response with status "healthy"

### Access API Documentation
1. Visit: `https://your-app-name.railway.app/docs`
2. You should see the interactive API documentation

### Test Integration Endpoint
1. Use the API docs to test the `/api/v1/integrations` endpoint
2. Create a test integration with your TIXR event data

## Step 5: Production Configuration

### Custom Domain (Optional)
1. In Railway, go to Settings > Domains
2. Add your custom domain
3. Update your DNS records as instructed

### Monitoring Setup
1. Monitor your app through Railway's built-in metrics
2. Set up alerts in Railway dashboard
3. Monitor Supabase database usage

### Security Hardening
1. Rotate the SECRET_KEY to a production-grade value
2. Review and restrict API access as needed
3. Set up proper backup procedures

## Environment Variables Quick Reference

| Variable | Required | Source | Example |
|----------|----------|--------|---------|
| `DATABASE_URL` | ✅ | Supabase Dashboard | `postgresql://postgres:...` |
| `REDIS_URL` | ✅ | Auto-set by Railway | `redis://default:...` |
| `TIXR_CPK` | ✅ | TIXR Support | `your_cpk_here` |
| `TIXR_PRIVATE_KEY` | ✅ | TIXR Support | `your_private_key_here` |
| `KLAVIYO_API_KEY` | ✅ | Klaviyo Dashboard | `pk_your_key_here` |
| `SECRET_KEY` | ✅ | Generate Random | `random_32_char_string` |

## Troubleshooting

### Common Issues

**Database Connection Failed**
- Check DATABASE_URL format includes `?sslmode=require`
- Verify Supabase project is active
- Ensure password is correct in connection string

**Redis Connection Failed**  
- Verify Redis service is running in Railway
- Check Railway logs for Redis connectivity errors

**API Authentication Failed**
- Verify TIXR credentials are correct
- Test Klaviyo API key in Klaviyo dashboard
- Check for typos in environment variables

**Application Won't Start**
- Check Railway deployment logs
- Verify all required environment variables are set
- Ensure Python dependencies are compatible

### Getting Help

1. Check Railway deployment logs: Railway Dashboard > Deployments > View Logs
2. Check Supabase logs: Supabase Dashboard > Logs
3. Review the comprehensive documentation in `SUPABASE_RAILWAY_GUIDE.md`
4. Test locally first using the same environment variables

## Next Steps

1. **Set up monitoring**: Configure alerts and monitoring dashboards
2. **Implement backups**: Set up automated backup procedures  
3. **Scale as needed**: Monitor usage and scale resources accordingly
4. **Security review**: Implement additional security measures for production

## Cost Optimization

- **Supabase**: Free tier includes 500MB database, 2GB bandwidth
- **Railway**: Free tier includes $5/month credit, pay-as-you-go after
- **Monitor usage**: Both platforms provide usage dashboards
- **Optimize resources**: Scale down during low usage periods

## Support Resources

- **Railway Documentation**: [docs.railway.app](https://docs.railway.app)
- **Supabase Documentation**: [supabase.com/docs](https://supabase.com/docs)
- **Integration Documentation**: See `SUPABASE_RAILWAY_GUIDE.md` for comprehensive guide

---

🎉 **Congratulations!** Your TIXR-Klaviyo integration is now running on modern, managed infrastructure with automatic scaling, SSL, and monitoring built-in.

