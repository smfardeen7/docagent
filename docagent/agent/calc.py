"""Arithmetic over an AST whitelist. Never calls eval(); bounds the size of every intermediate result."""

import ast
import operator

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_RESULT_BITS = 2048  # ~600 decimal digits; nothing an answer would ever quote needs more


def _checked_pow(left, right):
    # Big-int pow holds the GIL for as long as the result takes to build, so bound the result before computing it.
    if isinstance(left, int) and isinstance(right, int) and right > 0 and abs(left) > 1:
        if left.bit_length() * right > MAX_RESULT_BITS:
            raise ValueError("result too large")
    return operator.pow(left, right)


def _eval(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        return _checked_pow(_eval(node.left), _eval(node.right))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        value = _BIN[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(value, int) and value.bit_length() > MAX_RESULT_BITS:
            raise ValueError("result too large")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported expression: {type(node).__name__}")


def safe_calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        value = _eval(tree.body)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, MemoryError) as e:
        return f"error: {e}"
