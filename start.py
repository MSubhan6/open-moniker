#!/usr/bin/env python
"""Start the Moniker Service."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("moniker_svc.main:app", host="0.0.0.0", port=8050, reload=False)
