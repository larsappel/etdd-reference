"""Return feature: a borrower closes an open loan by returning the book."""

import datetime

from library_loan.borrow import LoanRefused


def return_(ledger, *, book_id: str, borrower_id: str) -> dict:
    """Close the open loan matching (book_id, borrower_id).

    Returns the closed loan record (a dict) with returned_at added.
    Raises LoanRefused("not_on_loan") if no matching open loan exists.
    """
    matching = [
        record
        for record in ledger.open_loans()
        if record["book_id"] == book_id and record["borrower_id"] == borrower_id
    ]

    if not matching:
        raise LoanRefused("not_on_loan", f"No open loan for book '{book_id}' by borrower '{borrower_id}'.")

    record = matching[0]
    ledger._remove(record)
    record["returned_at"] = datetime.datetime.utcnow().isoformat()
    return record
