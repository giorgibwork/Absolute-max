# RSI Statistical Gate (TRUST-hardened) — v5.3.0

**Purpose:** Stop recursive self-improvement from accepting lucky or inferior updates.  
**Evidence base:** TRUST (arXiv:2611.10787), hold-out practice, BOXBOX/Meta² spirit.

## Rule

No harness edit, plugin change, prompt change, or synthesized tool is **promoted to default** until this gate passes.

## Procedure

1. **Propose**  
   Exact change (path, diff summary, or rule text).

2. **Consult Meta-Skill**  
   Read `05-rsi/META-SKILL.md`. If Meta-Skill says KEEP for this pattern, do not evolve unless new evidence clearly overrides.

3. **Primary test**  
   Motivating case must improve (S=1).

4. **Hold-out test**  
   At least one related case **not** used to design the change. No regression.

5. **Failure probe**  
   Known bad input still fails closed (no new injection/privilege path).

6. **False-evolution control (TRUST spirit)**  
   - Prefer ≥2 independent runs or clear multi-check evidence when stakes are high.  
   - If only one run: treat as **candidate**, not default, until a second confirming case.  
   - Track accepted updates that later prove inferior; if rate rises, tighten gate.

7. **Decision**  
   - **Promote** — primary fixed, hold-out non-regressive, failure probe clean, Meta-Skill not violated.  
   - **Reject / quarantine** — otherwise; keep prior version active.  
   - Log decision + evidence in diagnostics or a short promote/reject note.

## Regression definition

- Prior passing task now fails  
- New injection or privilege path  
- Large token cost increase without quality gain  
- SPR or memory guard weakened  

## Integration

- BOXBOX tool synthesis: sandbox test = primary; second sample = hold-out.  
- Plugin / AGENTS edits: same gate before `active`.  
- Daily improver: never auto-promote; always leave promote/reject record.

---

## v5.4 binding

- Positive check: suite metric improves (success, tokens/success, stuck rate, or time-to-done) within tolerance on others
- Negative check: no rise in false completions, rule breaks, boot failures, memory origin gaps
- Both required or REJECT and log in META-SKILL
- No land from fluency or single lucky run
- Holdout / adversarial tickets when overfitting suspected
