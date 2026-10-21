from core.models.adapters import AdapterRegistry
from core.models.factory import ModelAdapterFactory
from core.models.providers.builders import build_gemini_adapter
from core.models.providers.builders import build_freellmapi_adapter
from core.models.providers.builders import build_groq_adapter
from core.models.providers.builders import build_openrouter_adapter
from core.models.providers.demo import DemoAdapter
from core.models.registry import ModelRegistry


def build_adapter_registry(
    registry: ModelRegistry,
) -> AdapterRegistry:
    """Build adapters for all enabled models in the model registry."""

    adapter_registry = AdapterRegistry()

    factory = ModelAdapterFactory()
    factory.register("google", build_gemini_adapter)
    factory.register("openrouter", build_openrouter_adapter)
    factory.register("groq", build_groq_adapter)
    factory.register("freellmapi", build_freellmapi_adapter)
    factory.register(
        "demo",
        lambda model: DemoAdapter(
            name=model.name,
            model_id=model.model_id,
        ),
    )

    for model in registry.list_enabled():
        adapter = factory.create(model)
        adapter_registry.register(adapter)

    return adapter_registry
