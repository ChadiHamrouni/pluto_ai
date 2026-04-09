"""Helper functions for budget tracking and savings goals persistence."""

from __future__ import annotations

import sqlite3
from calendar import monthrange
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.budget import SavingsGoalCreate, TransactionCreate

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Recurring expansion
# ---------------------------------------------------------------------------

def _expand_recurring(rows: list, as_of: date) -> list[dict]:
    """
    Expand recurring transactions into one dict per occurrence up to `as_of`.

    For a "monthly" transaction recorded on 2026-03-15 with as_of=2026-06-01:
      → occurrences on 2026-03-15, 2026-04-15, 2026-05-15  (June not yet reached)

    Non-recurring rows are returned as-is (one dict each).
    """
    expanded: list[dict] = []
    for row in rows:
        d = row if isinstance(row, dict) else dict(row)
        recurring = d.get("recurring", "")
        start = date.fromisoformat(d["date"])

        if not recurring or start > as_of:
            if start <= as_of:
                expanded.append(d)
            continue

        # Generate all occurrences from start up to (but not including) as_of+1
        occurrence = start
        while occurrence <= as_of:
            expanded.append({**d, "date": occurrence.isoformat()})
            if recurring == "monthly":
                occurrence += relativedelta(months=1)
            elif recurring == "weekly":
                occurrence += timedelta(weeks=1)
            elif recurring == "yearly":
                occurrence += relativedelta(years=1)
            else:
                break  # unknown recurrence — treat as one-time

    return expanded


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
    currency: str = "TND",
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
    currency = currency.strip().upper() or "TND"
    conn = _connect(db_path)
    cursor = conn.execute(
        """INSERT INTO budget_transactions
           (type, amount, category, description, date, recurring, recurring_day, currency)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            validated.tx_type,
            validated.amount,
            validated.category,
            validated.description,
            effective_date,
            validated.recurring,
            validated.recurring_day,
            currency,
        ),
    )
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Added %s transaction id=%d amount=%.2f %s cat=%s", tx_type, tx_id, amount, currency, category)
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


def get_summary_range(db_path: str, from_month: str, to_month: str) -> dict:
    """Return per-month breakdown from from_month to to_month (both inclusive, YYYY-MM format)."""
    conn = _connect(db_path)
    all_rows = conn.execute("SELECT * FROM budget_transactions").fetchall()
    conn.close()

    today = date.today()
    fy, fm = int(from_month[:4]), int(from_month[5:7])
    ty, tm = int(to_month[:4]), int(to_month[5:7])

    months = []
    cy, cm = fy, fm
    while (cy, cm) <= (ty, tm):
        months.append((cy, cm))
        cm += 1
        if cm > 12:
            cm = 1
            cy += 1

    # Expand recurring up to end of to_month — no cap at today, so future months are projected
    _, last_day_to = monthrange(ty, tm)
    as_of = date(ty, tm, last_day_to)
    expanded = _expand_recurring(all_rows, as_of)

    # Compute opening balance = net of everything before from_month
    range_start = date(fy, fm, 1).isoformat()
    prior = [r for r in expanded if r["date"] < range_start]
    opening_balance = round(
        sum(r["amount"] for r in prior if r["type"] == "income") -
        sum(r["amount"] for r in prior if r["type"] == "expense"),
        2,
    )

    monthly_rows = []
    total_income = total_expense = 0.0
    by_category: dict[str, dict] = {}
    running_balance = opening_balance

    for year, mon in months:
        _, last_day = monthrange(year, mon)
        m_start = date(year, mon, 1).isoformat()
        m_end = date(year, mon, last_day).isoformat()
        m_rows = [r for r in expanded if m_start <= r["date"] <= m_end]
        m_income = sum(r["amount"] for r in m_rows if r["type"] == "income")
        m_expense = sum(r["amount"] for r in m_rows if r["type"] == "expense")
        total_income += m_income
        total_expense += m_expense
        running_balance = round(running_balance + m_income - m_expense, 2)
        monthly_rows.append({
            "month": f"{year}-{mon:02d}",
            "income": round(m_income, 2),
            "expenses": round(m_expense, 2),
            "net": round(m_income - m_expense, 2),
            "balance": running_balance,
            "projected": date(year, mon, 1) > today,
        })
        for r in m_rows:
            key = f"{r['type']}:{r['category']}"
            if key not in by_category:
                by_category[key] = {"type": r["type"], "category": r["category"], "total": 0.0}
            by_category[key]["total"] = round(by_category[key]["total"] + r["amount"], 2)

    return {
        "period": f"{from_month} to {to_month}",
        "opening_balance": opening_balance,
        "monthly_breakdown": monthly_rows,
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expense, 2),
        "net": round(total_income - total_expense, 2),
        "closing_balance": running_balance,
        "by_category": sorted(by_category.values(), key=lambda x: x["total"], reverse=True),
    }


def get_summary(db_path: str, month: str = "") -> dict:
    """Return income/expense totals and per-category breakdown for a month (YYYY-MM) or all time.

    Recurring transactions are expanded into all occurrences up to today (or the end of the
    requested month), so a "monthly" expense recorded once is counted every month it applies.
    """
    conn = _connect(db_path)
    all_rows = conn.execute("SELECT * FROM budget_transactions").fetchall()
    conn.close()

    today = date.today()
    if month:
        year, mon = int(month[:4]), int(month[5:7])
        _, last_day = monthrange(year, mon)
        period_start = date(year, mon, 1)
        period_end = date(year, mon, last_day)
        as_of = min(period_end, today)
    else:
        period_start = None
        period_end = None
        as_of = today

    # Expand recurring transactions into all occurrences up to as_of
    expanded = _expand_recurring(all_rows, as_of)

    # Filter to period if requested
    if period_start:
        expanded = [r for r in expanded if period_start.isoformat() <= r["date"] <= period_end.isoformat()]

    total_income = sum(r["amount"] for r in expanded if r["type"] == "income")
    total_expense = sum(r["amount"] for r in expanded if r["type"] == "expense")
    net = total_income - total_expense

    by_category: dict[str, dict] = {}
    for r in expanded:
        key = f"{r['type']}:{r['category']}"
        if key not in by_category:
            by_category[key] = {"type": r["type"], "category": r["category"], "total": 0.0}
        by_category[key]["total"] = round(by_category[key]["total"] + r["amount"], 2)

    return {
        "period": month or "all_time",
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expense, 2),
        "net": round(net, 2),
        "by_category": sorted(by_category.values(), key=lambda x: x["total"], reverse=True),
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
    all_rows = [dict(r) for r in conn.execute("SELECT * FROM budget_transactions").fetchall()]

    today = date.today()

    # Expand all recurring transactions up to today
    expanded = _expand_recurring(all_rows, today)

    # Total net savings (all time, expanded)
    total_income = sum(r["amount"] for r in expanded if r["type"] == "income")
    total_expense = sum(r["amount"] for r in expanded if r["type"] == "expense")
    net_savings = total_income - total_expense

    # Monthly savings rate: average over last 3 full calendar months (expanded)
    monthly_rates = []
    for offset in range(1, 4):
        first_of_this = today.replace(day=1)
        target_month = (first_of_this - relativedelta(months=offset))
        _, last_day = monthrange(target_month.year, target_month.month)
        m_from = target_month.replace(day=1).isoformat()
        m_to = target_month.replace(day=last_day).isoformat()

        m_income = sum(r["amount"] for r in expanded if r["type"] == "income" and m_from <= r["date"] <= m_to)
        m_expense = sum(r["amount"] for r in expanded if r["type"] == "expense" and m_from <= r["date"] <= m_to)
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
