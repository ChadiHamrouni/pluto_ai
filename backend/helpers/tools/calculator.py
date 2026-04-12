"""Safe arithmetic evaluator used by the calculate function_tool."""

from __future__ import annotations

import ast
import math
import operator
from typing import Union

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pi": math.pi,
    "e": math.e,
}


def _eval_node(node: ast.AST) -> Union[int, float]:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _SAFE_FUNCTIONS:
        val = _SAFE_FUNCTIONS[node.id]
        if isinstance(val, (int, float)):
            return val
        raise ValueError(f"'{node.id}' is a function, not a value")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent too large")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCTIONS:
            fn = _SAFE_FUNCTIONS[node.func.id]
            if callable(fn):
                args = [_eval_node(a) for a in node.args]
                return fn(*args)
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def safe_eval(expr: str) -> Union[int, float]:
    expr = expr.strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {exc}") from exc
    return _eval_node(tree.body)
