import json
import re

from docagent.agent import build_agent_system_prompt, build_default_tools, parse_tool_call
from docagent.store import Store


def test_system_prompt_lists_tools_and_shows_a_parseable_example(tmp_path):
    reg = build_default_tools(retriever=None, store=Store(tmp_path / "t.db"))
    prompt = build_agent_system_prompt(reg)
    for name in ["search_docs", "read_chunk", "compare", "calculate", "final_answer"]:
        assert name in prompt
    # the worked example must itself be a valid tool call, so the model copies a good shape
    examples = re.findall(r"Example[^\n]*\n(\{.*?\})\n", prompt, flags=re.S)
    assert examples, "prompt should contain at least one worked example"
    for ex in examples:
        call = parse_tool_call(ex)
        assert call.tool in set(reg.names()) | {"final_answer"}
        json.loads(ex)  # strict JSON, no trailing prose
    assert "complete sentence" in prompt and "exact" in prompt
