from core.models.base import ModelAdapter
from core.models.providers.gemini import GeminiAdapter
from core.models.registry import ModelDefinition


def build_gemini_adapter(model: ModelDefinition) -> ModelAdapter:
    """Build a Gemini adapter from a model definition."""

    if model.provider != "google":
        raise ValueError(
            f"Expected Google provider, got: {model.provider}"
        )

    if not model.model_id:
        raise ValueError(
            f"Model '{model.name}' requires a model_id."
        )

    return GeminiAdapter(
        name=model.name,
        model_id=model.model_id,
    )