"""
Model configuration serializer.

Save business models to YAML format.
"""

import os
from pathlib import Path

import yaml

from .types import Model
from .registry import ModelRegistry


def save_models_to_yaml(
    models: list[Model] | ModelRegistry,
    file_path: str | Path
) -> None:
    """
    Save models to a YAML file.

    Output format:
        # Business Models Configuration
        # Measures, metrics, and fields that appear across monikers

        risk.analytics:
          display_name: Risk Analytics
          ...

        risk.analytics/dv01:
          display_name: Dollar Value of 01
          ...

    Args:
        models: List of models or a ModelRegistry
        file_path: Path to write the YAML file
    """
    if isinstance(models, ModelRegistry):
        model_list = models.all_models()
    else:
        model_list = sorted(models, key=lambda m: m.path)

    # Build the YAML structure
    data = {}
    for model in model_list:
        model_data = model.to_dict()
        # Remove the path key since it's the YAML key
        model_data.pop("path", None)
        # Only include non-empty values
        model_data = {
            k: v for k, v in model_data.items()
            if v is not None and (v or isinstance(v, bool))
        }
        data[model.path] = model_data

    path = Path(file_path).resolve()
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Business Models Configuration\n")
        f.write("# Measures, metrics, and fields that appear across monikers\n\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        f.flush()
        os.fsync(f.fileno())
