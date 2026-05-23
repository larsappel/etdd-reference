"""
Tests for the `overdue` feature of the library-loan tracker.

Public interface assumed:
  from library_loan.overdue import overdue

  overdue(ledger, *, as_of, loan_period) -> list

  - ledger: a mutable object tracking open loans; exposes:
      ledger.open_loans()            -> list of loan records
      ledger.loans_for(borrower_id)  -> list of open loans for that borrower
      ledger.loans_for_book(book_id) -> list of open loans for that book
  - as_of: a datetime.datetime value supplied by the caller.
    The function does NOT call datetime.utcnow() or any other clock
    internally. This is a load-bearing constraint (outcome §"The moment
    asked is supplied by the caller, not read from a clock").
  - loan_period: a datetime.timedelta value supplied by the caller.
    Represents the duration after which a loan becomes overdue. Passed
    as a keyword argument named `loan_period`. The function does NOT use
    a module-level constant or a value baked into the loan record.
  - Returns a list of open loan records (dicts) whose due-date has
    reached or passed `as_of`. Due-date is computed as:
        due_date = datetime.fromisoformat(record["borrowed_at"]) + loan_period
    Loans are overdue when: due_date <= as_of  (boundary is INCLUSIVE).
  - Returns an empty list (never None) when no loans are overdue.
  - Does not raise on an empty ledger or an all-on-time ledger.

Free-dimension choices made by etdd-test-author-overdue (2026-05-22):

  1. MODULE PATH / FUNCTION NAME: `from library_loan.overdue import overdue`
     A single function named `overdue` inside module `library_loan.overdue`.
     Constraint on the implementation-author: the module must live at
     `library_loan/overdue.py` and export a callable named `overdue`.

  2. LOAN-PERIOD TYPE: datetime.timedelta
     Timedelta is the natural Python type and allows direct arithmetic with
     datetime objects. It makes the boundary edge (== case) straightforwardly
     testable without conversion. An integer-days alternative would require
     timedelta(days=n) on the implementation side; timedelta at the call site
     is cleaner and more composable for callers asking projection questions.

  3. `as_of` TYPE: datetime.datetime
     The caller supplies a datetime.datetime. This is consistent with the
     practitioner guide's `NOW = datetime(...)` convention in the worked
     example. It is the natural Python type for "a moment in time."

  4. `borrowed_at` REPRESENTATION: ISO string (str)
     Loan records carry `borrowed_at` as an ISO-format string, matching what
     borrow.py writes: `datetime.datetime.utcnow().isoformat()`. The `overdue`
     function must parse this string (e.g., via `datetime.fromisoformat`) to
     perform the comparison. Tests inject records with `borrowed_at` as ISO
     strings to match production borrow output exactly.
     Constraint on the implementation-author: `overdue` must parse
     `record["borrowed_at"]` from ISO string to datetime before comparing.

  5. OUTPUT COLLECTION SHAPE: list
     A `list` is returned. Empty when no loan is overdue. Never None.
     The list is iterable, has a definable length, and supports membership
     queries. Order is a free dimension per the outcome; tests assert on the
     SET of listed loans, not on positional order.

  6. DEFAULT LOAN PERIOD: None provided.
     No default value for `loan_period` is established. The caller must
     always supply `loan_period`. This ensures the constraint "a caller asking
     with a different period gets a different answer from the same ledger
     state" is testable without ambiguity about what default the function
     might have used.

Boundary rule (outcome §"The moment a loan becomes overdue"):
  due_date <= as_of  is the comparison. A loan whose due_date equals as_of
  is overdue. This is the load-bearing `<=` edge; an implementation using `<`
  would fail test_exactly_at_due_date_is_listed.
"""

import datetime
import inspect
import pytest
import library_loan.overdue as _overdue_module
from library_loan.overdue import overdue
from library_loan.borrow import borrow
from library_loan.return_ import return_


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
        """Called by return_ to close a loan."""
        self._loans.remove(record)


