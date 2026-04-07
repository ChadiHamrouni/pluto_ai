"""Budget tracking @function_tool wrappers for the DashboardAgent."""

from __future__ import annotations

import json

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.budget import (
    add_transaction as _add_transaction,
)
from helpers.tools.budget import (
    create_goal as _create_goal,
)
from helpers.tools.budget import (
    delete_goal as _delete_goal,
)
from helpers.tools.budget import (
    delete_transaction as _delete_transaction,
)
from helpers.tools.budget import (
    get_db_path,
)
from helpers.tools.budget import (
    get_summary as _get_summary,
    get_summary_range as _get_summary_range,
)
from helpers.tools.budget import (
    list_goals as _list_goals,
)
from helpers.tools.budget import (
    list_transactions as _list_transactions,
)
from helpers.tools.budget import (
    recalculate_goals as _recalculate_goals,
)

logger = get_logger(__name__)

VALID_TYPES = {"income", "expense"}
VALID_RECURRING = {"", "monthly", "weekly", "yearly"}


@function_tool
def add_transaction(
    tx_type: str,
    amount: float,
    category: str,
    currency: str = "TND",
    description: str = "",
    date: str = "",
    recurring: str = "",
) -> str:
    """
    Record an income or expense transaction. Goals and projections update automatically.

    Use this when the user says they earned money, spent money, bought something,
    paid a bill, received a salary, got paid, etc. Every transaction immediately
    recalculates all savings goals and projections.

    IMPORTANT: Always record the currency the user actually mentioned (TND, USD, EUR, etc.).
    Never assume a currency — if the user says "1000 TND", use currency="TND".
    Default currency is TND (Tunisian Dinar) if the user doesn't specify.

    Args:
        tx_type:     REQUIRED. Either "income" or "expense".
        amount:      REQUIRED. Positive numeric amount (e.g. 1000.0). Use the exact
                     number the user stated — never convert or invent values.
        currency:    Currency code (e.g. "TND", "USD", "EUR"). Default: "TND".
        category:    REQUIRED. One of: salary, freelance, food, transport, rent,
                     utilities, subscriptions, entertainment, health, education,
                     savings, other.
        description: Optional note (e.g. "Netflix subscription", "freelance project X").
        date:        ISO-8601 date (e.g. "2026-03-31"). Defaults to today if empty.
        recurring:   Recurrence: "monthly", "weekly", "yearly", or "" for one-time.

    Returns:
        Confirmation string with the transaction id and updated goal summary.
    """
    if tx_type not in VALID_TYPES:
        return f"Error: tx_type must be 'income' or 'expense', got '{tx_type}'."
    if amount <= 0:
        return "Error: amount must be a positive number."
    if recurring not in VALID_RECURRING:
        return f"Error: recurring must be one of: {sorted(VALID_RECURRING)}."

    db_path = get_db_path()
    try:
        tx = _add_transaction(db_path, tx_type, amount, category, description, date, recurring, currency=currency)
        goals = _recalculate_goals(db_path)

        goal_lines = []
        for g in goals:
            pct = g.get("percent_complete", 0)
            proj = g.get("projected_completion_date", "Unknown")
            goal_lines.append(f"  • {g['name']}: {pct}% funded → {proj}")

        goal_summary = "\n".join(goal_lines) if goal_lines else "  (no savings goals yet)"
        currency_code = tx.get("currency", currency).upper()
        return (
            f"Transaction recorded (id={tx['id']}): {tx_type} {amount:.2f} {currency_code} [{category}]"
            f"{' — ' + description if description else ''}\n"
            f"Goals updated:\n{goal_summary}"
        )
    except Exception as exc:
        logger.error("add_transaction failed: %s", exc)
        return f"Failed to record transaction: {exc}"


@function_tool
def list_transactions(
    tx_type: str = "",
    category: str = "",
    from_date: str = "",
    to_date: str = "",
) -> str:
    """
    List budget transactions, optionally filtered.

    Args:
        tx_type:   Filter by "income" or "expense". Empty = all.
        category:  Filter by category name. Empty = all.
        from_date: ISO-8601 start date (e.g. "2026-03-01"). Empty = no lower bound.
        to_date:   ISO-8601 end date (e.g. "2026-03-31"). Empty = no upper bound.

    Returns:
        JSON array of transaction objects, or a message if none found.
    """
    try:
        txs = _list_transactions(get_db_path(), tx_type, category, from_date, to_date)
        if not txs:
            return "No transactions found matching those filters."
        return json.dumps(txs, indent=2)
    except Exception as exc:
        logger.error("list_transactions failed: %s", exc)
        return f"Failed to list transactions: {exc}"


