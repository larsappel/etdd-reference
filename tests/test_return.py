"""
Tests for the `return_` feature of the library-loan tracker.

Public interface assumed:
  from library_loan.return_ import return_
  from library_loan.borrow import LoanRefused

  return_(ledger, *, book_id, borrower_id) -> dict

  - ledger: a mutable object tracking open loans; exposes:
      ledger.open_loans()            -> list of loan records
      ledger.loans_for(borrower_id)  -> list of open loans for that borrower
      ledger.loans_for_book(book_id) -> list of open loans for that book
  - Returns the closed loan record (a dict with at least book_id, borrower_id,
    and returned_at) on success. The closed record is observable to the caller;
    a successful return does not vanish silently.
  - Raises LoanRefused on any refusal, with a `reason` attribute.

Free-dimension choices made by etdd-test-author-return (2026-05-22):

  1. MODULE PATH: `from library_loan.return_ import return_`
     Python reserves the name `return`, so the module and function use a
     trailing underscore. Constraint on the implementation-author: the module
     must live at `library_loan/return_.py` and export a callable named
     `return_`. Alternatively, the implementation-author may re-export from
     a different internal location, but the import line above must resolve.

  2. LOANREFUSED IMPORT PATH: `from library_loan.borrow import LoanRefused`
     LoanRefused is the same class established by the borrow feature. The
     canonical location is `library_loan.borrow`. Constraint on the
     implementation-author: the class must be importable from that path and
     must be the same class raised by return_ (isinstance checks pass).

  3. SUCCESS-OUTPUT-SHAPE: The closed loan record (a dict).
     return_ returns the dict that was the open loan record, augmented with a
     `returned_at` timestamp field. Minimum required keys: book_id, borrower_id.
     The returned_at key is required; its value is an ISO-format timestamp
     string. This choice makes a successful return distinguishable from a refusal
     (exception) and from a no-op (no return value or None would be ambiguous
     across call sites).

  4. CALL-SIGNATURE-SHAPE: `return_(ledger, *, book_id, borrower_id)`
     Catalog and registry are not needed: the outcome forbids returning a book
     that was never lent, and that guard is ledger-checkable without catalog
     lookup. Keyword-only arguments for book_id and borrower_id mirror the
     borrow signature style.

  5. REFUSAL REASON STRING(S): `not_on_loan` (single ground)
     Double-return is collapsed into this same ground (whether-double-return-
     collapses-to-not-on-loan is a declared free dimension; collapsing is the
     simpler defensible choice). The string `not_on_loan` is distinct from the
     four borrow grounds: book_on_loan, limit_reached, unknown_book,
     unknown_borrower.

  6. LEDGER SETUP: _add injection (not borrow() calls)
     Tests pre-populate the ledger via SimpleLedger._add() to decouple return
     tests from the borrow feature. The borrow tests already verify borrow;
     injecting a synthetic open loan record lets return_ tests stand on their
     own. The borrow() path is used only in tests that explicitly exercise the
     borrow/return integration (borrowable-again, loan-limit regain).
"""

import pytest
from library_loan.return_ import return_
from library_loan.borrow import borrow, LoanRefused


# ---------------------------------------------------------------------------
# Helpers — minimal inline fixtures (no pytest fixtures; sparse is better)
# ---------------------------------------------------------------------------

def _catalog(*book_ids):
    return set(book_ids)

def _registry(*borrower_ids):
    return set(borrower_ids)

class SimpleLedger:
    """Minimal in-memory ledger used only in tests."""
    def __init__(self):
        self._loans = []

    def open_loans(self):
        return list(self._loans)

    def loans_for(self, borrower_id):
        return [l for l in self._loans if l["borrower_id"] == borrower_id]

    def loans_for_book(self, book_id):
        return [l for l in self._loans if l["book_id"] == book_id]

    def _add(self, record):
        """Direct injection for test setup. Tests must not call this outside setup."""
        self._loans.append(record)

    def _remove(self, record):
        """Called by return_ to close a loan. Implementation will use this."""
        self._loans.remove(record)


# ---------------------------------------------------------------------------
# Successful return — observable closure
# ---------------------------------------------------------------------------

