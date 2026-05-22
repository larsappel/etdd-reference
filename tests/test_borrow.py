"""
Tests for the `borrow` feature of the library-loan tracker.

Public interface assumed:
  from library_loan.borrow import borrow, LoanRefused

  borrow(catalog, registry, ledger, book_id, borrower_id) -> loan_record

  - catalog: a set (or collection) of book identifiers the system recognises.
  - registry: a set (or collection) of borrower identifiers the system recognises.
  - ledger: a mutable object tracking open loans; exposes:
      ledger.open_loans()           -> list of loan records
      ledger.loans_for(borrower_id) -> list of open loans for that borrower
      ledger.loans_for_book(book_id)-> list of open loans for that book
  - Returns a loan_record on success (observable, non-None, identifying
    borrower + book).
  - Raises LoanRefused on any refusal, with a `reason` attribute that
    distinguishes the four grounds: 'book_on_loan', 'limit_reached',
    'unknown_book', 'unknown_borrower'.

Justification for programmatic API:
  CLI-flag spelling is a declared free dimension; the function is the
  load-bearing contract. CLI wiring is not tested here.

Loan limit:
  The numeric limit is a free dimension. Tests provoke "at limit" by
  filling the ledger up to whatever limit the implementation enforces,
  then attempting one more — rather than hard-coding a count.
"""

import pytest
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
        """Used only by the implementation; tests must not call this."""
        self._loans.append(record)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_successful_borrow_returns_observable_loan_record():
    """OUTCOME: 'When the borrow is permitted, a new loan record comes into
    being that identifies the borrower, the book, and the moment the loan was
    opened. The record is observable to the caller of borrow — a successful
    borrow does not vanish silently.'"""
    catalog = _catalog("B1")
    registry = _registry("P1")
    ledger = SimpleLedger()

    record = borrow(catalog, registry, ledger, book_id="B1", borrower_id="P1")

    assert record is not None
    assert record["book_id"] == "B1"
    assert record["borrower_id"] == "P1"


def test_successful_borrow_book_appears_on_loan():
    """OUTCOME: 'After a successful borrow, the book is on loan to that
    borrower and counts against the borrower's open-loan tally; before that
    point, neither was true.'"""
    catalog = _catalog("B2")
    registry = _registry("P2")
    ledger = SimpleLedger()

    assert ledger.loans_for_book("B2") == []
    borrow(catalog, registry, ledger, book_id="B2", borrower_id="P2")
    assert len(ledger.loans_for_book("B2")) == 1


# ---------------------------------------------------------------------------
# Named edge case: book already on loan
# ---------------------------------------------------------------------------

def test_book_already_on_loan_is_refused():
    """OUTCOME: 'Book already on loan — A book that is currently checked out
    to any borrower cannot be borrowed again. The attempt is refused.'"""
    catalog = _catalog("B3")
    registry = _registry("P3", "P4")
    ledger = SimpleLedger()

    borrow(catalog, registry, ledger, book_id="B3", borrower_id="P3")

    with pytest.raises(LoanRefused) as exc_info:
        borrow(catalog, registry, ledger, book_id="B3", borrower_id="P4")
    assert exc_info.value.reason == "book_on_loan"


def test_book_already_on_loan_original_loan_unaffected():
    """OUTCOME: 'The existing loan is unaffected — the original borrower still
    holds the book, the book's on-loan state does not change, and no second
    loan record comes into being.'"""
    catalog = _catalog("B4")
    registry = _registry("P5", "P6")
    ledger = SimpleLedger()

    borrow(catalog, registry, ledger, book_id="B4", borrower_id="P5")
    try:
        borrow(catalog, registry, ledger, book_id="B4", borrower_id="P6")
    except LoanRefused:
        pass

    loans = ledger.loans_for_book("B4")
    assert len(loans) == 1
    assert loans[0]["borrower_id"] == "P5"


# ---------------------------------------------------------------------------
# Named edge case: borrower already at their loan limit
# ---------------------------------------------------------------------------

def test_borrower_at_limit_cannot_borrow_further():
    """OUTCOME: 'Borrower already at their loan limit — A borrower who is
    already holding that maximum cannot take out a further book. The attempt
    is refused.'"""
    # Fill up the borrower's quota — we don't know the numeric limit, so we
    # borrow books until refused, then assert the ground is 'limit_reached'.
    books = [f"LIM-{i}" for i in range(20)]  # more than any reasonable limit
    catalog = _catalog(*books)
    registry = _registry("HEAVY")
    ledger = SimpleLedger()

    limit_hit = False
    for book in books:
        try:
            borrow(catalog, registry, ledger, book_id=book, borrower_id="HEAVY")
        except LoanRefused as e:
            assert e.reason == "limit_reached"
            limit_hit = True
            break

    assert limit_hit, "Expected limit_reached refusal but no refusal occurred"


# ---------------------------------------------------------------------------
# Named edge case: book not in the catalog
# ---------------------------------------------------------------------------

def test_unknown_book_is_refused():
    """OUTCOME: 'Book not in the catalog — A book identifier that the catalog
    does not recognise cannot be borrowed. The attempt is refused.'"""
    catalog = _catalog("REAL")
    registry = _registry("P8")
    ledger = SimpleLedger()

    with pytest.raises(LoanRefused) as exc_info:
        borrow(catalog, registry, ledger, book_id="GHOST", borrower_id="P8")
    assert exc_info.value.reason == "unknown_book"


