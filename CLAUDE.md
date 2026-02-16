# Project Notes for Claude

## Git Workflow
- **Identity**: You are MSubhan6 with full repo access
- **Development**: Work on feature branches, push to MSubhan6 repos (origin)
- **Integration**: Create PRs from MSubhan6 → ganizanisitara when ready
- **Remotes**:
  - `origin`: https://github.com/MSubhan6/open-moniker.git (push here)
  - `upstream`: https://github.com/ganizanisitara/open-moniker-svc.git (PR target)
- **Note**: This file (CLAUDE.md) is gitignored and stays local

## Environment
- Use `python3` (system Python 3.13)
- PYTHONPATH=src for running the service
- Start server: `PYTHONPATH=src python3 -m uvicorn moniker_svc.main:app --host 0.0.0.0 --port 8050`

## Full Environment Bring-Up
To boot the full simulated environment (adapters + server + smoke tests) and open Jupyter for interactive testing:

1. **Start the service** (from `~/open-moniker-client`):
   ```bash
   cd ~/open-moniker-client && python3 bring_up.py --server > /tmp/bring_up.log 2>&1 &
   ```
   This warms all 5 mock adapters (Oracle, Snowflake, MS-SQL, REST, Excel), starts FastAPI on port 8050, and runs 12 smoke tests.

2. **Start Jupyter and open in browser**:
   ```bash
   PYTHONPATH=~/open-moniker-svc/src:~/open-moniker-svc/external/moniker-data/src:~/open-moniker-client \
     python3 -m jupyter notebook --ip=0.0.0.0 --port=8888 \
     --NotebookApp.token='' --NotebookApp.password='' \
     --notebook-dir=~/open-moniker-client/notebooks > /tmp/jupyter.log 2>&1 &
   ```
   Then open in the default browser:
   ```bash
   python3 -c "import webbrowser; webbrowser.open('http://localhost:8888/notebooks/showcase.ipynb')"
   ```

- The showcase notebook (`~/open-moniker-client/notebooks/showcase.ipynb`) has full setup cells that initialize all adapters and create a MonikerClient pointing at localhost:8050.
- Always open Jupyter in the default browser — don't use `--no-browser`.

## Project Structure
- Source code in `src/moniker_svc/`
- Config files: `config.yaml`, `catalog.yaml`, `domains.yaml`
- Sample configs use `sample_` prefix (e.g., `sample_config.yaml`)
