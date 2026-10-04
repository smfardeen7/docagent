from .base import Message


class AnthropicProvider:
    """Optional hosted provider. Needs ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model: str):
        import anthropic

        self.name = f"anthropic:{model}"
        self._client = anthropic.Anthropic()
        self._model = model

    def generate(self, messages: list[Message], max_new_tokens: int = 384) -> str:
        system = "\n".join(m.content for m in messages if m.role == "system")
        chat = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        kwargs = {"model": self._model, "max_tokens": max_new_tokens, "messages": chat}
        if system:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
