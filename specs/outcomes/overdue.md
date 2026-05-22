---
outcome: overdue
status: locked
created: 2026-05-22
updated: 2026-05-22
co_specifier: lars-appel
spec_author: etdd-spec-author-feature3
free_dimensions:
  - loan-period-source
  - default-loan-period-value
  - output-collection-shape
  - call-signature-shape
  - sort-order-of-listed-loans
---

# Outcome: overdue

A librarian asks which open loans are past their due-date as of a given moment. The system answers with the subset of the currently-open loans whose due-date has come and gone by that moment. The act is a read: the ledger, the catalog, and the registry are unaffected. The answer is computed afresh on each call from the open loans and the moment supplied; no overdue flag is stored on any loan record and none is added by the call. A loan that was overdue an hour ago and has since been returned is not in the answer; a loan that becomes due in the next second is not in the answer either.

## Why this feature, given the no-modify-borrow constraint

The `borrow` outcome left `due-date-presence-and-policy` free; the locked implementation pinned no due-date onto the loan record. The `return` outcome declined to leave its overdue axis free and stated that a future feature adding a due-date concept would force `return` to be revisited. `overdue` is that feature, and the choice exercises the demonstration goals more sharply than `extend` or `renew` would. `renew` can be defined entirely on the open-loan transition without reference to dates and so avoids the load-bearing axis the W2 spec invites a breaker to attack; `extend` requires both a due-date concept and an extensions registry and doubles the load without doubling the demonstration. `overdue` confronts the date axis head-on, names the `>=`-at-now boundary the practitioner guide treats as its canonical edge, and forces the spec to take an explicit stance on where the due-date comes from — all without touching `borrow.py`, `test_borrow.py`, or `return_.py`.

## Named edge cases

- **A loan past its due-date at the moment asked is listed.** Each open loan has a due-date derivable from `borrowed_at` and a loan-period value supplied to the call. A loan whose due-date is strictly earlier than the moment asked is in the answer. The closed half of an already-returned loan is not — only open loans are candidates.

- **A loan exactly at its due-date at the moment asked is listed.** The boundary is inclusive: when the moment asked equals the loan's due-date to the precision the system records times at, the loan is overdue. The convention mirrors the practitioner guide's `>=`-at-now edge for subscription access and the manifesto's stance that boundaries must be pinned rather than left to implementer discretion. A loan whose due-date is strictly later than the moment asked is not in the answer.

- **A loan not yet at its due-date at the moment asked is not listed.** Loans whose due-date lies in the future relative to the moment asked are open-and-on-time and absent from the answer. The asymmetry between this case and the previous one is the load-bearing distinction; an implementation that uses `>` instead of `>=` against the due-date silently drops the boundary loan and fails the previous case.

- **The empty ledger and the all-on-time ledger both produce an empty answer.** When no open loans exist, or when every open loan's due-date is strictly later than the moment asked, the answer is an empty collection of the declared output shape. The call does not raise. An empty answer is observably distinct from a refusal and from a call that did not happen.

## Additional edge cases

- **The call is a read and mutates nothing.** No ledger entry is added, removed, or modified. The catalog and the registry are not consulted and not changed. After the call, `ledger.open_loans()`, `ledger.loans_for(borrower_id)`, and `ledger.loans_for_book(book_id)` return exactly what they returned before the call, including for loans that the answer named as overdue. The overdue judgment is not a persisted property of the loan; it is a property of the loan-plus-moment pair recomputed on each call.

- **Returned loans never appear in the answer.** A loan that was open and overdue before being returned is not in the answer after `return_` has closed it. The `overdue` feature reads `ledger.open_loans()` and only the open loans; the closed records `return_` produces are out of scope. A loan closed at the exact moment asked is also not in the answer — `return_` has already removed it from the open set.

- **The moment asked is supplied by the caller, not read from a clock.** The function does not call `datetime.utcnow()` or any other time source. The moment used for the comparison is a caller-supplied argument. Rationale: a `datetime.utcnow()` read inside the function would make the answer dependent on hidden global state, would make the boundary case untestable without freezing time, and would prevent a caller from asking "which loans will be overdue at the start of tomorrow's business hours?" The same argument that makes the `>=`-at-now boundary verifiable also makes the function usable for projection queries.

