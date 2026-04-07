"""Calculator @function_tool — grounded arithmetic for the agent."""

from __future__ import annotations

import ast
import math
import operator
from typing import Union

from agents import function_tool

from helpers.core.logger import get_logger

logger = get_logger(__name__)

# Safe operators only — no imports, no builtins, no side effects
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


def _safe_eval(expr: str) -> Union[int, float]:
    expr = expr.strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression: {exc}") from exc
    return _eval_node(tree.body)


@function_tool
def calculate(expression: str) -> str:
    """
    Evaluate a math expression and return the exact result.

    Use this for ANY arithmetic — addition, subtraction, multiplication, division,
    percentages, powers, roots — especially in budgeting calculations. Never guess
    or approximate: always call this tool to get the correct number.

    Supports: +, -, *, /, // (floor div), % (modulo), ** or ^ (power),
              abs(), round(), sqrt(), ceil(), floor(), log(), log10(),
              sin(), cos(), tan(), pi, e.

    Args:
        expression: A math expression string (e.g. "1000 * 0.18", "sqrt(144)",
                    "1500 + 320 - 75", "2 ** 10", "round(1000/3, 2)").

    Returns:
        The result as a string, or an error message if the expression is invalid.

    Examples:
        calculate("1000 + 500")       → "1500.0"
        calculate("3000 * 0.9")       → "2700.0"
        calculate("sqrt(144)")        → "12.0"
        calculate("round(1000/3, 2)") → "333.33"
    """
    try:
        result = _safe_eval(expression)
        # Return int if result is a whole number, float otherwise
        if isinstance(result, float) and result.is_integer():
            return str(int(result))
        return str(round(result, 10)).rstrip("0").rstrip(".")
    except ZeroDivisionError:
        return "Error: division by zero."
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.warning("calculate failed for %r: %s", expression, exc)
        return f"Error: could not evaluate '{expression}'."
