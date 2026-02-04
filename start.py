#!/usr/bin/env python
"""Start the Moniker Service."""

import os
import sys
from pathlib import Path

# Change to script directory so relative paths work correctly
script_dir = Path(__file__).parent.resolve()
os.chdir(script_dir)

# Add src to path
src_path = script_dir / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("moniker_svc.main:app", host="0.0.0.0", port=8050, reload=False)