def test_successful_return_closes_loan_in_ledger():
    """OUTCOME: 'After a successful return, the book is no longer on loan to
    that borrower, the borrower's open-loan tally has decreased by one, and
    the closed loan no longer appears among the open loans the ledger reports.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B1", "borrower_id": "P1", "borrowed_at": "2026-05-01T10:00:00"})

    return_(ledger, book_id="B1", borrower_id="P1")

    assert ledger.loans_for_book("B1") == []
    assert ledger.loans_for("P1") == []
    assert ledger.open_loans() == []


def test_successful_return_returns_observable_closed_record():
    """OUTCOME: 'The caller of return observes that the return happened — the
    call does not vanish silently. The exact shape of what the caller observes
    ... is a free dimension; what is constrained is that a successful return is
    distinguishable from a no-op and from a refusal.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B2", "borrower_id": "P2", "borrowed_at": "2026-05-01T10:00:00"})

    result = return_(ledger, book_id="B2", borrower_id="P2")

    assert result is not None
    assert result["book_id"] == "B2"
    assert result["borrower_id"] == "P2"
    assert "returned_at" in result


def test_successful_return_only_closes_matching_loan():
    """OUTCOME: 'A borrower with multiple open loans returning one book closes
    only that one loan; the borrower's other open loans are unaffected.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B3", "borrower_id": "P3", "borrowed_at": "2026-05-01T10:00:00"})
    ledger._add({"book_id": "B4", "borrower_id": "P3", "borrowed_at": "2026-05-01T10:00:00"})

    return_(ledger, book_id="B3", borrower_id="P3")

    assert ledger.loans_for_book("B3") == []
    loans_remaining = ledger.loans_for("P3")
    assert len(loans_remaining) == 1
    assert loans_remaining[0]["book_id"] == "B4"


# ---------------------------------------------------------------------------
# Named edge case: book not currently on loan
# ---------------------------------------------------------------------------

def test_book_not_on_loan_is_refused():
    """OUTCOME: 'A book that has no open loan against this borrower cannot be
    returned by this borrower. The attempt is refused. The refusal is an error,
    not a silent success.'"""
    ledger = SimpleLedger()

    with pytest.raises(LoanRefused) as exc_info:
        return_(ledger, book_id="NEVER_BORROWED", borrower_id="P4")
    assert exc_info.value.reason == "not_on_loan"


def test_book_not_on_loan_refusal_leaves_no_trace():
    """OUTCOME: 'The ledger is unaffected. Refusals leave no trace — a refused
    return does not mutate the ledger. No "denied return" entry is created.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B5", "borrower_id": "P5", "borrowed_at": "2026-05-01T10:00:00"})
    snapshot_before = [dict(r) for r in ledger.open_loans()]

    try:
        return_(ledger, book_id="NEVER_BORROWED", borrower_id="P5")
    except LoanRefused:
        pass

    assert ledger.open_loans() == snapshot_before


# ---------------------------------------------------------------------------
# Named edge case: double-return (collapsed to not_on_loan)
# ---------------------------------------------------------------------------

def test_double_return_is_refused():
    """OUTCOME: 'A borrower attempting to return the same book a second time,
    after a successful return has already closed the loan, is refused on the
    same ground as "book not currently on loan." The first return closed the
    loan; the second return finds no open loan to close.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B6", "borrower_id": "P6", "borrowed_at": "2026-05-01T10:00:00"})

    return_(ledger, book_id="B6", borrower_id="P6")

    with pytest.raises(LoanRefused) as exc_info:
        return_(ledger, book_id="B6", borrower_id="P6")
    assert exc_info.value.reason == "not_on_loan"


