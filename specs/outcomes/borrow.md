---
outcome: borrow
status: locked
created: 2026-05-22
updated: 2026-05-22
co_specifier: lars-appel
spec_author: etdd-spec-author-borrow
free_dimensions:
  - cli-flag-spelling
  - exact-error-message-wording
  - success-output-shape
  - default-loan-limit-value
  - due-date-presence-and-policy
---

# Outcome: borrow

A registered borrower takes out a book from the catalog. The system records that this borrower now holds this book until it is returned. After a successful borrow, the book is on loan to that borrower and counts against the borrower's open-loan tally; before that point, neither was true. The operation is the librarian's act of handing the physical book across the desk and writing the borrower's name in the ledger. The act either succeeds or it is refused; partial states do not exist.

## Named edge cases

- **Book already on loan.** A book that is currently checked out to any borrower cannot be borrowed again. The attempt is refused. The existing loan is unaffected — the original borrower still holds the book, the book's on-loan state does not change, and no second loan record comes into being.

- **Borrower already at their loan limit.** Each borrower has a maximum number of books they may hold open at once. A borrower who is already holding that maximum cannot take out a further book. The attempt is refused. The borrower's existing loans are unaffected and the book remains available in the catalog for anyone else who is eligible.

- **Book not in the catalog.** A book identifier that the catalog does not recognise cannot be borrowed. The attempt is refused. The catalog is unaffected — the refusal does not implicitly register the book, and a follow-up `borrow` on the same identifier is refused on the same ground.

- **Borrower not registered.** A borrower identifier that the registry does not recognise cannot borrow. The attempt is refused. The registry is unaffected — the refusal does not implicitly register the borrower, and a follow-up `borrow` for the same identifier is refused on the same ground.

## Additional edge cases

- **Successful borrow produces a loan record.** When the borrow is permitted, a new loan record comes into being that identifies the borrower, the book, and the moment the loan was opened. That record is the basis on which a future `return` closes the loan and on which `overdue` (or a sibling reporting feature) can list it. The record is observable to the caller of `borrow` — a successful borrow does not vanish silently.

- **The same borrower cannot borrow the same book twice while their loan is open.** This case is already covered by "book already on loan," but the symmetry matters: the rule is keyed on the book's state, not on whether the second attempt comes from the same person. A borrower returning to ask for a book they already hold is refused on the same ground as a stranger asking for that book.

- **Refusals are distinguishable.** A caller can tell which of the four refusal grounds applied — book-on-loan, limit-reached, unknown-book, unknown-borrower. The grounds are not collapsed into a single opaque refusal. The exact wording of how the ground is conveyed is a free dimension; the fact that the four grounds are distinguishable is constrained.

- **Refusals leave no trace in the loan history.** A refused `borrow` does not create a loan record, does not create a "denied" entry, and does not advance any counter that an eligible later attempt would observe. From the ledger's point of view, a refused borrow did not happen.

- **Precedence among refusal grounds is not pinned.** When more than one refusal ground applies — for example, an unknown borrower attempting to take out a book that is also already on loan — the outcome does not pin which ground is reported. Any of the applicable grounds is acceptable, as long as the report is one of the four named grounds and the system state is unchanged. Implementations are free to check the grounds in any order.

- **`borrow` is the open half of a loan; `return` is the close half.** A successful `borrow` puts a book into the state from which a future `return` is the only legitimate exit. The outcome of `borrow` is consistent with a sibling `return` feature existing — the loan record `borrow` produces is the same record `return` consumes. `borrow` does not itself describe what `return` does; it commits to leaving the loan in a state a `return` can close.

## Free dimensions

The five axes named in the frontmatter are granted to the test-author and implementer:

- **cli-flag-spelling** — exact flag names on the CLI (for example `--book` versus `--book-id`, `--borrower` versus `--patron`) are surface naming, not load-bearing for the outcome.
- **exact-error-message-wording** — the prose used to convey each refusal ground is a craft choice. The constraint is that the four grounds remain distinguishable to the caller.
- **success-output-shape** — whether a successful borrow returns a confirmation string, a structured record, a loan identifier, or some combination is granted. The constraint is that the new loan record is observable to the caller.
- **default-loan-limit-value** — the numeric loan limit per borrower is not pinned by this outcome. The constraint is that the limit exists and is enforced; the value (3, 5, 10, or configurable) is the implementer's call, justified at test-author time if it has to be picked to write a test.
- **due-date-presence-and-policy** — whether the loan record carries a due-date at the moment `borrow` runs, and if so how that date is derived (fixed offset, configurable, none), is not pinned here. The constraint is that whatever shape the loan record takes, a sibling `return` can close it and a sibling overdue-reporting feature can read it.
