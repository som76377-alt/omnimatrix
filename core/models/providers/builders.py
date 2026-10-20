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

    timeout_seconds = model.metadata.get("timeout_seconds", 60.0)
    max_retries = model.metadata.get("max_retries", 2)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
    ):
        raise ValueError(f"Model '{model.name}' has an invalid timeout_seconds.")
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
        raise ValueError(f"Model '{model.name}' has an invalid max_retries.")

    return GeminiAdapter(
        name=model.name,
        model_id=model.model_id,
        timeout=float(timeout_seconds),
        max_retries=max_retries,
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
    reasoning_effort = model.metadata.get("reasoning_effort")
    exclude_reasoning = model.metadata.get("exclude_reasoning", True)
    if reasoning_effort is not None and reasoning_effort not in {
        "minimal", "low", "medium", "high", "xhigh", "none"
    }:
        raise ValueError(f"Model '{model.name}' has an invalid reasoning_effort.")
    if not isinstance(exclude_reasoning, bool):
        raise ValueError(f"Model '{model.name}' has an invalid exclude_reasoning.")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int):
        raise ValueError(f"Model '{model.name}' has an invalid max_output_tokens.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError(f"Model '{model.name}' has an invalid timeout_seconds.")

    return OpenRouterAdapter(
        name=model.name,
        model_id=model.model_id,
        api_key_env=api_key_env,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
        exclude_reasoning=exclude_reasoning,
        timeout=float(timeout_seconds),
    )
