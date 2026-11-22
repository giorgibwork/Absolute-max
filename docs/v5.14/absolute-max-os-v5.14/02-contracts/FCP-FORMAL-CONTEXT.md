# FCP — Formal Context Protocol

**Source:** Shashank, FCP: Formal Context Protocol for Verifying LLM-Generated Artifacts (arXiv:2611.21679, 15 Nov 2026).

**Status:** Protocol for Absolute Max OS verification of LLM-generated artifacts (code, text, agent trajectories, designs) against the original request. Free-only, no new weights. Complements SPR, three-valued evidence, BAVAR, and existing formal verification notes.

## Core Claim
When the same system writes an artifact *and* its tests/assertions, a passing check is weak evidence: one misreading of the request yields both a faulty artifact and a check that accepts it. FCP checks the artifact against the *request itself*, independently of self-generated tests.

## Separation
- **Conformance**: Does the artifact satisfy a formal reading of a requirement? Decided by model checkers / SMT solvers.
- **Fidelity**: Does the formal reading mean what the prose means? No decision procedure; refutable by a concrete witness (behavior accepted by one independent reading and rejected by another).

## Eight False-Assurance Situations (each with mechanical witness except F)
| ID | Situation | Witness |
|----|-----------|---------|
| V | Vacuity (property never triggers) | Unreachable trigger proof |
| E | Assumption excludes artifact behaviors | Non-receptive state |
| F | Reading differs from prose meaning | Concrete behavior for human judgment |
| C | Requirements contradict | Unrealizability sequence |
| U | Request under-determines output | Two conforming behaviors differing in output |
| W | Properties too weak | Mutant not killed by any property |
| D | Holds only because black-box (model) behaves | Violation when component unconstrained |
| T | Engine/model wrong | Engine disagreement or simulator mismatch |

## Protocol Sketch (implementable without new weights)
1. Decompose request into atomic requirements (verbatim quotes, re-checked).
2. Produce ≥2 independent formal readings (assumptions A + property φ) via isolated formalizers.
3. Adapter maps artifact type to common engines:
   - Code → bounded exhaustive scope derived from request + recorded calls; optional translation-validated symbolic execution.
   - Text → labeled trace.
   - Agent → scaffold with free model input (trust class: enforced / delegated / broken).
   - Hardware → direct.
4. Run checks on request alone (conflicts, forcing stimuli, open choices, reading comparison in context) and on artifact (proof / exhaustive scope, replay, vacuity, mutants, trust classes).
5. Report per requirement: holds (proof), violated (replayed witness), or question (concrete example for author).
6. Circuit proof counts only if two engines agree; every counterexample is replayed.

## Integration
- Use before accepting LLM-generated code, tests, agents, or designs as done.
- Independent formalizers reduce correlated misreadings (measured effect: agreement does not imply correctness).
- Composes with BAVAR (budgeted allocation of formal checks) and SPR terminal gate.
- Questions that only the request author can answer become Clarify / Abstain paths (DISCERN).

## Effect Size Notes
Hardware (4 designs): self-assertions certified 23% of violated requirements; FCP certified none. Code (10 tasks, 3 models): every model passed its own tests and violated the request; self-tests certified all 33 violations; FCP certified 3 (removable by one additional reading of an ambiguous phrase). Agreement among models, readings, or tests did not imply correctness.

## Fail-closed
No independent reading or no witness for a claimed hold → treat as Unsupported. Conflicting readings → surface concrete witness and do not promote. Engine disagreement → do not accept proof.