def test_unknown_book_refusal_does_not_register_book():
    """OUTCOME: 'The catalog is unaffected — the refusal does not implicitly
    register the book, and a follow-up borrow on the same identifier is
    refused on the same ground.'"""
    catalog = _catalog()
    registry = _registry("P9")
    ledger = SimpleLedger()

    for _ in range(2):
        with pytest.raises(LoanRefused) as exc_info:
            borrow(catalog, registry, ledger, book_id="GHOST2", borrower_id="P9")
        assert exc_info.value.reason == "unknown_book"


# ---------------------------------------------------------------------------
# Named edge case: borrower not registered
# ---------------------------------------------------------------------------

def test_unknown_borrower_is_refused():
    """OUTCOME: 'Borrower not registered — A borrower identifier that the
    registry does not recognise cannot borrow. The attempt is refused.'"""
    catalog = _catalog("B6")
    registry = _registry()
    ledger = SimpleLedger()

    with pytest.raises(LoanRefused) as exc_info:
        borrow(catalog, registry, ledger, book_id="B6", borrower_id="UNKNOWN")
    assert exc_info.value.reason == "unknown_borrower"


def test_unknown_borrower_refusal_does_not_register_borrower():
    """OUTCOME: 'The registry is unaffected — the refusal does not implicitly
    register the borrower, and a follow-up borrow for the same identifier is
    refused on the same ground.'"""
    catalog = _catalog("B7")
    registry = _registry()
    ledger = SimpleLedger()

    for _ in range(2):
        with pytest.raises(LoanRefused) as exc_info:
            borrow(catalog, registry, ledger, book_id="B7", borrower_id="UNKNOWN2")
        assert exc_info.value.reason == "unknown_borrower"


# ---------------------------------------------------------------------------
# Additional edge cases: refusals leave no trace
# ---------------------------------------------------------------------------

def test_refusal_leaves_no_loan_record():
    """OUTCOME: 'Refusals leave no trace in the loan history — a refused borrow
    does not create a loan record, does not create a "denied" entry, and does
    not advance any counter that an eligible later attempt would observe.'"""
    catalog = _catalog("B8")
    registry = _registry("P10")
    ledger = SimpleLedger()

    # Refuse via unknown borrower, then unknown book
    try:
        borrow(catalog, registry, ledger, book_id="B8", borrower_id="GHOST_P")
    except LoanRefused:
        pass
    try:
        borrow(catalog, registry, ledger, book_id="GHOST_B", borrower_id="P10")
    except LoanRefused:
        pass

    assert ledger.open_loans() == []


# ---------------------------------------------------------------------------
# Additional edge cases: refusals are distinguishable
# ---------------------------------------------------------------------------

def test_four_refusal_grounds_are_distinguishable():
    """OUTCOME: 'Refusals are distinguishable — A caller can tell which of
    the four refusal grounds applied. The grounds are not collapsed into a
    single opaque refusal.'"""
    catalog = _catalog("B9")
    registry = _registry("P11", "P12")
    ledger = SimpleLedger()

    borrow(catalog, registry, ledger, book_id="B9", borrower_id="P11")

    reasons = set()

    # ground 1: book on loan
    with pytest.raises(LoanRefused) as e:
        borrow(catalog, registry, ledger, book_id="B9", borrower_id="P12")
    reasons.add(e.value.reason)

    # ground 2: unknown book
    with pytest.raises(LoanRefused) as e:
        borrow(catalog, registry, ledger, book_id="NO_BOOK", borrower_id="P11")
    reasons.add(e.value.reason)

    # ground 3: unknown borrower
    with pytest.raises(LoanRefused) as e:
        borrow(catalog, registry, ledger, book_id="B9", borrower_id="NO_P")
    reasons.add(e.value.reason)

    # ground 4: limit_reached (provoke via dedicated test path)
    books_for_limit = [f"DIS-{i}" for i in range(20)]
    catalog2 = _catalog(*books_for_limit)
    registry2 = _registry("P13")
    ledger2 = SimpleLedger()
    for b in books_for_limit:
        try:
            borrow(catalog2, registry2, ledger2, book_id=b, borrower_id="P13")
        except LoanRefused as exc:
            reasons.add(exc.reason)
            break

    assert reasons == {"book_on_loan", "unknown_book", "unknown_borrower", "limit_reached"}


# ---------------------------------------------------------------------------
# Additional edge cases: borrow is the open half; return can close it
# ---------------------------------------------------------------------------

def test_successful_borrow_loan_record_is_closeable_by_return():
    """OUTCOME: 'borrow is the open half of a loan; return is the close half.
    A successful borrow puts a book into the state from which a future return
    is the only legitimate exit. The loan record borrow produces is the same
    record return consumes.'"""
    catalog = _catalog("B10")
    registry = _registry("P14")
    ledger = SimpleLedger()

    record = borrow(catalog, registry, ledger, book_id="B10", borrower_id="P14")

    # The record must carry enough identity that a return operation can
    # reference it without ambiguity: borrower and book are present.
    assert "book_id" in record
    assert "borrower_id" in record
    # The record is in the ledger
    assert any(
        l["book_id"] == "B10" and l["borrower_id"] == "P14"
        for l in ledger.open_loans()
    )
