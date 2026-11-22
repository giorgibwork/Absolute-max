"""BAVAR Adaptive Verification + MCP Code Mode Return-Shape Stubs + FinVeriQA Math Guard.

Pure Python 3.14 stdlib ($0.00):
- BAVAR (Adeli et al., 2026): allocates verification effort strictly by
  criticality, irreversibility, uncertainty, and remaining budget (avoids verifier tax).
- MCP Code Mode Stubs (arXiv:2611.19123): renders compact typed Python stubs with
  explicit return-shape hints instead of dumping raw JSON schemas every turn.
- FinVeriQA Python Math Guard (arXiv:2611.25071): safe AST-only arithmetic evaluator
  (zero eval() RCE) that records every computed number into the Evidence Store.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any

from . import OmegaPaths, get_paths
from .memory import KnowledgeFabric

HIGH_RISK_CLASSES = {"SPEND", "PRIVILEGE_CHANGE", "EXTERNAL_MUTATION", "DESTRUCTIVE", "EVOLUTION_PROMOTE"}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_SAFE_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
}


def allocate_verification(
    action_class: str,
    *,
    uncertainty: float = 0.2,
    irreversible: bool = False,
    budget_remaining: float = 1.0,
) -> dict[str, Any]:
    """BAVAR Budgeted Adaptive Verification policy."""
    ac = action_class.upper().strip()
    unc = max(0.0, min(1.0, float(uncertainty)))
    bud = max(0.0, min(1.0, float(budget_remaining)))
    critical = irreversible or (ac in HIGH_RISK_CLASSES)

    if critical and bud < 0.08:
        return {
            "tier": "ABSTAIN_CLARIFY",
            "checks": ["deterministic_kernel_gate", "human_approval_required"],
            "estimated_llm_calls": 0,
            "reason": "BAVAR budget exhaustion on irreversible/critical action -> abstain & ask human.",
        }
    if critical or unc >= 0.65:
        return {
            "tier": "CROSS_FAMILY_JURY",
            "checks": ["deterministic_kernel_gate", "unit_and_copy_test", "cross_family_adversarial_check"],
            "estimated_llm_calls": 1,
            "reason": f"High criticality ({ac}, irreversible={irreversible}) or high uncertainty ({unc:.2f}).",
        }
    if ac in ("WORKSPACE_MUTATION", "LOCAL_PREPARE") or unc >= 0.35:
        return {
            "tier": "UNIT_AND_MUTANT",
            "checks": ["deterministic_kernel_gate", "unit_and_copy_test"],
            "estimated_llm_calls": 0,
            "reason": "Bounded local code edit -> deterministic tests sufficient (saves LLM verifier calls).",
        }
    return {
        "tier": "DETERMINISTIC_ONLY",
        "checks": ["deterministic_kernel_gate"],
        "estimated_llm_calls": 0,
        "reason": "Low-risk read/inspect action -> microsecond deterministic gate only.",
    }


def generate_code_mode_stubs(tools: list[dict[str, Any]]) -> str:
    """Emit compact MCP Code Mode stubs with explicit return-shape hints (arXiv:2611.19123)."""
    lines = ["# OMEGA MCP Code Mode Stubs (with explicit return-shape hints)"]
    for t in tools:
        name = t["name"]
        params = t.get("params", "")
        ret = t.get("returns", "{ok: bool, data: any, error?: str}")
        desc = t.get("desc", "")
        lines.append(f"def {name}({params}) -> dict:  # returns: {ret}" + (f" | {desc}" if desc else ""))
    return "\n".join(lines) + "\n"


def _eval_ast_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("Exponent out of safe bounds.")
        return float(_BIN_OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return float(_UNARY_OPS[type(node.op)](_eval_ast_node(node.operand)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
        args = [_eval_ast_node(a) for a in node.args]
        return float(_SAFE_FUNCS[node.func.id](*args))
    raise ValueError(f"Disallowed expression construct: {type(node).__name__}")


def verified_calc(
    expression: str,
    *,
    label: str = "calculation",
    mission_id: str = "",
    record_evidence: bool = True,
    paths: OmegaPaths | None = None,
) -> dict[str, Any]:
    """FinVeriQA guard: compute exact numbers via safe AST arithmetic and log evidence."""
    expr = expression.strip()
    if not expr or len(expr) > 256:
        raise ValueError("Expression must be 1..256 chars.")
    tree = ast.parse(expr, mode="eval")
    val = _eval_ast_node(tree)
    rounded = round(val, 8)
    ev_id = ""
    if record_evidence:
        kf = KnowledgeFabric(paths or get_paths())
        ev = kf.record_evidence(
            claim_text=f"{label}: {expr} = {rounded}",
            source_id="omega_bavar_calc",
            locator=f"python_ast://{expr}",
            content_sample=f"{expr} == {val!r}",
            mission_id=mission_id,
            source_type="dataset",
            retrieval_scope="full_text",
            support_type="supports",
            verification_method="deterministic_python_ast",
            verification_status="verified",
        )
        ev_id = ev["evidence_id"]
    return {"label": label, "expression": expr, "value": rounded, "evidence_id": ev_id}