- **The loan-period value is supplied per call.** The duration that converts `borrowed_at` into a due-date is an argument to the call, not a constant baked into the implementation and not a value read from the loan record. This is the spec's stance on the due-date source: the due-date is computed at query time as `borrowed_at + loan_period`, with `loan_period` passed in by the caller. The borrow record is not modified to add a due-date; no separate registry of due-dates is introduced; no module-level constant pins the period. A caller asking with a different period gets a different answer from the same ledger state, and that property is the test that an implementation has not silently leaked a default.

- **Listed loans carry the same identity the loan record already had.** Each entry in the answer identifies the borrower, the book, and the moment the loan was opened — at minimum the same `book_id`, `borrower_id`, and `borrowed_at` fields the borrow outcome put on the record. Whether the entry is the original loan-record dict, a copy of it, a new dict with a computed `due_at` added, or a richer structure with the moment asked echoed back is a free dimension; what is constrained is that each listed loan is identifiable to a caller who already knows the borrow record's shape.

- **The answer's order is not pinned.** When multiple loans are overdue, the order in which they appear in the answer is a free dimension. Implementations may order by `borrowed_at`, by `book_id`, by `borrower_id`, by insertion order in the ledger, or by any other deterministic ordering. The constraint is that the *set* of listed loans is exactly the overdue open loans; the order is the implementer's call.

- **Loans across borrowers and books are weighed independently.** Whether a given loan is overdue depends only on that loan's `borrowed_at`, the supplied loan-period, and the supplied moment. It does not depend on whether the borrower has other open loans, on whether the book has been borrowed before, on the borrower's loan-limit position, or on any other loan in the ledger. The function treats each open loan as an independent candidate.

## Free dimensions

The five axes named in the frontmatter are granted to the test-author and implementer:

- **loan-period-source** — whether the loan-period is a positional argument, a keyword argument named `loan_period`, a keyword argument named `period`, a `timedelta`, a count of days as an integer, or some other shape, is the implementer's call. The constraint is that the period is supplied by the caller, not read from a clock and not pinned by a module-level constant.

- **default-loan-period-value** — if the implementation chooses to support a default value for the loan-period when none is supplied, the numeric default is the implementer's call. The constraint is that an explicitly-supplied period is honoured; a default, if any, must be documented in the test file so the test-author's choice is visible.

- **output-collection-shape** — whether the answer is a `list`, a `tuple`, a generator, a `set`, or some richer collection type is granted. The constraint is that the answer is iterable, has a definable length, supports membership questions a test can ask, and is empty (not `None`) when no loan is overdue.

- **call-signature-shape** — whether the public function is `overdue(ledger, *, as_of, loan_period)`, `overdue_loans(ledger, as_of, loan_period)`, or another spelling is the implementer's call. The constraint is that the function is testable against the public ledger interface (`open_loans`, `loans_for`, `loans_for_book`) and that the moment asked and the loan-period are both caller-supplied.

- **sort-order-of-listed-loans** — the order in which overdue loans appear in the answer is granted, provided the order is deterministic for a fixed ledger state and call. Tests assert on the *set* of listed loans, not on positional order.

## Stance on the items the spec required an explicit position on

- **Loan-limit value.** Not re-pinned. `overdue` is a read over open loans and has no interaction with the loan-limit rule established by `borrow`. The limit value remains a free dimension at the `borrow` outcome's level; this outcome inherits that grant unchanged.

- **Due-date source.** A policy applied at query time. The due-date for each open loan is computed as `borrowed_at + loan_period`, where `loan_period` is supplied by the caller of `overdue`. No due-date field is added to the loan record; no separate due-date registry is introduced; no module-level constant pins the period. This stance keeps `borrow.py`, `test_borrow.py`, and `return_.py` unmodified — the loan record's shape is unchanged, the borrow API is unchanged, and the return API is unchanged. It also keeps the `return` outcome's declared position consistent: `return` said the loan record has no due-date and therefore cannot flag overdue at close-time; that remains true, and the overdue judgment lives only inside `overdue` calls, never as a persisted property.

- **Idempotency and repeatability.** The call is a pure read. Two consecutive calls with the same ledger state, the same moment asked, and the same loan-period yield equal answers. The call mutates nothing the next call could observe. Repeatability is not a separate constraint to enforce; it is a property of the function being a read.

- **The moment a loan becomes overdue.** Inclusive at the due-date boundary. A loan whose due-date is exactly equal to the moment asked, to the precision the system records times at, is overdue. The comparison is `due_date <= as_of`, equivalently `borrowed_at + loan_period <= as_of`. The `<=` (or `>=` from the as_of side) is load-bearing and is the boundary the practitioner guide's worked example treats as its canonical edge.