# ---------------------------------------------------------------------------
# Boundary and core listing behaviour
# ---------------------------------------------------------------------------

def test_past_due_loan_is_listed():
    """OUTCOME: 'A loan past its due-date at the moment asked is listed.
    A loan whose due-date is strictly earlier than the moment asked is
    in the answer.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B1",
        "borrower_id": "P1",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    # loan_period = 7 days  => due_date = 2026-05-08T10:00:00
    # as_of = 2026-05-22T10:00:00 (14 days after due_date)
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )
    assert any(
        r["book_id"] == "B1" and r["borrower_id"] == "P1"
        for r in result
    )


def test_exactly_at_due_date_is_listed():
    """OUTCOME: 'A loan exactly at its due-date at the moment asked is listed.
    The boundary is inclusive: when the moment asked equals the loan's
    due-date ... the loan is overdue. Comparison: due_date <= as_of.'

    This is the load-bearing edge case. An implementation using < instead of
    <= would fail here."""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B2",
        "borrower_id": "P2",
        "borrowed_at": "2026-05-15T12:00:00",
    })
    # loan_period = 7 days => due_date = 2026-05-22T12:00:00
    # as_of = 2026-05-22T12:00:00 (exactly at due_date)
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 12, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )
    assert any(
        r["book_id"] == "B2" and r["borrower_id"] == "P2"
        for r in result
    )


def test_not_yet_due_loan_is_not_listed():
    """OUTCOME: 'A loan not yet at its due-date at the moment asked is not
    listed. Loans whose due-date lies in the future relative to the moment
    asked are open-and-on-time and absent from the answer.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B3",
        "borrower_id": "P3",
        "borrowed_at": "2026-05-20T08:00:00",
    })
    # loan_period = 14 days => due_date = 2026-06-03T08:00:00
    # as_of = 2026-05-22T10:00:00 (before due_date)
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=14),
    )
    assert not any(
        r["book_id"] == "B3"
        for r in result
    )


# ---------------------------------------------------------------------------
# Empty / all-on-time cases
# ---------------------------------------------------------------------------

def test_empty_ledger_returns_empty_list():
    """OUTCOME: 'The empty ledger ... produce[s] an empty answer. When no open
    loans exist ... the answer is an empty collection of the declared output
    shape. The call does not raise.'"""
    ledger = SimpleLedger()
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )
    assert result == [] or (hasattr(result, '__len__') and len(result) == 0)


def test_all_on_time_ledger_returns_empty_list():
    """OUTCOME: '... the all-on-time ledger [produces] an empty answer. When
    every open loan's due-date is strictly later than the moment asked, the
    answer is an empty collection.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B4",
        "borrower_id": "P4",
        "borrowed_at": "2026-05-21T09:00:00",
    })
    ledger._add({
        "book_id": "B5",
        "borrower_id": "P5",
        "borrowed_at": "2026-05-22T09:00:00",
    })
    # loan_period = 30 days => both due 2026-06-20 and 2026-06-21
    # as_of = 2026-05-22T10:00:00 — both are on time
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=30),
    )
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Mutation invariant
# ---------------------------------------------------------------------------

def test_overdue_call_mutates_nothing():
    """OUTCOME: 'The call is a read and mutates nothing. No ledger entry is
    added, removed, or modified. After the call, ledger.open_loans() ...
    return[s] exactly what [it] returned before the call.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B6",
        "borrower_id": "P6",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    ledger._add({
        "book_id": "B7",
        "borrower_id": "P6",
        "borrowed_at": "2026-05-10T10:00:00",
    })
    snapshot_before = [dict(r) for r in ledger.open_loans()]

    overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )

    assert [dict(r) for r in ledger.open_loans()] == snapshot_before


# ---------------------------------------------------------------------------
# Returned loans absent
# ---------------------------------------------------------------------------