@function_tool
def delete_transaction(transaction_id: int) -> str:
    """
    Delete a transaction and recalculate all savings goals.

    Use this to correct a mistake or remove an entry. Goals update automatically.

    Args:
        transaction_id: The numeric id of the transaction to delete.

    Returns:
        Confirmation string with updated goal summary, or error.
    """
    db_path = get_db_path()
    try:
        deleted = _delete_transaction(db_path, transaction_id)
        if not deleted:
            return f"No transaction found with id={transaction_id}."
        goals = _recalculate_goals(db_path)
        goal_lines = [
            f"  • {g['name']}: {g.get('percent_complete', 0)}% funded"
            f" → {g.get('projected_completion_date', 'Unknown')}"
            for g in goals
        ]
        goal_summary = "\n".join(goal_lines) if goal_lines else "  (no savings goals)"
        return f"Transaction {transaction_id} deleted.\nGoals updated:\n{goal_summary}"
    except Exception as exc:
        logger.error("delete_transaction failed: %s", exc)
        return f"Failed to delete transaction: {exc}"


@function_tool
def budget_summary(month: str = "", from_month: str = "", to_month: str = "") -> str:
    """
    Get a full budget summary with income, expenses, net, and goal progress.

    Use this when the user asks about their finances, spending, budget overview,
    how much they've saved, or how their goals are doing.

    ALWAYS call this after add_transaction or delete_transaction to show updated numbers.
    NEVER compute totals yourself — always call this tool and report what it returns.

    Args:
        month:      Single month in "YYYY-MM" format (e.g. "2026-04"). Empty = all-time.
        from_month: Start of a month range (e.g. "2026-04"). Use with to_month for multi-month view.
        to_month:   End of a month range (e.g. "2026-09"). Use with from_month for multi-month view.

    Returns:
        JSON object with totals, per-month breakdown (if range), per-category breakdown, and savings goals.
    """
    db_path = get_db_path()
    try:
        if from_month and to_month:
            summary = _get_summary_range(db_path, from_month, to_month)
        else:
            summary = _get_summary(db_path, month)
        goals = _recalculate_goals(db_path)
        summary["savings_goals"] = goals
        return json.dumps(summary, indent=2)
    except Exception as exc:
        logger.error("budget_summary failed: %s", exc)
        return f"Failed to get budget summary: {exc}"


@function_tool
def create_savings_goal(name: str, target_amount: float, deadline: str = "") -> str:
    """
    Create a savings goal. Progress and projections calculate automatically from transactions.

    Args:
        name:          REQUIRED. Goal name (e.g. "Emergency fund", "Laptop upgrade").
        target_amount: REQUIRED. Target amount to save (e.g. 5000.0).
        deadline:      Optional target date in ISO-8601 (e.g. "2026-12-31").

    Returns:
        Confirmation with current progress and projected completion date.
    """
    if target_amount <= 0:
        return "Error: target_amount must be a positive number."
    try:
        goal = _create_goal(get_db_path(), name, target_amount, deadline)
        pct = goal.get("percent_complete", 0)
        proj = goal.get("projected_completion_date", "Unknown")
        return (
            f"Savings goal created (id={goal['id']}): \"{name}\" — "
            f"target {target_amount:.2f}, currently {pct}% funded, "
            f"projected completion: {proj}"
        )
    except Exception as exc:
        logger.error("create_savings_goal failed: %s", exc)
        return f"Failed to create savings goal: {exc}"


@function_tool
def list_savings_goals() -> str:
    """
    List all savings goals with live progress and projections.

    Shows current funding level, percentage complete, average monthly savings rate,
    and projected completion date based on recent spending/income patterns.

    Returns:
        JSON array of goal objects including projections, or a message if none exist.
    """
    try:
        goals = _list_goals(get_db_path())
        if not goals:
            return "No savings goals found. Use create_savings_goal to add one."
        return json.dumps(goals, indent=2)
    except Exception as exc:
        logger.error("list_savings_goals failed: %s", exc)
        return f"Failed to list savings goals: {exc}"


@function_tool
def delete_savings_goal(goal_id: int) -> str:
    """
    Delete a savings goal.

    Args:
        goal_id: The numeric id of the goal to delete.

    Returns:
        Confirmation or error string.
    """
    try:
        deleted = _delete_goal(get_db_path(), goal_id)
        if deleted:
            return f"Savings goal {goal_id} deleted."
        return f"No savings goal found with id={goal_id}."
    except Exception as exc:
        logger.error("delete_savings_goal failed: %s", exc)
        return f"Failed to delete savings goal: {exc}"
