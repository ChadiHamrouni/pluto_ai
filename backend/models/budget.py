"""Pydantic models for budget tool inputs and outputs."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TransactionType = Literal["income", "expense"]
RecurringType = Literal["", "monthly", "weekly", "yearly"]

VALID_CATEGORIES = {
    "salary", "freelance", "food", "transport", "rent", "utilities",
    "subscriptions", "entertainment", "health", "education", "savings", "other",
}


class TransactionCreate(BaseModel):
    tx_type: TransactionType
    amount: float = Field(..., gt=0)
    category: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=300)
    date: str = Field(default="", description="ISO-8601 date, defaults to today")
    recurring: RecurringType = ""
    recurring_day: Optional[int] = Field(default=None, ge=1, le=31)

    @field_validator("category", mode="before")
    @classmethod
    def normalise_category(cls, v: str) -> str:
        v = v.strip().lower()
        return v if v in VALID_CATEGORIES else "other"


class TransactionOut(BaseModel):
    id: int
    type: TransactionType
    amount: float
    category: str
    description: str
    date: str
    recurring: str
    recurring_day: Optional[int]
    created_at: str

    @classmethod
    def from_row(cls, row: dict) -> "TransactionOut":
        return cls(
            id=row["id"],
            type=row["type"],
            amount=row["amount"],
            category=row["category"],
            description=row.get("description", ""),
            date=row["date"],
            recurring=row.get("recurring", ""),
            recurring_day=row.get("recurring_day"),
            created_at=row.get("created_at", ""),
        )


class SavingsGoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_amount: float = Field(..., gt=0)
    deadline: Optional[str] = Field(default=None, description="ISO-8601 date e.g. 2026-12-31")

    @field_validator("deadline", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v


class SavingsGoalOut(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    deadline: Optional[str]
    created_at: str
    percent_complete: float = 0.0
    avg_monthly_savings: float = 0.0
    projected_completion_date: str = "Unknown"
    months_remaining: Optional[float] = None

    @classmethod
    def from_row(cls, row: dict) -> "SavingsGoalOut":
        return cls(
            id=row["id"],
            name=row["name"],
            target_amount=row["target_amount"],
            current_amount=row.get("current_amount", 0.0),
            deadline=row.get("deadline"),
            created_at=row.get("created_at", ""),
            percent_complete=row.get("percent_complete", 0.0),
            avg_monthly_savings=row.get("avg_monthly_savings", 0.0),
            projected_completion_date=row.get("projected_completion_date", "Unknown"),
            months_remaining=row.get("months_remaining"),
        )


class BudgetSummaryOut(BaseModel):
    period: str
    total_income: float
    total_expenses: float
    net: float
    by_category: list[dict]
    savings_goals: list[SavingsGoalOut] = Field(default_factory=list)
