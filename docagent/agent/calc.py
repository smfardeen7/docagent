"""Arithmetic over an AST whitelist. Never calls eval()."""

import ast
import operator

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_EXP = 64


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXP:
            raise ValueError("exponent too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported expression: {type(node).__name__}")


def safe_calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        value = _eval(tree.body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as e:
        return f"error: {e}"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)
