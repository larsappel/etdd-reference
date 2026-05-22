"""Overdue feature: identify open loans whose due-date has reached or passed."""

import datetime


def overdue(ledger, *, as_of: datetime.datetime, loan_period: datetime.timedelta) -> list:
    """Return open loans whose due-date is on or before as_of.

    due_date = datetime.fromisoformat(record["borrowed_at"]) + loan_period.
    Comparison is inclusive (due_date <= as_of). Pure read; ledger is not mutated.
    """
    return [
        dict(record)
        for record in ledger.open_loans()
        if datetime.datetime.fromisoformat(record["borrowed_at"]) + loan_period <= as_of
    ]
