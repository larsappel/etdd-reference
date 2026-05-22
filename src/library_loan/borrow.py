"""Borrow feature: a registered borrower takes out a book from the catalog."""

import datetime

LOAN_LIMIT = 3


class LoanRefused(Exception):
    """Raised when a borrow attempt cannot be fulfilled.

    Attributes:
        reason: one of 'book_on_loan', 'limit_reached',
                'unknown_book', 'unknown_borrower'.
    """

    def __init__(self, reason: str, message: str = ""):
        self.reason = reason
        super().__init__(message or reason)


def borrow(catalog, registry, ledger, *, book_id: str, borrower_id: str) -> dict:
    """Attempt to loan book_id to borrower_id.

    Returns a loan record dict on success.
    Raises LoanRefused on any refusal ground; the ledger is not mutated.
    """
    if book_id not in catalog:
        raise LoanRefused("unknown_book", f"Book '{book_id}' is not in the catalog.")

    if borrower_id not in registry:
        raise LoanRefused("unknown_borrower", f"Borrower '{borrower_id}' is not registered.")

    if ledger.loans_for_book(book_id):
        raise LoanRefused("book_on_loan", f"Book '{book_id}' is already on loan.")

    if len(ledger.loans_for(borrower_id)) >= LOAN_LIMIT:
        raise LoanRefused("limit_reached", f"Borrower '{borrower_id}' has reached the loan limit.")

    record = {
        "book_id": book_id,
        "borrower_id": borrower_id,
        "borrowed_at": datetime.datetime.utcnow().isoformat(),
    }
    ledger._add(record)
    return record
