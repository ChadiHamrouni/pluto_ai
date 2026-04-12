"""Calculator @function_tool — grounded arithmetic for the agent."""

from __future__ import annotations

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.calculator import safe_eval

logger = get_logger(__name__)


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
        result = safe_eval(expression)
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