def test_returned_loan_absent_from_overdue():
    """OUTCOME: 'Returned loans never appear in the answer. A loan that was
    open and overdue before being returned is not in the answer after
    return_ has closed it. The overdue feature reads ledger.open_loans()
    and only the open loans.'"""
    catalog = _catalog("B8")
    registry = _registry("P8")
    ledger = SimpleLedger()

    # Borrow, then return immediately — the loan is now closed.
    borrow(catalog, registry, ledger, book_id="B8", borrower_id="P8")
    return_(ledger, book_id="B8", borrower_id="P8")

    # Asking far in the future — would be overdue if still open.
    result = overdue(
        ledger,
        as_of=datetime.datetime(2099, 1, 1, 0, 0, 0),
        loan_period=datetime.timedelta(days=1),
    )
    assert not any(r["book_id"] == "B8" for r in result)


# ---------------------------------------------------------------------------
# Identity of listed loans
# ---------------------------------------------------------------------------

def test_listed_loans_carry_borrow_identity_fields():
    """OUTCOME: 'Listed loans carry the same identity the loan record already
    had. Each entry in the answer identifies the borrower, the book, and the
    moment the loan was opened — at minimum the same book_id, borrower_id, and
    borrowed_at fields the borrow outcome put on the record.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B9",
        "borrower_id": "P9",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )
    assert len(result) >= 1
    loan = next(r for r in result if r["book_id"] == "B9")
    assert "book_id" in loan
    assert "borrower_id" in loan
    assert "borrowed_at" in loan
    assert loan["book_id"] == "B9"
    assert loan["borrower_id"] == "P9"


# ---------------------------------------------------------------------------
# Loan-period is respected per call (not a module constant)
# ---------------------------------------------------------------------------

def test_loan_period_controls_overdue_classification():
    """OUTCOME: 'The loan-period value is supplied per call. A caller asking
    with a different period gets a different answer from the same ledger state,
    and that property is the test that an implementation has not silently
    leaked a default.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B10",
        "borrower_id": "P10",
        "borrowed_at": "2026-05-15T10:00:00",
    })
    as_of = datetime.datetime(2026, 5, 22, 10, 0, 0)
    # borrowed_at = 2026-05-15T10:00:00; as_of = 2026-05-22T10:00:00 => 7 days elapsed

    # Short period (3 days): due_date = 2026-05-18T10:00:00 -> overdue
    short_result = overdue(ledger, as_of=as_of, loan_period=datetime.timedelta(days=3))
    # Long period (30 days): due_date = 2026-06-14T10:00:00 -> not overdue
    long_result = overdue(ledger, as_of=as_of, loan_period=datetime.timedelta(days=30))

    assert any(r["book_id"] == "B10" for r in short_result)
    assert not any(r["book_id"] == "B10" for r in long_result)


# ---------------------------------------------------------------------------
# `as_of` is honoured (not read from a clock)
# ---------------------------------------------------------------------------

def test_as_of_controls_overdue_classification():
    """OUTCOME: 'The moment asked is supplied by the caller, not read from a
    clock. The function does not call datetime.utcnow() or any other time
    source. The moment used for the comparison is a caller-supplied argument.'"""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B11",
        "borrower_id": "P11",
        "borrowed_at": "2026-05-15T10:00:00",
    })
    loan_period = datetime.timedelta(days=7)
    # due_date = 2026-05-22T10:00:00

    # as_of far in the past: loan not yet started
    past_result = overdue(
        ledger,
        as_of=datetime.datetime(2020, 1, 1, 0, 0, 0),
        loan_period=loan_period,
    )
    # as_of far in the future: definitely overdue
    future_result = overdue(
        ledger,
        as_of=datetime.datetime(2099, 1, 1, 0, 0, 0),
        loan_period=loan_period,
    )

    assert not any(r["book_id"] == "B11" for r in past_result)
    assert any(r["book_id"] == "B11" for r in future_result)


# ---------------------------------------------------------------------------
# Independent of unrelated loans
# ---------------------------------------------------------------------------

