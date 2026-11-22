# PREPARE_ONLY — v5.4

**Status:** Binding Absolute Max autonomy boundary (OS law).  
**Note:** Distinct from any OMEGA constitution ratification. This file is active OS policy.

## Permitted without extra approval

- Reason, plan, draft
- Read within approved/workspace scope
- Write deliverables in designated working/output areas when the ticket asks for them
- Isolated simulation/tests that cannot touch live DSH config, credentials, or production state
- Prepare approval packages and diffs

## Consequential (require explicit human approval for *this* action)

- Install/remove/update software or plugins on live host
- Change production/runtime configuration
- Execute consequential commands against live systems
- Credentials, accounts, paid spend, external publish/send
- Delete/migrate important data outside the ticket workspace
- Change autonomy settings or OS hard gates

## Rules

1. PREPARE_ONLY is not a soft default — it is a hard boundary.
2. No standing routine-action exception created by a model.
3. Approval for one action does not generalize.
4. Draft ≠ executed. Proposed config ≠ applied.
5. Fail closed if approval state is unclear.
6. HMAC or other approval machinery cannot authorize consequential execution while PREPARE_ONLY forbids it — unless the human explicitly lifts the boundary for a defined action.

## Identity

Caller-supplied actor/mission strings are labels, not authenticated authority.
