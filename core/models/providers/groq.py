"""Groq's OpenAI-compatible Chat Completions adapter.

This reuses the validated Chat Completions request/response handling but uses
Groq's endpoint and reports Groq as the provider identity.
"""
from __future__ import annotations

from core.models.providers.openrouter import OpenRouterAdapter


class GroqAdapter(OpenRouterAdapter):
    """Groq Cloud adapter using an explicit model ID and key environment variable."""

    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    @property
    def provider(self) -> str:
        return "groq"
