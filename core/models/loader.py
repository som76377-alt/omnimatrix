import json
from pathlib import Path
from typing import Any

from core.models.registry import ModelDefinition, ModelRegistry


class ModelConfigLoader:
    """Loads and validates model definitions from a JSON configuration file."""

    def load(self, path: str | Path) -> ModelRegistry:
        config_path = Path(path)

        with config_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Model configuration must be a JSON object.")

        models = data.get("models")

        if not isinstance(models, list):
            raise ValueError("'models' must be a list.")

        registry = ModelRegistry()

        for index, entry in enumerate(models):
            self._validate_entry(entry, index)

            model = ModelDefinition(
                name=entry["name"],
                provider=entry["provider"],
                capabilities=frozenset(entry.get("capabilities", [])),
                context_window=entry.get("context_window"),
                enabled=entry.get("enabled", True),
                metadata=entry.get("metadata", {}),
            )

            registry.register(model)

        return registry

    def _validate_entry(self, entry: Any, index: int) -> None:
        if not isinstance(entry, dict):
            raise ValueError(
                f"Model entry at index {index} must be an object."
            )

        name = entry.get("name")
        provider = entry.get("provider")
        capabilities = entry.get("capabilities", [])
        context_window = entry.get("context_window")
        enabled = entry.get("enabled", True)
        metadata = entry.get("metadata", {})

        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Model entry at index {index} has an invalid name."
            )

        if not isinstance(provider, str) or not provider.strip():
            raise ValueError(
                f"Model '{name}' has an invalid provider."
            )

        if (
            not isinstance(capabilities, list)
            or not all(isinstance(item, str) and item.strip() for item in capabilities)
        ):
            raise ValueError(
                f"Model '{name}' has invalid capabilities."
            )

        if context_window is not None:
            if (
                not isinstance(context_window, int)
                or isinstance(context_window, bool)
                or context_window <= 0
            ):
                raise ValueError(
                    f"Model '{name}' has an invalid context_window."
                )

        if not isinstance(enabled, bool):
            raise ValueError(
                f"Model '{name}' has an invalid enabled value."
            )

        if not isinstance(metadata, dict):
            raise ValueError(
                f"Model '{name}' has invalid metadata."
            )
