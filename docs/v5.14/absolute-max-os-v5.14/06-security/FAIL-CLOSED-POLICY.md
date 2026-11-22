# Fail-Closed Policy — v5.4

## Unknown capability

Unknown or unclassified operation → **DENY** (not read-only fallback).

## Path safety

- Reject path traversal and escapes outside workspace/approved roots
- Canonicalize before allow
- Empty / `.` / absolute sensitive paths → DENY unless explicitly in policy

## Policy checker vs enforcement

A standalone policy function is not proof of DSH tool-boundary enforcement.  
Document integration status honestly: VERIFIED | PARTIAL | UNVERIFIED | BLOCKED.

## Spoof resistance

CLI flags or caller metadata must not self-approve consequential ops under PREPARE_ONLY.
