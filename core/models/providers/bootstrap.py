from core.models.adapters import AdapterRegistry
from core.models.factory import ModelAdapterFactory
from core.models.providers.builders import build_gemini_adapter
from core.models.registry import ModelRegistry


def build_adapter_registry(
    registry: ModelRegistry,
) -> AdapterRegistry:
    """Build adapters for all enabled models in the model registry."""

    adapter_registry = AdapterRegistry()

    factory = ModelAdapterFactory()
    factory.register("google", build_gemini_adapter)

    for model in registry.list_enabled():
        adapter = factory.create(model)
        adapter_registry.register(adapter)

    return adapter_registry