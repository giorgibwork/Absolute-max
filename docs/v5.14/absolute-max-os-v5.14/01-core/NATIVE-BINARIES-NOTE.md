# Native binaries

v5.2 fidelity layer is designed to **overlay** the verified native binaries from Absolute Max OS v5.1 (`os-core/bin/`).

On DSH-Go:
1. Keep v5.1 `os-core/bin/` (spr-verify, pagegram-guard, os-daemon, etc.)
2. Replace/overlay docs and rules with this v5.2 tree
3. Enforce contracts + RSI gate + threat model from v5.2

On non-DSH hosts: ignore native bins; use `04-portable/`.

Do not re-introduce domain engines onto the default PATH.
