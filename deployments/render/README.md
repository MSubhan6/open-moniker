# Render.com Deployment

Simple cloud deployment for demos and testing.

## Architecture

- **Java Resolver**: Docker container on Render
- **Python Admin**: Python service on Render
- **PostgreSQL**: Managed database on Render

## Prerequisites

1. Render account: https://render.com
2. Render CLI (optional): `brew install render`
3. GitHub repository connected to Render

## Quick Deploy

### Option 1: Blueprint (Recommended)

1. Fork this repository to your GitHub
2. Go to https://render.com/deploy
3. Connect your GitHub repository
4. Render will detect `render.yaml` and create all services
5. Wait 5-10 minutes for deployment

### Option 2: Manual Setup

```bash
cd deployments/render

# 1. Create services via Render dashboard
# 2. Run bootstrap script for schema
./bootstrap.sh

# 3. Deploy with Render CLI
render deploy
```

## Configuration

### Environment Variables

All configured in `render.yaml`:
- `TELEMETRY_ENABLED=true`
- `TELEMETRY_SINK_TYPE=postgres`
- Database credentials auto-injected from Render

### Database Schema

Run after database is created:

```bash
# Get database URL from Render dashboard
render databases list

# Run migrations
psql $DATABASE_URL < /tmp/schema.sql
```

## Accessing Services

After deployment:

- **Java Resolver**: `https://moniker-resolver-java.onrender.com`
  - Health: `/health`
  - Resolve: `/resolve/risk.greeks`
  - Catalog: `/catalog`

- **Python Admin**: `https://moniker-admin.onrender.com`
  - Dashboard: `/dashboard`
  - Config UI: `/config/ui`
  - API Docs: `/docs`

## Testing

```bash
# Health checks
curl https://moniker-resolver-java.onrender.com/health
curl https://moniker-admin.onrender.com/health

# Test resolution
curl https://moniker-resolver-java.onrender.com/resolve/risk.greeks

# View dashboard
open https://moniker-admin.onrender.com/dashboard
```

## Costs

**Free Tier:**
- 2 web services (750 hours/month each)
- PostgreSQL Starter: $7/month
- **Total: ~$7/month**

**Paid Tier (Starter):**
- Java Resolver: $7/month
- Python Admin: $7/month
- PostgreSQL: $7/month
- **Total: ~$21/month**

## Monitoring

- Logs: Render dashboard > Service > Logs
- Metrics: Render dashboard > Service > Metrics
- Database: Render dashboard > Database > Metrics

## Troubleshooting

### Services won't start

Check logs in Render dashboard:
```bash
render logs -s moniker-resolver-java
render logs -s moniker-admin
```

### Database connection fails

Verify environment variables are set:
```bash
render env:get -s moniker-resolver-java | grep TELEMETRY_DB
```

### Telemetry not working

1. Check database schema exists
2. Verify TELEMETRY_ENABLED=true
3. Check logs for errors

## Scaling

In Render dashboard:
- Java Resolver: Increase instances (1 → 3)
- Python Admin: Keep at 1 (low traffic)
- Database: Upgrade plan (Starter → Standard)

## CI/CD

Render auto-deploys on git push to main:
- Detects changes in `resolver-java/` → rebuilds Java
- Detects changes in `src/` → redeploys Python
- Zero-downtime deployments

## Next Steps

For production deployment, see [AWS Documentation](../aws/README.md).
