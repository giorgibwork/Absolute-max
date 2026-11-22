# MCP Code Mode + Return-Shape Hints

**Source:** Beyond Plain MCP: Do Decision Models and Code Mode Make Tool Use Cheaper and Faster? (arXiv:2611.19123, 14 Nov 2026). Harness + traces released.

**Status:** Preferred tool-use paradigm for Absolute Max when tool catalogs grow or token cost matters. Free-only.

## Core Results
- **Code mode** (agent writes short scripts against tool stubs) substantially outperforms plain MCP tool calling.
- Token usage cut **70–90%** while utility rises.
- Declaring **return-shape hints** in stubs is first-order: swings success by up to **39.5 points** for weaker agents — larger effect than adding a decision-layer router.
- Decision layer in front of code mode: minor non-significant gains for weaker agents; slight cost for strongest. Do not treat router-as-always-better.

## Protocol for Absolute Max
1. Prefer **code mode** over dumping full tool schemas into every turn (aligns with default-dark + TICKET-AND-TOOLS projection).
2. Every tool stub exposed to the agent MUST include a concise **return-shape hint** (types, key fields, error shape). Example: `returns: {ok: bool, path: string, error?: string}`.
3. When catalog size > ~20–50 tools or many distractors, still prefer code mode first; only add a cheap decision/router layer if measured utility improves on the host.
4. Keep tool projection dark: Router assigns `tool_class`; code mode operates inside that class.
5. Truncate and hash large tool outputs; code mode scripts should request only needed fields.

## Integration
- Update any MCP / plugin catalog notes: stubs with return-shape > plain list.
- EXTERNAL-TOOLS-AND-PLUGINS and host transfer packs: prefer code-mode examples.
- Cost discipline (09-cost) and HarnessMM: code mode reduces rounds and tokens → higher reuse opportunity.
- Pair with ActiveSec / capability rings: scripts still execute under Ring-0 / class guards; intelligence proposes script, authority runs it.

## Anti-patterns
- Full schema dump every turn.
- Code mode without return-shape hints (especially on smaller/open-weight readers).
- Assuming a decision layer is mandatory; measure first.
