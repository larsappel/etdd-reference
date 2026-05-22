# PROMPTS

Archive of the agent prompts used to build this repository. The verbatim prompt text for each role is recorded after the role runs. Per-feature attribution lists which agent identifier played which role.

## Principle-6 compliance declaration

For every ETDD-treated feature in this repo, three distinct agent identifiers played the roles of outcome-document-author, test-author, and implementation-author. No agent occupied more than one of those roles for the same feature.

The program's contract-author role has no per-feature CLI-side analogue here; the repo-level acceptance contract lives at [`program/workstreams/W2-poc-repo/etdd-reference.accept.md`](https://github.com/larsappel/extreme-tdd-program/blob/main/program/workstreams/W2-poc-repo/etdd-reference.accept.md) in the program repo and was authored by a separate contract-author (`contract-author-w2-reference`).

## Per-feature attribution

| Feature | Outcome-document-author | Test-author | Implementation-author | Breaker |
|---------|-------------------------|-------------|------------------------|---------|
| `borrow` | `etdd-spec-author-borrow` | `etdd-test-author-borrow` | `etdd-drafter-borrow` | _G5b_ |
| `return` | _G5b_ | _G5b_ | _G5b_ | _G5b_ |
| `<third feature>` | _G5b_ | _G5b_ | _G5b_ | _G5b_ |

## Roles

### Spec-author (outcome-document-author)

Writes `specs/outcomes/<slug>.md` for one feature. Treats the W2 spec at `program/workstreams/W2-poc-repo/etdd-reference.spec.md` and the matching feature row in §"Domain and feature set" as input. Names edge cases. Does not write the test or the implementation.

_Verbatim prompt: to be recorded after the role runs._

### Test-author

Writes `tests/test_<slug>.py` for one feature. Treats the matching outcome document as input. Every test traces to a sentence or named edge case in the outcome. Tests must fail at the commit that adds them (no implementation yet). Uses pytest only.

_Verbatim prompt: to be recorded after the role runs._

### Implementation-author

Writes the production code under `src/library_loan/` such that the failing tests pass. Treats the failing test file as the contract. Does not modify the outcome or the tests. Minimal code; no premature abstraction.

_Verbatim prompt: to be recorded after the role runs._

### Breaker (Pattern 5)

Reads the outcome (for intent) and the test (for the contract). Attempts to produce an implementation that passes the test while violating the outcome's intent. If a break is found, a new negative predicate is added to the outcome and the implementation is fixed. If no break is found, the report at `docs/process/breaker-<feature>.md` names at least three attack vectors the breaker explored.

The breaker is a fourth agent identifier — not the test-author and not the implementation-author for the feature it breaks.

_Verbatim prompt: to be recorded after the role runs._
