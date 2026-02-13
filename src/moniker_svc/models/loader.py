"""
Model configuration loaders.

Load business models from YAML files.
"""

from pathlib import Path

import yaml

from .types import Model
from .registry import ModelRegistry


def load_models_from_yaml(
    file_path: str | Path,
    registry: ModelRegistry | None = None
) -> list[Model]:
    """
    Load models from a YAML file.

    Expected format:
        risk.analytics:
          display_name: Risk Analytics
          description: Risk measurement models
          ownership:
            methodology_owner: quant-research@firm.com

        risk.analytics/dv01:
          display_name: Dollar Value of 01
          description: Change in value for 1bp yield shift
          formula: "dV/dy × 0.0001"
          unit: USD
          appears_in:
            - moniker_pattern: "risk.cvar/*/*"
              column_name: DV01
            - moniker_pattern: "portfolios/*/risk/*"

    Args:
        file_path: Path to the YAML file
        registry: Optional registry to populate

    Returns:
        List of loaded models
    """
    path = Path(file_path)
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    models = []
    for model_path, config in data.items():
        if isinstance(config, dict):
            model = Model.from_dict(model_path, config)
            models.append(model)
            if registry is not None:
                registry.register_or_update(model)

    return models
