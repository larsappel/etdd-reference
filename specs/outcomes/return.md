---
outcome: return
status: locked
created: 2026-05-22
updated: 2026-05-22
co_specifier: lars-appel
spec_author: etdd-spec-author-return
free_dimensions:
  - call-signature-shape
  - success-output-shape
  - exact-error-message-wording
  - refusal-reason-string-spelling
  - whether-double-return-collapses-to-not-on-loan
---

# Outcome: return

A borrower who currently holds a book gives it back. The system closes the open loan that pairs this borrower with this book. After a successful return, the book is no longer on loan to that borrower, the borrower's open-loan tally has decreased by one, and the closed loan no longer appears among the open loans the ledger reports. The operation is the librarian's act of taking the physical book back across the desk and crossing the entry off the open ledger. The act either succeeds or it is refused; partial states do not exist. A return is the close half of the loan that a prior `borrow` opened; the loan record `borrow` produced is the same record `return` consumes.

## Named edge cases

- **Book not currently on loan.** A book that has no open loan against this borrower cannot be returned by this borrower. The attempt is refused. The refusal is an error, not a silent success: returning a book that was never borrowed (or that was already returned, or that is held by a different borrower) is a caller mistake and must be distinguishable from a successful close. The ledger is unaffected. Justification for the error-not-idempotent choice: the `borrow` precedent established that refusals are distinguishable to the caller and leave no trace; collapsing this case into a silent success would break that symmetry, hide double-submissions from a UI, and make double-return indistinguishable from first-return when the caller cannot already tell the open loans from the closed ones. The error path preserves the property that a caller who passes through the function without raising can act on a real state change. Idempotency, if a future caller needs it, is a wrapper concern over a function that distinguishes the grounds, not the function's own responsibility.

- **Double-return.** A borrower attempting to return the same book a second time, after a successful return has already closed the loan, is refused on the same ground as "book not currently on loan." The first return closed the loan; the second return finds no open loan to close. The ledger is unaffected by the second attempt — neither the closed loan from the first call nor any other record changes. Whether the implementation treats double-return as a distinct refusal ground or as a special case of "book not currently on loan" is a free dimension; what is constrained is that the second return does not succeed and does not mutate state.

- **Returning past due-date.** The loan record produced by `borrow` carries only the moment the loan was opened (`borrowed_at`); it does not carry a due-date. From the loan record alone, the system cannot determine whether a return is overdue. The "past due-date" edge therefore reduces to "a normal return": the loan is closed in the usual way and no overdue flag appears in the output, because no due-date exists to compare against. If a later feature introduces a due-date field on the loan record (in either the third ETDD-treated feature of this repo or a future build), `return` will need to revisit this — overdue-flagging behaviour would belong in that revisit. This outcome does not leave that axis free; it declares the current build's loan-record shape does not support overdue determination, and a future build that adds a due-date must update this outcome rather than have the drafter infer the behaviour.

## Additional edge cases

- **Successful return closes the loan and is observable.** When the return is permitted, the open loan pairing this borrower with this book is removed from the ledger. After the call, `ledger.loans_for_book(book_id)` no longer contains the closed loan; `ledger.loans_for(borrower_id)` no longer contains it; `ledger.open_loans()` no longer contains it. The caller of `return` observes that the return happened — the call does not vanish silently. The exact shape of what the caller observes (the closed record echoed back, a confirmation, `None`, or some other observable signal) is a free dimension; what is constrained is that a successful return is distinguishable from a no-op and from a refusal.

- **Refusals are distinguishable.** A caller can tell on what ground a return was refused. The `LoanRefused` exception established by `borrow` is reused; the reason strings introduced for `return` are enumerable and distinct from each other and from the four borrow grounds. The exact reason-string spelling is a free dimension; the constraint is enumerability and distinguishability. At minimum the "book not currently on loan" ground is named distinctly. If the implementation chooses to split double-return into its own ground, that ground is also distinct.

- **Refusals leave no trace.** A refused return does not mutate the ledger. No "denied return" entry is created. No counter advances. No previously-open loan becomes closed or vice versa as a side effect of the refused call. From the ledger's point of view, a refused return did not happen. This mirrors the borrow precedent.

- **A returned book becomes borrowable again.** After a successful return, the book is once again eligible to be borrowed — by the same borrower or by a different one — through the normal `borrow` path. `return` does not itself describe what subsequent borrows do; it commits to leaving the book in a state from which a future `borrow` is the legitimate next operation. The borrower's open-loan count has decreased by one, so a borrower who was at their loan limit before the return now has room for one more loan. The loan-limit value itself remains a free dimension established by the `borrow` outcome and is not re-pinned here.

- **Return is keyed on the open loan, not on borrower identity alone.** A borrower with multiple open loans returning one book closes only that one loan; the borrower's other open loans are unaffected. Symmetrically, a book on loan to borrower A cannot be returned by borrower B — the (borrower, book) pair must identify a currently-open loan. Whether borrower B's attempt is refused as "book not currently on loan to this borrower" or as a more specific "wrong borrower" ground is a free dimension; what is constrained is that B's attempt does not close A's loan and does not succeed.

## Free dimensions

The five axes named in the frontmatter are granted to the test-author and implementer:

- **call-signature-shape** — whether the public function is `return_(ledger, *, book_id, borrower_id)`, whether it also accepts `catalog` and `registry` for symmetry with `borrow`, or whether it accepts a loan record / loan id directly. The constraint is that the behaviour is testable against the public ledger interface (`open_loans`, `loans_for`, `loans_for_book`); the keyword-argument shape is the implementer's call.
- **success-output-shape** — whether a successful return returns the closed loan record, a confirmation string, a boolean, `None`, or some combination. The constraint is that a successful return is observably distinguishable from a refusal and from a no-op.
- **exact-error-message-wording** — the prose used to convey each refusal ground is a craft choice. The constraint is that the grounds remain distinguishable to the caller.
- **refusal-reason-string-spelling** — the exact spelling of return-specific `LoanRefused` reason strings (for example `not_on_loan`, `no_open_loan`, `book_not_borrowed`, or another spelling) is the implementer's call. The constraint is that the strings are distinct from the four borrow grounds and from each other if more than one is introduced.
- **whether-double-return-collapses-to-not-on-loan** — whether the implementation introduces a separate refusal ground for double-return or treats it as a special case of "book not currently on loan." The constraint is that double-return does not succeed and does not mutate state; the surface taxonomy is granted.
