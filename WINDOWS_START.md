# Starting Open Moniker on Windows

Quick start guide for Windows (Python only, no batch files).

## Prerequisites

1. Python 3.9 or later
2. Git (to clone the repo)

## Quick Start

```cmd
cd open-moniker-svc
pip install -r requirements.txt
python start.py
```

That's it! Service starts on http://localhost:8050

## Installation Steps

1. **Clone the repository:**
```cmd
git clone https://github.com/MSubhan6/open-moniker.git
cd open-moniker-svc
```

2. **Install dependencies:**
```cmd
pip install -r requirements.txt
```

3. **Start the service:**
```cmd
python start.py
```

## Usage

**Start default monolith (all features, port 8050):**
```cmd
python start.py
```

**Start management service only (port 8052):**
```cmd
python start.py --service management
```

**Start resolver service only (port 8051):**
```cmd
python start.py --service resolver
```

**Custom port:**
```cmd
python start.py --port 9000
```

**Enable auto-reload for development:**
```cmd
python start.py --reload
```

## Access the Service

Once running, open your browser:

- **Health Check:** http://localhost:8050/health
- **API Docs:** http://localhost:8050/docs
- **Config UI:** http://localhost:8050/config
- **Dashboard:** http://localhost:8050/dashboard

## What Each Service Does

**Monolith (main):**
- Everything: resolution, management, config UI, dashboard
- Best for: Single-server deployments, development, demos

**Management:**
- Config UI, dashboard, domains, models, requests
- No resolution endpoints
- Best for: Admin/control plane

**Resolver:**
- Resolution endpoints only (/resolve/*, /catalog)
- No admin features
- Best for: Scaling out data plane

## Troubleshooting

**Error: No module named 'moniker_svc'**
- Make sure you're in the project root directory
- The start.py script sets PYTHONPATH automatically

**Error: No module named 'fastapi'**
- Install dependencies: `pip install -r requirements.txt`

**Error: Cannot find config files**
- The script uses sample_config.yaml and sample_catalog.yaml by default
- Make sure these files exist in the project root

**Port already in use:**
```cmd
python start.py --port 9000
```

**Service won't start:**
1. Check Python version: `python --version` (need 3.9+)
2. Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
3. Check if port is available: `netstat -an | findstr 8050`

## Configuration Files

The service uses these files by default:
- `sample_config.yaml` - Service configuration
- `sample_catalog.yaml` - Data catalog

To use custom configs, set environment variables:
```cmd
set CONFIG_FILE=my_config.yaml
set CATALOG_FILE=my_catalog.yaml
python start.py
```

## Testing

Test the service is running:
```cmd
curl http://localhost:8050/health
```

Or open in browser: http://localhost:8050/health

## Next Steps

1. Open the API docs: http://localhost:8050/docs
2. Try the config UI: http://localhost:8050/config
3. Test resolution: http://localhost:8050/resolve/reference
4. View dashboard: http://localhost:8050/dashboard

## Getting Help

- Read CLAUDE.md for developer notes
- Check deployments/README.md for deployment options
- Visit http://localhost:8050/docs for API documentation