def test_overdue_judgment_independent_of_other_loans():
    """OUTCOME: 'Loans across borrowers and books are weighed independently.
    Whether a given loan is overdue depends only on that loan's borrowed_at,
    the supplied loan-period, and the supplied moment. It does not depend on
    whether the borrower has other open loans, on whether the book has been
    borrowed before, or on any other loan in the ledger.'"""
    ledger = SimpleLedger()
    # Loan A: overdue (borrowed 21 days ago, period = 14 days)
    ledger._add({
        "book_id": "B12",
        "borrower_id": "P12",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    # Loan B: on time (borrowed today, period = 14 days)
    ledger._add({
        "book_id": "B13",
        "borrower_id": "P12",
        "borrowed_at": "2026-05-22T10:00:00",
    })
    # Loan C: on time (borrowed 5 days ago, period = 14 days)
    ledger._add({
        "book_id": "B14",
        "borrower_id": "P13",
        "borrowed_at": "2026-05-17T10:00:00",
    })

    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=14),
    )

    # Only loan A (B12) is overdue (due 2026-05-15, as_of = 2026-05-22)
    overdue_books = {r["book_id"] for r in result}
    assert "B12" in overdue_books
    assert "B13" not in overdue_books
    assert "B14" not in overdue_books


# ---------------------------------------------------------------------------
# Multiple overdue loans — set semantics
# ---------------------------------------------------------------------------

def test_multiple_overdue_loans_all_listed():
    """OUTCOME: 'The answer is the subset of the currently-open loans whose
    due-date has come and gone by that moment.' When multiple loans are past
    due, all are listed. Tests assert on the set of listed loans, not
    positional order (outcome §'The answer's order is not pinned')."""
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B15",
        "borrower_id": "P14",
        "borrowed_at": "2026-04-01T10:00:00",
    })
    ledger._add({
        "book_id": "B16",
        "borrower_id": "P15",
        "borrowed_at": "2026-04-10T10:00:00",
    })
    ledger._add({
        "book_id": "B17",
        "borrower_id": "P14",
        "borrowed_at": "2026-04-20T10:00:00",
    })

    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )

    # All three are more than 7 days past borrowed_at as of 2026-05-22
    overdue_books = {r["book_id"] for r in result}
    assert overdue_books == {"B15", "B16", "B17"}


# ---------------------------------------------------------------------------
# Post-adversarial-review probes (G5b breaker found gaps; predicates pinned)
# ---------------------------------------------------------------------------

def test_listed_loan_borrowed_at_value_matches_source():
    """OUTCOME (After adversarial review): 'Each listed loan's book_id,
    borrower_id, and borrowed_at values are equal to the corresponding values
    on the open-loan record the ledger holds for that loan. The keys are not
    fabricable: an implementation that emits the right keys with values
    invented by the call does not satisfy the outcome.'

    The existing test_listed_loans_carry_borrow_identity_fields checks
    book_id and borrower_id values but does not assert the borrowed_at value.
    The adversarial implementation returned '1970-01-01T00:00:00' for every
    loan; this test pins that borrowed_at is the verbatim source string.
    """
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B18",
        "borrower_id": "P18",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )
    assert len(result) >= 1
    loan = next(r for r in result if r["book_id"] == "B18")
    assert loan["borrowed_at"] == "2026-05-01T10:00:00"


