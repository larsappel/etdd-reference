---
artifact: docs/process/breaker-overdue.md
feature: overdue
breaker: etdd-breaker-overdue
breaker_model: opus
created: 2026-05-23
verdict: break-found
---

# Breaker report: overdue

## 1. Verdict

BREAK FOUND. The test suite under-specifies the outcome on three independent axes that an adversarial implementation can exploit simultaneously while remaining 12-of-12 green. The most surgical of the three — identity-field value fabrication — produces output that a downstream caller would treat as authoritative loan data, with values that bear no relation to the loan records the ledger actually holds. The other two — calling `datetime.utcnow()` and emitting results in non-deterministic order — violate properties the outcome states explicitly and the test docstrings acknowledge but the assertions do not catch.

## 2. The attack vector

The outcome says listed loans "carry the same identity the loan record already had ... at minimum the same `book_id`, `borrower_id`, and `borrowed_at` fields the borrow outcome put on the record." The test `test_listed_loans_carry_borrow_identity_fields` checks that the three keys exist in the returned dict and asserts the values of `book_id` and `borrower_id` match the source record — but it does not assert anything about the value of `borrowed_at`. An implementation that returns a freshly-constructed dict carrying `book_id` and `borrower_id` correctly but a fabricated `borrowed_at` (any ISO-format sentinel) satisfies every assertion. The other tests query only `book_id` (in some cases `borrower_id`) and ignore `borrowed_at` entirely.

Layered onto this: the outcome says "The function does not call `datetime.utcnow()` or any other time source." The test docstring restates this constraint, but no test fails when the function calls `utcnow()` and discards the result — every test supplies absolute `as_of` values, so the answer is unaffected. And the outcome's `sort-order-of-listed-loans` free dimension is granted "provided the order is deterministic for a fixed ledger state and call." No test pins order; every assertion uses `any(...)`, `not any(...)`, set comprehensions, or `len(...)`. A `random.shuffle` violates determinism invisibly. A fourth violation — transient mutation of ledger records during the call, reverted before return — also slips past, because `test_overdue_call_mutates_nothing` snapshots only before and after, not during.

## 3. The alternative implementation

```python
"""Adversarial alternative — passes all 12 tests, violates outcome intent on four axes."""

import datetime
import random


def overdue(ledger, *, as_of: datetime.datetime, loan_period: datetime.timedelta) -> list:
    # Violation 1: forbidden clock read.
    _now_ignored = datetime.datetime.utcnow()

    open_loans = ledger.open_loans()

    # Violation 4: transient mutation. Marker added, then removed before return.
    for record in open_loans:
        record["_breaker_marker"] = True

    overdue_records = []
    for record in open_loans:
        due_date = datetime.datetime.fromisoformat(record["borrowed_at"]) + loan_period
        if due_date <= as_of:
            # Violation 2: fabricated borrowed_at; key present, value invented.
            overdue_records.append({
                "book_id": record["book_id"],
                "borrower_id": record["borrower_id"],
                "borrowed_at": "1970-01-01T00:00:00",
            })

    # Revert violation 4 so the mutation-invariant test cannot observe it.
    for record in open_loans:
        del record["_breaker_marker"]

    # Violation 3: non-deterministic order.
    random.shuffle(overdue_records)

    return overdue_records
```

Verified: with this implementation swapped into `src/library_loan/overdue.py`, `python -m pytest tests/test_overdue.py -v` reports 12 passed.

## 4. Why it passes the tests

- `test_past_due_loan_is_listed` — checks `any(r["book_id"] == "B1" and r["borrower_id"] == "P1")`. The fabricated record carries the correct `book_id` and `borrower_id`, so the predicate matches.
- `test_exactly_at_due_date_is_listed` — same `any(...)` shape on `B2/P2`. The boundary `<=` is preserved by the alternative; the `<=` comparison itself is honest.
- `test_not_yet_due_loan_is_not_listed` — checks `not any(r["book_id"] == "B3")`. The alternative filters by the same `<=` boundary and emits no record for B3.
- `test_empty_ledger_returns_empty_list` — empty input yields empty `overdue_records`; the test accepts `result == []` or `len == 0`.
- `test_all_on_time_ledger_returns_empty_list` — all due-dates exceed `as_of`; no record emitted.
- `test_overdue_call_mutates_nothing` — the snapshot is taken via `[dict(r) for r in ledger.open_loans()]` before the call and again after. The transient `_breaker_marker` is added and deleted within the call, so the post-call snapshot equals the pre-call snapshot. The test never inspects intermediate state.
- `test_returned_loan_absent_from_overdue` — checks `not any(r["book_id"] == "B8")`. The real `return_` removed the record from the ledger, so `ledger.open_loans()` does not contain it and the alternative emits nothing for B8.
- `test_listed_loans_carry_borrow_identity_fields` — checks the three keys are present in the dict, then asserts `loan["book_id"] == "B9"` and `loan["borrower_id"] == "P9"`. The fabricated `borrowed_at` value is never inspected. THIS IS THE LOAD-BEARING GAP.
- `test_loan_period_controls_overdue_classification` — short and long `loan_period` both honored by the real `<=` comparison.
- `test_as_of_controls_overdue_classification` — past and future `as_of` both honored. The `utcnow()` call is made but the result is discarded, so the assertion is unaffected. THIS IS A LOAD-BEARING GAP for the no-clock rule.
- `test_overdue_judgment_independent_of_other_loans` — set membership over `book_id` only; all three loans are evaluated independently by the real `<=`.
- `test_multiple_overdue_loans_all_listed` — set equality `{r["book_id"] for r in result} == {"B15", "B16", "B17"}`. Order does not appear in any assertion, so `random.shuffle` is invisible.

