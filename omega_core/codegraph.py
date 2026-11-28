"""Vectorless Python AST Code-Graph Indexer & Recursive-CTE Call-Graph Navigator.

Pure Python 3.14 stdlib + SQLite FTS5 ($0.00, zero embeddings, zero pip deps).
Parses repositories incrementally (SHA-256 skip unchanged files) into exact
symbols, signatures, docstrings, line ranges, and call edges so agents read
only the exact 30 lines needed instead of whole files.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import time
from typing import Any

from . import (
    SCHEMA_BIT_CODEGRAPH,
    OmegaPaths,
    ensure_dirs,
    get_paths,
    mark_schema_bit,
    safe_fts_query,
    schema_has_bit,
    tune_sqlite,
)

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".antigem"}


def _db_path(paths: OmegaPaths) -> str:
    return os.path.join(paths.omega_home, "codegraph.db")


def _connect(paths: OmegaPaths, *, read_only: bool = False) -> sqlite3.Connection:
    ensure_dirs(paths)
    conn = sqlite3.connect(_db_path(paths), timeout=5.0)
    conn.row_factory = sqlite3.Row
    if schema_has_bit(conn, SCHEMA_BIT_CODEGRAPH):
        tune_sqlite(conn, read_only=read_only)
        return conn
    tune_sqlite(conn, read_only=False)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            lines INTEGER NOT NULL,
            indexed_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            name TEXT NOT NULL,
            qualname TEXT NOT NULL,
            kind TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            signature TEXT NOT NULL DEFAULT '',
            docstring TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_path);
        CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);

        CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(
            name, qualname, signature, docstring, file_path,
            content='symbols', content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS sym_ai AFTER INSERT ON symbols BEGIN
            INSERT INTO symbols_fts(rowid, name, qualname, signature, docstring, file_path)
            VALUES (new.id, new.name, new.qualname, new.signature, new.docstring, new.file_path);
        END;
        CREATE TRIGGER IF NOT EXISTS sym_ad AFTER DELETE ON symbols BEGIN
            INSERT INTO symbols_fts(symbols_fts, rowid, name, qualname, signature, docstring, file_path)
            VALUES ('delete', old.id, old.name, old.qualname, old.signature, old.docstring, old.file_path);
        END;

        CREATE TABLE IF NOT EXISTS call_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_file TEXT NOT NULL,
            caller_symbol TEXT NOT NULL,
            callee_name TEXT NOT NULL,
            lineno INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_edge_callee ON call_edges(callee_name);
        CREATE INDEX IF NOT EXISTS idx_edge_caller ON call_edges(caller_symbol);
        """
    )
    mark_schema_bit(conn, SCHEMA_BIT_CODEGRAPH)
    conn.commit()
    return conn


def _format_args(args: ast.arguments) -> str:
    names = [a.arg for a in args.posonlyargs] + [a.arg for a in args.args]
    if args.vararg:
        names.append(f"*{args.vararg.arg}")
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append(f"**{args.kwarg.arg}")
    return f"({', '.join(names)})"


