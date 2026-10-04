from .base import LLMProvider, Message
from .fake import FakeProvider

__all__ = ["LLMProvider", "Message", "FakeProvider", "make_provider"]


def make_provider(settings) -> LLMProvider:
    """Build the configured provider lazily so importing this package never loads a model."""
    if settings.provider == "fake":
        return FakeProvider([])
    if settings.provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.anthropic_model)
    from .hf_local import HFLocalProvider

    return HFLocalProvider(settings.generation_model)
