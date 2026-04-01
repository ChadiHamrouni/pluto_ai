"""Helper functions for budget tracking and savings goals persistence."""

from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, timedelta

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.budget import SavingsGoalCreate, TransactionCreate

logger = get_logger(__name__)


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def add_transaction(
    db_path: str,
    tx_type: str,
    amount: float,
    category: str,
    description: str = "",
    tx_date: str = "",
    recurring: str = "",
    recurring_day: int | None = None,
) -> dict:
    # Validate via Pydantic
    validated = TransactionCreate(
        tx_type=tx_type,  # type: ignore[arg-type]
        amount=amount,
        category=category,
        description=description,
        date=tx_date,
        recurring=recurring,  # type: ignore[arg-type]
        recurring_day=recurring_day,
    )
    effective_date = validated.date or date.today().isoformat()
    conn = _connect(db_path)
    cursor = conn.execute(
        """INSERT INTO budget_transactions
           (type, amount, category, description, date, recurring, recurring_day)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            validated.tx_type,
            validated.amount,
            validated.category,
            validated.description,
            effective_date,
            validated.recurring,
            validated.recurring_day,
        ),
    )
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Added %s transaction id=%d amount=%.2f cat=%s", tx_type, tx_id, amount, category)
    return get_transaction(db_path, tx_id)


def get_transaction(db_path: str, tx_id: int) -> dict | None:
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM budget_transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_transactions(
    db_path: str,
    tx_type: str = "",
    category: str = "",
    from_date: str = "",
    to_date: str = "",
) -> list[dict]:
    clauses = []
    params = []
    if tx_type:
        clauses.append("type = ?")
        params.append(tx_type)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if from_date:
        clauses.append("date >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("date <= ?")
        params.append(to_date)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = _connect(db_path)
    rows = conn.execute(
        f"SELECT * FROM budget_transactions {where} ORDER BY date DESC",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_transaction(db_path: str, tx_id: int) -> bool:
    conn = _connect(db_path)
    cursor = conn.execute("DELETE FROM budget_transactions WHERE id = ?", (tx_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_summary(db_path: str, month: str = "") -> dict:
    """Return income/expense totals and per-category breakdown for a month (YYYY-MM) or all time."""
    conn = _connect(db_path)

    if month:
        year, mon = int(month[:4]), int(month[5:7])
        _, last_day = monthrange(year, mon)
        from_date = f"{month}-01"
        to_date = f"{month}-{last_day:02d}"
        date_filter = "AND date >= ? AND date <= ?"
        date_params = [from_date, to_date]
        cat_where = "WHERE date >= ? AND date <= ?"
    else:
        date_filter = ""
        date_params = []
        cat_where = ""

    def _total(tx_type: str) -> float:
        q = (
            f"SELECT COALESCE(SUM(amount), 0) FROM budget_transactions"
            f" WHERE type = ? {date_filter}"
        )
        row = conn.execute(q, [tx_type] + date_params).fetchone()
        return float(row[0])

    total_income = _total("income")
    total_expense = _total("expense")
    net = total_income - total_expense

    # Per-category breakdown
    rows = conn.execute(
        f"SELECT type, category, SUM(amount) as total"
        f" FROM budget_transactions {cat_where}"
        f" GROUP BY type, category ORDER BY total DESC",
        date_params,
    ).fetchall()
    conn.close()

    by_category: dict[str, dict] = {}
    for r in rows:
        key = f"{r['type']}:{r['category']}"
        by_category[key] = {
            "type": r["type"],
            "category": r["category"],
            "total": round(float(r["total"]), 2),
        }

    return {
        "period": month or "all_time",
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expense, 2),
        "net": round(net, 2),
        "by_category": list(by_category.values()),
    }


# ---------------------------------------------------------------------------
# Savings Goals
# ---------------------------------------------------------------------------

def create_goal(db_path: str, name: str, target_amount: float, deadline: str = "") -> dict:
    validated = SavingsGoalCreate(
        name=name,
        target_amount=target_amount,
        deadline=deadline or None,
    )
    conn = _connect(db_path)
    cursor = conn.execute(
        "INSERT INTO savings_goals (name, target_amount, deadline) VALUES (?, ?, ?)",
        (validated.name, validated.target_amount, validated.deadline),
    )
    goal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Created savings goal id=%d name='%s' target=%.2f", goal_id, name, target_amount)
    # Recalculate immediately so projections are set
    goals = recalculate_goals(db_path)
    return next((g for g in goals if g["id"] == goal_id), {"id": goal_id, "name": name})


def list_goals(db_path: str) -> list[dict]:
    return recalculate_goals(db_path)


def update_goal(db_path: str, goal_id: int, **fields) -> dict | None:
    allowed = {"name", "target_amount", "deadline"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        goals = recalculate_goals(db_path)
        return next((g for g in goals if g["id"] == goal_id), None)
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [goal_id]
    conn = _connect(db_path)
    conn.execute(f"UPDATE savings_goals SET {set_clause} WHERE id = ?", params)
    conn.commit()
    conn.close()
    goals = recalculate_goals(db_path)
    return next((g for g in goals if g["id"] == goal_id), None)


def delete_goal(db_path: str, goal_id: int) -> bool:
    conn = _connect(db_path)
    cursor = conn.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def recalculate_goals(db_path: str) -> list[dict]:
    """
    Recompute current_amount and projections for all savings goals.

    Logic:
    - Net savings = total income - total expenses (all time)
    - Monthly savings rate = average net savings per month over last 3 months
    - current_amount for each goal = net savings (shared pool)
    - projected_completion_date = today + months until (target - current) / monthly_rate
    """
    conn = _connect(db_path)

    # Total net savings
    total_income = float(
        conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions WHERE type = 'income'"
        ).fetchone()[0]
    )
    total_expense = float(
        conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions WHERE type = 'expense'"
        ).fetchone()[0]
    )
    net_savings = total_income - total_expense

    # Monthly savings rate: average over last 3 full calendar months
    today = date.today()
    monthly_rates = []
    for offset in range(1, 4):
        # Walk back offset months
        first_of_this = today.replace(day=1)
        target_month = (first_of_this - timedelta(days=offset * 28)).replace(day=1)
        _, last_day = monthrange(target_month.year, target_month.month)
        m_from = target_month.isoformat()
        m_to = target_month.replace(day=last_day).isoformat()

        _q = (
            "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions"
            " WHERE type = ? AND date >= ? AND date <= ?"
        )
        m_income = float(conn.execute(_q, ("income", m_from, m_to)).fetchone()[0])
        m_expense = float(conn.execute(_q, ("expense", m_from, m_to)).fetchone()[0])
        monthly_rates.append(m_income - m_expense)

    avg_monthly_rate = sum(monthly_rates) / len(monthly_rates) if monthly_rates else 0.0

    # Fetch all goals
    goals = [dict(r) for r in conn.execute("SELECT * FROM savings_goals ORDER BY id").fetchall()]

    # Update each goal
    for goal in goals:
        goal["current_amount"] = round(net_savings, 2)
        goal["percent_complete"] = round(
            min(100.0, (net_savings / goal["target_amount"]) * 100), 1
        ) if goal["target_amount"] > 0 else 0.0
        goal["avg_monthly_savings"] = round(avg_monthly_rate, 2)

        remaining = goal["target_amount"] - net_savings
        if remaining <= 0:
            goal["projected_completion_date"] = "Already funded"
            goal["months_remaining"] = 0
        elif avg_monthly_rate > 0:
            months = remaining / avg_monthly_rate
            projected = today + timedelta(days=int(months * 30.44))
            goal["projected_completion_date"] = projected.isoformat()
            goal["months_remaining"] = round(months, 1)
        else:
            goal["projected_completion_date"] = "Unknown (no savings data yet)"
            goal["months_remaining"] = None

        # Persist updated current_amount
        conn.execute(
            "UPDATE savings_goals SET current_amount = ? WHERE id = ?",
            (goal["current_amount"], goal["id"]),
        )

    conn.commit()
    conn.close()
    return goals
