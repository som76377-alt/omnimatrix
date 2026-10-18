from core.models.base import ModelAdapter
from core.models.providers.gemini import GeminiAdapter
from core.models.providers.openrouter import OpenRouterAdapter
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



def build_openrouter_adapter(model: ModelDefinition) -> ModelAdapter:
    """Build an OpenRouter adapter from an explicit model profile."""
    if model.provider != "openrouter":
        raise ValueError(f"Expected OpenRouter provider, got: {model.provider}")
    if not model.model_id:
        raise ValueError(f"Model '{model.name}' requires a model_id.")

    api_key_env = model.metadata.get("api_key_env", "OPENROUTER_API_KEY")
    if not isinstance(api_key_env, str) or not api_key_env.strip():
        raise ValueError(f"Model '{model.name}' has an invalid api_key_env.")

    max_output_tokens = model.metadata.get("max_output_tokens", 8192)
    timeout_seconds = model.metadata.get("timeout_seconds", 60.0)
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int):
        raise ValueError(f"Model '{model.name}' has an invalid max_output_tokens.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError(f"Model '{model.name}' has an invalid timeout_seconds.")

    return OpenRouterAdapter(
        name=model.name,
        model_id=model.model_id,
        api_key_env=api_key_env,
        max_output_tokens=max_output_tokens,
        timeout=float(timeout_seconds),
    )