## 5. Why it violates the outcome's intent

Four sentences in `specs/outcomes/overdue.md` are directly contradicted:

1. "Listed loans carry the same identity the loan record already had ... at minimum the same `book_id`, `borrower_id`, and `borrowed_at` fields the borrow outcome put on the record." The fabricated implementation emits the SAME KEYS but a fabricated VALUE for `borrowed_at`. A downstream caller asked "which loans are overdue and when were they borrowed?" receives `"1970-01-01T00:00:00"` for every overdue loan.
2. "The function does not call `datetime.utcnow()` or any other time source." The alternative calls `datetime.utcnow()` on the first line.
3. "The answer's order is not pinned ... provided the order is deterministic for a fixed ledger state and call." `random.shuffle` makes two calls with the same arguments return the same set in different orders.
4. "The call is a read and mutates nothing. No ledger entry is added, removed, or modified." The alternative adds a `_breaker_marker` key to every open-loan record during execution. The mutation is reverted before return, but during the call the ledger's records carry a key they did not carry before. A concurrent reader, a logging hook, or any code path that observes records mid-call sees the modification.

## 6. Recommended new negative predicates

The outcome document should grow an `## After adversarial review` section adding these constraints. Spec-author-revise should phrase them, but the substance is:

1. **Identity values, not just keys, match the source record.** "Each listed loan's `book_id`, `borrower_id`, and `borrowed_at` values are equal to the corresponding values on the open-loan record the ledger holds. Echoing the keys with fabricated values is not permitted."
2. **No clock reads of any kind.** "The function does not call `datetime.utcnow()`, `datetime.now()`, `time.time()`, `time.monotonic()`, or any other process-wide time source, even if the result is discarded. The `as_of` argument is the only moment the function is permitted to know about."
3. **Order is deterministic.** "Two calls with the same ledger state, the same `as_of`, and the same `loan_period` return overdue loans in the same order. The order itself is a free dimension; the determinism is not."
4. **No transient mutation during the call.** "During the call, no key is added to, removed from, or modified on any ledger record, even if reverted before return. A concurrent observer of the ledger during the call sees records in the same state they were in before the call began."

## 7. Recommended implementation fix shape

The current green implementation at `src/library_loan/overdue.py` already satisfies all four new predicates — it uses `dict(record)` to copy each record verbatim, does not import `random` or any time module beyond the type hint, and does no in-place mutation. The fix is therefore zero-line: the new predicates pin properties the current implementation already happens to honor, and the spec-author-revise pass adds the predicates without forcing a code change. A drafter wanting belt-and-braces could also add a test per new predicate (e.g., a `borrowed_at`-value check, a `monkeypatch.setattr(datetime.datetime, 'utcnow', ...)` clock-poisoning probe, a two-call order-equality assertion, and a record-identity-check on `ledger._loans` during a callback). Those test additions are the test-author-revise's call, not the breaker's.

## 8. Other attack vectors explored but rejected

- **Loan-period leak via a module-level default.** Considered an implementation that read `loan_period` from a module constant when the kwarg matched some sentinel, falling back to the supplied value otherwise. `test_loan_period_controls_overdue_classification` exercises two distinct `timedelta` values (3 days, 30 days) and asserts opposite verdicts; any implementation that ignores the supplied period for either value fails the test. The period axis is genuinely pinned by the two-call shape.
- **Output as a non-list iterable.** Considered returning a generator or a custom collection. `test_empty_ledger_returns_empty_list` admits `result == []` or `len(result) == 0`, and `test_all_on_time_ledger_returns_empty_list` requires `len(result) == 0`. A bare generator fails `len(...)`; a list subclass passes. The shape is loose ("list-like with `__len__` and iteration") but a generator-only return is caught. This is a real gap relative to the outcome's "iterable, has a definable length" phrasing but it does not enable an intent-violating implementation — every list-like the tests accept satisfies the outcome too.
- **Reading from a source other than `ledger.open_loans()`.** Considered an implementation that read `ledger._loans` directly or maintained a private cache. The test setup uses `ledger._add` to inject records, and the `borrow → return → overdue` chain in `test_returned_loan_absent_from_overdue` exercises the real `_remove` path. Any source that diverges from `open_loans()` would either miss injected records (failing the listing tests) or include returned ones (failing the absent-from-overdue test). The source is well-pinned by the chained-feature test.
- **Group-by-borrower-and-take-first.** Considered an implementation that grouped by `borrower_id` and reported at most one overdue loan per borrower. `test_overdue_judgment_independent_of_other_loans` uses two loans on the same borrower (`P12` holds both `B12` and `B13`) but only one is overdue, so this test does not catch the bug. `test_multiple_overdue_loans_all_listed` has two loans on `P14` (`B15` and `B17`), both overdue, and asserts set equality `{"B15", "B16", "B17"}`. A group-by-borrower-take-first implementation would emit only one of `B15`/`B17` and fail the set equality. Independence is well-pinned.
- **The "asked-about-the-past" framing flagged by the spec-author.** When `as_of` strictly predates every `borrowed_at`, the outcome implies the answer is empty (the loans are not yet at their due-date). `test_as_of_controls_overdue_classification` exercises exactly this case (`as_of = 2020-01-01`, loan borrowed in 2026) and asserts the past_result is empty. Any implementation that mis-handled the past-as_of case (e.g., by taking `abs(as_of - borrowed_at)` or by treating negative time-deltas as overdue) would fail this test. The candidate gap the spec-author invited the breaker to attack is, in fact, well-pinned. The deeper concern — whether a NAMED case for "asked-about-the-past" should exist in the outcome — is a documentation question, not a behavioural gap, and is not a break.
