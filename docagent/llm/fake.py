from collections.abc import Callable

from .base import Message


class FakeProvider:
    """Scripted provider for tests: a list of canned replies, or a callable that computes one from the messages."""

    name = "fake"

    def __init__(self, responses: list[str] | Callable[[list[Message]], str]):
        self._fn = responses if callable(responses) else None
        self._responses = None if callable(responses) else list(responses)
        self.calls: list[list[Message]] = []

    def generate(self, messages: list[Message], max_new_tokens: int = 384) -> str:
        self.calls.append(list(messages))
        if self._fn is not None:
            return self._fn(messages)
        if not self._responses:
            raise RuntimeError("FakeProvider responses exhausted")
        return self._responses.pop(0)