def test_double_return_does_not_mutate_ledger():
    """OUTCOME: 'The ledger is unaffected by the second attempt — neither the
    closed loan from the first call nor any other record changes.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B7", "borrower_id": "P7", "borrowed_at": "2026-05-01T10:00:00"})
    ledger._add({"book_id": "B8", "borrower_id": "P7", "borrowed_at": "2026-05-01T10:00:00"})

    return_(ledger, book_id="B7", borrower_id="P7")
    snapshot_after_first = [dict(r) for r in ledger.open_loans()]

    try:
        return_(ledger, book_id="B7", borrower_id="P7")
    except LoanRefused:
        pass

    assert ledger.open_loans() == snapshot_after_first


# ---------------------------------------------------------------------------
# Named edge case: return keyed on (borrower, book) pair
# ---------------------------------------------------------------------------

def test_wrong_borrower_cannot_return_book():
    """OUTCOME: 'A book on loan to borrower A cannot be returned by borrower B —
    the (borrower, book) pair must identify a currently-open loan. Whether
    borrower B's attempt is refused as "book not currently on loan to this
    borrower" ... is a free dimension; what is constrained is that B's attempt
    does not close A's loan and does not succeed.'"""
    ledger = SimpleLedger()
    ledger._add({"book_id": "B9", "borrower_id": "PA", "borrowed_at": "2026-05-01T10:00:00"})

    with pytest.raises(LoanRefused) as exc_info:
        return_(ledger, book_id="B9", borrower_id="PB")
    assert exc_info.value.reason == "not_on_loan"

    # A's loan is unaffected
    loans = ledger.loans_for_book("B9")
    assert len(loans) == 1
    assert loans[0]["borrower_id"] == "PA"


# ---------------------------------------------------------------------------
# Named edge case: returning past due-date reduces to normal return
# ---------------------------------------------------------------------------

def test_past_due_date_return_succeeds_normally():
    """OUTCOME: 'The "past due-date" edge therefore reduces to "a normal return":
    the loan is closed in the usual way and no overdue flag appears in the
    output, because no due-date exists to compare against.'"""
    ledger = SimpleLedger()
    # The borrow outcome specifies borrowed_at only; no due_date field on record.
    ledger._add({"book_id": "B10", "borrower_id": "P10", "borrowed_at": "2025-01-01T10:00:00"})

    result = return_(ledger, book_id="B10", borrower_id="P10")

    assert result is not None
    assert "overdue" not in result
    assert ledger.loans_for_book("B10") == []


# ---------------------------------------------------------------------------
# Additional edge: returned book becomes borrowable again
# ---------------------------------------------------------------------------

def test_returned_book_is_borrowable_again():
    """OUTCOME: 'After a successful return, the book is once again eligible to
    be borrowed — by the same borrower or by a different one — through the
    normal borrow path.'"""
    catalog = _catalog("B11")
    registry = _registry("P11", "P12")
    ledger = SimpleLedger()

    # Set up an open loan via injection, return it, then borrow again.
    ledger._add({"book_id": "B11", "borrower_id": "P11", "borrowed_at": "2026-05-01T10:00:00"})
    return_(ledger, book_id="B11", borrower_id="P11")

    new_loan = borrow(catalog, registry, ledger, book_id="B11", borrower_id="P12")

    assert new_loan is not None
    assert new_loan["book_id"] == "B11"
    assert new_loan["borrower_id"] == "P12"
    assert len(ledger.loans_for_book("B11")) == 1


# ---------------------------------------------------------------------------
# Additional edge: borrower at limit regains room after return
# ---------------------------------------------------------------------------

def test_borrower_at_limit_regains_room_after_return():
    """OUTCOME: 'The borrower's open-loan count has decreased by one, so a
    borrower who was at their loan limit before the return now has room for
    one more loan. The loan-limit value itself remains a free dimension.'"""
    # Fill the borrower's quota without pinning the limit value.
    books = [f"LIM-{i}" for i in range(20)]
    catalog = _catalog(*books)
    registry = _registry("HEAVY2")
    ledger = SimpleLedger()

    last_borrowed = None
    for book in books:
        try:
            last_borrowed = borrow(catalog, registry, ledger, book_id=book, borrower_id="HEAVY2")
        except LoanRefused as e:
            assert e.reason == "limit_reached"
            break
    else:
        pytest.fail("Expected limit_reached refusal but no refusal occurred")

    assert last_borrowed is not None, "Must have borrowed at least one book before hitting the limit"

    # Return the last successfully borrowed book.
    return_(ledger, book_id=last_borrowed["book_id"], borrower_id="HEAVY2")

    # Now exactly one more borrow must succeed on a book not yet borrowed.
    remaining_books = [b for b in books if b != last_borrowed["book_id"]
                       and not ledger.loans_for_book(b)]
    assert remaining_books, "Need at least one un-borrowed book to verify regained room"

    new_loan = borrow(catalog, registry, ledger, book_id=remaining_books[0], borrower_id="HEAVY2")
    assert new_loan is not None
    assert new_loan["borrower_id"] == "HEAVY2"
