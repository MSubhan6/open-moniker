# Project Notes for Claude

## Environment
- Use `python` not `python3` (conda environment)
- PYTHONPATH=src for running the service
- Start server: `PYTHONPATH=src uvicorn moniker_svc.main:app --host 0.0.0.0 --port 8050`

## Project Structure
- Source code in `src/moniker_svc/`
- Config files: `config.yaml`, `catalog.yaml`, `domains.yaml`
- Sample configs use `sample_` prefix (e.g., `sample_config.yaml`)
