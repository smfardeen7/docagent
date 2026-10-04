import json
from dataclasses import dataclass


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class ToolCall:
    thought: str
    tool: str
    args: dict


def _extract_first_object(text: str) -> str | None:
    """Return the first balanced {...} span, honouring braces inside JSON strings."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def parse_tool_call(text: str) -> ToolCall:
    raw = _extract_first_object(text)
    if raw is None:
        raise ParseError("no JSON object found")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ParseError("expected a JSON object")
    tool = obj.get("tool")
    if not isinstance(tool, str) or not tool:
        raise ParseError("missing 'tool' string")
    args = obj.get("args", {})
    if not isinstance(args, dict):
        raise ParseError("'args' must be an object")
    return ToolCall(thought=str(obj.get("thought", "")), tool=tool, args=args)
