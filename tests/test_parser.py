import pytest

from docagent.agent.parser import ParseError, parse_tool_call


def test_plain_json():
    c = parse_tool_call('{"thought": "look", "tool": "search_docs", "args": {"query": "meals", "k": 3}}')
    assert c.tool == "search_docs" and c.args["k"] == 3 and c.thought == "look"


def test_json_in_code_fence_with_prose():
    text = 'Sure, here is my call:\n```json\n{"thought":"t","tool":"calculate","args":{"expression":"1+1"}}\n```\nDone.'
    assert parse_tool_call(text).tool == "calculate"


def test_nested_braces_in_strings():
    text = '{"thought": "the {weird} one", "tool": "final_answer", "args": {"answer": "x } y", "citations": [1]}}'
    c = parse_tool_call(text)
    assert c.args["answer"] == "x } y"


def test_missing_args_defaults_to_empty():
    assert parse_tool_call('{"tool": "search_docs"}').args == {}


def test_first_object_wins_when_model_emits_two():
    text = '{"tool": "search_docs", "args": {"query": "a"}} {"tool": "final_answer", "args": {}}'
    assert parse_tool_call(text).tool == "search_docs"


@pytest.mark.parametrize("bad", ["no json here", '{"tool": 5}', '{"args": {}}', '{"tool": "x", "args": []}', "{unbalanced", "{} tool"])
def test_invalid_raises(bad):
    with pytest.raises(ParseError):
        parse_tool_call(bad)
