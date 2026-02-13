"""
Business Models Layer

Provides business model/measure/field definitions that can appear across
multiple monikers. Models represent the "what it means" layer in the
three-layer architecture:

    Model (business concept)  →  Moniker (data path)  →  Binding (data source)
           ↓                           ↓                        ↓
       "What it means"         "Where it lives"         "How to get it"

Example: "risk.analytics/dv01" is a Model representing DV01 that appears
in monikers like "risk/cvar/*/USD", "portfolios/*/risk", etc.
"""

from .types import Model, ModelOwnership, MonikerLink
from .registry import ModelRegistry
from .loader import load_models_from_yaml
from .serializer import save_models_to_yaml

__all__ = [
    "Model",
    "ModelOwnership",
    "MonikerLink",
    "ModelRegistry",
    "load_models_from_yaml",
    "save_models_to_yaml",
]