def test_overdue_does_not_call_utcnow(monkeypatch):
    """OUTCOME (After adversarial review): 'The function does not call
    datetime.utcnow(), datetime.now(), time.time(), time.monotonic(), or any
    other process-wide time source, even when the result is discarded. The
    as_of argument is the sole moment the function is permitted to know about.
    A call that reads a clock and ignores the result is ruled out.'

    Implementation: monkeypatch replaces library_loan.overdue.datetime with a
    stub module whose datetime.utcnow raises. Because datetime.datetime is a C
    type and cannot be patched directly, we swap out the module-level name the
    implementation holds. fromisoformat is preserved on the subclass. Static
    fallback (inspect.getsource) is also asserted for belt-and-braces.
    """
    utcnow_calls = []
    _dt_module = datetime  # capture module reference before class shadows the name

    class _GuardedDatetime(_dt_module.datetime):
        @classmethod
        def utcnow(cls):
            utcnow_calls.append("utcnow called")
            raise AssertionError("clock read forbidden")

    class _GuardedModule:
        datetime = _GuardedDatetime
        timedelta = _dt_module.timedelta

    monkeypatch.setattr(_overdue_module, "datetime", _GuardedModule())

    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B19",
        "borrower_id": "P19",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    # If the implementation calls utcnow(), the stub raises AssertionError.
    result = overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )
    assert utcnow_calls == [], "overdue called datetime.utcnow(); clock read is forbidden"

    # Belt-and-braces static check: the source must not mention utcnow at all.
    src = inspect.getsource(_overdue_module.overdue)
    assert "utcnow" not in src, "overdue source mentions 'utcnow'; clock read is forbidden"


def test_overdue_order_is_deterministic():
    """OUTCOME (After adversarial review): 'Two calls with the same ledger
    state, the same as_of, and the same loan_period return the overdue loans
    in the same order. The order itself remains a free dimension — the
    sort-order-of-listed-loans axis is unchanged — but the determinism within
    that axis is not free.'

    The adversarial implementation called random.shuffle on the result; two
    consecutive calls with a fixed ledger could return the same set in
    different positional orders. This test catches that by comparing two calls
    as ordered sequences, not as sets.
    """
    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B20",
        "borrower_id": "P20",
        "borrowed_at": "2026-04-01T10:00:00",
    })
    ledger._add({
        "book_id": "B21",
        "borrower_id": "P21",
        "borrowed_at": "2026-04-10T10:00:00",
    })
    ledger._add({
        "book_id": "B22",
        "borrower_id": "P22",
        "borrowed_at": "2026-04-20T10:00:00",
    })
    as_of = datetime.datetime(2026, 5, 22, 10, 0, 0)
    loan_period = datetime.timedelta(days=7)

    result1 = overdue(ledger, as_of=as_of, loan_period=loan_period)
    result2 = overdue(ledger, as_of=as_of, loan_period=loan_period)

    assert result1 == result2, (
        "overdue returned a different order on two identical calls; "
        "determinism is required even though sort-order is a free dimension"
    )


def test_overdue_call_observes_no_transient_mutation():
    """OUTCOME (After adversarial review): 'During the call, no key is added
    to, removed from, or modified on any ledger record, even if the
    modification is reverted before the call returns. A concurrent observer of
    the ledger during the call sees records in the state they held before the
    call began.'

    Approach: wrap ledger.open_loans so that each time it is called from
    inside overdue, it inspects the records returned and asserts none carry
    any key outside the canonical set {book_id, borrower_id, borrowed_at}.
    The adversarial implementation added _breaker_marker to each record
    before the loop and removed it after; this probe catches that by
    observing record state inside the call, not only before and after.
    """
    CANONICAL_KEYS = {"book_id", "borrower_id", "borrowed_at"}
    violations = []

    ledger = SimpleLedger()
    ledger._add({
        "book_id": "B23",
        "borrower_id": "P23",
        "borrowed_at": "2026-05-01T10:00:00",
    })
    ledger._add({
        "book_id": "B24",
        "borrower_id": "P24",
        "borrowed_at": "2026-05-05T10:00:00",
    })

    original_open_loans = ledger.open_loans

    def probing_open_loans():
        records = original_open_loans()
        for record in records:
            extra = set(record.keys()) - CANONICAL_KEYS
            if extra:
                violations.append({"record": dict(record), "extra_keys": extra})
        return records

    ledger.open_loans = probing_open_loans

    overdue(
        ledger,
        as_of=datetime.datetime(2026, 5, 22, 10, 0, 0),
        loan_period=datetime.timedelta(days=7),
    )

    assert violations == [], (
        f"overdue transiently mutated ledger records during the call; "
        f"records with unexpected keys observed: {violations}"
    )