def _extract_callee(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


class CodeGraph:
    def __init__(self, paths: OmegaPaths | None = None):
        self.paths = paths or get_paths()
        conn = _connect(self.paths)
        conn.close()

    def index_directory(self, root_dir: str) -> dict[str, Any]:
        """Incrementally index all .py files under root_dir (skips unchanged files by SHA-256)."""
        t0 = time.monotonic()
        abs_root = os.path.abspath(os.path.expanduser(root_dir))
        conn = _connect(self.paths)
        indexed = 0
        skipped = 0
        errors = 0
        symbols_added = 0
        edges_added = 0
        now = int(time.time())

        try:
            existing = {r["path"]: r["sha256"] for r in conn.execute("SELECT path, sha256 FROM files").fetchall()}
            seen_on_disk: set[str] = set()
            for root, dirs, files in os.walk(abs_root):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for fn in sorted(files):
                    if not fn.endswith(".py") or ".bak" in fn:
                        continue
                    fp = os.path.join(root, fn)
                    seen_on_disk.add(fp)
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            src = f.read()
                    except OSError:
                        errors += 1
                        continue
                    sha = hashlib.sha256(src.encode("utf-8")).hexdigest()
                    if existing.get(fp) == sha:
                        skipped += 1
                        continue
                    try:
                        tree = ast.parse(src, filename=fp)
                    except SyntaxError:
                        errors += 1
                        continue

                    conn.execute("DELETE FROM symbols WHERE file_path = ?", (fp,))
                    conn.execute("DELETE FROM call_edges WHERE caller_file = ?", (fp,))

                    syms, edges = self._parse_tree(fp, tree)
                    conn.executemany(
                        """
                        INSERT INTO symbols (file_path, name, qualname, kind, start_line, end_line, signature, docstring)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        syms,
                    )
                    conn.executemany(
                        "INSERT INTO call_edges (caller_file, caller_symbol, callee_name, lineno) VALUES (?, ?, ?, ?)",
                        edges,
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO files (path, sha256, lines, indexed_at) VALUES (?, ?, ?, ?)",
                        (fp, sha, len(src.splitlines()), now),
                    )
                    indexed += 1
                    symbols_added += len(syms)
                    edges_added += len(edges)
            # Prune deleted/renamed files under abs_root so stale ghost symbols never linger
            prefix = abs_root.rstrip(os.sep) + os.sep
            pruned_files = 0
            for old_path in list(existing.keys()):
                if (old_path.startswith(prefix) or old_path == abs_root) and old_path not in seen_on_disk:
                    conn.execute("DELETE FROM symbols WHERE file_path = ?", (old_path,))
                    conn.execute("DELETE FROM call_edges WHERE caller_file = ?", (old_path,))
                    conn.execute("DELETE FROM files WHERE path = ?", (old_path,))
                    pruned_files += 1
            conn.commit()
            tot_syms = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            tot_edges = conn.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0]
        finally:
            conn.close()

        return {
            "root": abs_root,
            "files_indexed": indexed,
            "files_unchanged_skipped": skipped,
            "files_pruned": pruned_files,
            "errors": errors,
            "symbols_added": symbols_added,
            "edges_added": edges_added,
            "total_symbols": tot_syms,
            "total_edges": tot_edges,
            "elapsed_ms": round((time.monotonic() - t0) * 1000.0, 2),
        }

    def _parse_tree(self, fp: str, tree: ast.AST) -> tuple[list[tuple], list[tuple]]:
        syms: list[tuple] = []
        edges: list[tuple] = []

        def visit_body(body: list[ast.stmt], prefix: str = "") -> None:
            for node in body:
                if isinstance(node, ast.ClassDef):
                    qn = f"{prefix}.{node.name}" if prefix else node.name
                    doc = (ast.get_docstring(node) or "")[:240]
                    syms.append((fp, node.name, qn, "class", node.lineno, getattr(node, "end_lineno", node.lineno), f"class {node.name}", doc))
                    visit_body(node.body, qn)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qn = f"{prefix}.{node.name}" if prefix else node.name
                    sig = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}{_format_args(node.args)}"
                    doc = (ast.get_docstring(node) or "")[:240]
                    syms.append((fp, node.name, qn, "method" if prefix else "function", node.lineno, getattr(node, "end_lineno", node.lineno), sig, doc))
                    # Record calls belonging to this function, and recurse into nested defs
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            visit_body([sub], qn)
                        else:
                            for desc in ast.walk(sub):
                                if isinstance(desc, ast.Call):
                                    callee = _extract_callee(desc)
                                    if callee:
                                        edges.append((fp, qn, callee, getattr(desc, "lineno", node.lineno)))
                else:
                    # Module-level calls (e.g. top-level scripts / entrypoints)
                    if not prefix:
                        for desc in ast.walk(node):
                            if isinstance(desc, ast.Call):
                                callee = _extract_callee(desc)
                                if callee:
                                    edges.append((fp, "<module>", callee, getattr(desc, "lineno", getattr(node, "lineno", 1))))

        visit_body(getattr(tree, "body", []))
        return syms, edges

    def find_symbol(self, query: str, limit: int = 12) -> list[dict[str, Any]]:
        """BM25 symbol search returning exact file:start-end line slices."""
        q = query.strip()
        if not q:
            return []
        fts_q = safe_fts_query(q, mode="OR", max_terms=5) or q
        conn = _connect(self.paths, read_only=True)
        try:
            try:
                rows = conn.execute(
                    """
                    SELECT s.file_path, s.name, s.qualname, s.kind, s.start_line, s.end_line, s.signature, s.docstring
                    FROM symbols_fts f
                    JOIN symbols s ON s.id = f.rowid
                    WHERE symbols_fts MATCH ?
                    ORDER BY bm25(symbols_fts), s.name ASC
                    LIMIT ?
                    """,
                    (fts_q, int(limit)),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if not rows:
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT file_path, name, qualname, kind, start_line, end_line, signature, docstring
                    FROM symbols
                    WHERE name LIKE ? OR qualname LIKE ? OR signature LIKE ? OR docstring LIKE ?
                    ORDER BY name ASC LIMIT ?
                    """,
                    (like, like, like, like, int(limit)),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def trace_callers(self, symbol_name: str, max_hops: int = 2, limit: int = 25) -> list[dict[str, Any]]:
        """Multi-hop SQLite Recursive CTE upstream caller graph for impact analysis."""
        conn = _connect(self.paths, read_only=True)
        try:
            rows = conn.execute(
                """
                WITH RECURSIVE callers(caller_file, caller_symbol, callee_name, lineno, hop) AS (
                    SELECT caller_file, caller_symbol, callee_name, lineno, 1
                    FROM call_edges
                    WHERE callee_name = ?
                    UNION
                    SELECT e.caller_file, e.caller_symbol, e.callee_name, e.lineno, c.hop + 1
                    FROM call_edges e
                    JOIN callers c ON (
                        e.callee_name = c.caller_symbol
                        OR (instr(c.caller_symbol, '.') > 0 AND e.callee_name = substr(c.caller_symbol, instr(c.caller_symbol, '.') + 1))
                    )
                    WHERE c.hop < ?
                )
                SELECT DISTINCT caller_file, caller_symbol, callee_name, lineno, hop
                FROM callers
                ORDER BY hop ASC, caller_file ASC, lineno ASC
                LIMIT ?
                """,
                (symbol_name.strip(), max(1, min(4, int(max_hops))), int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def file_outline(self, file_path: str) -> list[dict[str, Any]]:
        ap = os.path.abspath(os.path.expanduser(file_path))
        conn = _connect(self.paths, read_only=True)
        try:
            rows = conn.execute(
                "SELECT qualname, kind, start_line, end_line, signature FROM symbols WHERE file_path = ? ORDER BY start_line ASC",
                (ap,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
