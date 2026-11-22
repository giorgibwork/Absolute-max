# Ticket: Install DSH minimal plugin set

```text
TICKET:
  goal: Install minimal Absolute Max plugin set on DSH Go without breaking boot
  success: each plugin listed/loadable; boot healthy; OS_READY still yes
  fail: boot failure; dangling Cordis; live config outside disposable if PREPARE_ONLY demands isolation
  max_turns: 20
  tool_class: SHELL
  risk: T2
```

Order: market → memory → MCP → panel → optional compact.  
Verify after each. Stop on failure and revert last insert.
