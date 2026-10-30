#!/usr/bin/env python3
"""
build_toc_trie.py — Build a deterministic trie (prefix tree) from a hierarchical
Table of Contents for constrained-decoding STAIR retrieval.

Usage:
    python3 build_toc_trie.py <toc.json> [-o trie.json]

toc.json format:
{
  "title": "Book Title",
  "children": [
    {"title": "Chapter 1", "children": [
      {"title": "1.1 First section", "children": []},
      {"title": "1.2 Second section", "children": []}
    ]}
  ]
}

Output trie.json maps every leaf title to its full hierarchical path and
contains the adjacency structure for constrained prefix-constrained decoding.
"""

import json
import sys
import argparse
from typing import Dict, List, Any, Set


def extract_leaves(node: Dict[str, Any], path_prefix: List[str] = None) -> List[Dict[str, str]]:
    """Walk the ToC tree and collect every leaf node with its full path."""
    if path_prefix is None:
        path_prefix = []
    current_path = path_prefix + [node.get("title", "")]
    children = node.get("children", []) or []
    if not children:
        # Leaf
        return [{
            "title": node["title"],
            "full_path": " > ".join([p for p in current_path if p]),
            "depth": len(current_path) - 1,
        }]
    leaves = []
    for child in children:
        leaves.extend(extract_leaves(child, current_path))
    return leaves


def build_trie(leaf_titles: List[str]) -> Dict[str, Any]:
    """
    Build a character-level trie over all leaf titles.
    Each node is {"children": {char: node}, "is_terminal": bool, "title": str|None}.
    """
    root: Dict[str, Any] = {"children": {}, "is_terminal": False, "title": None}
    for title in leaf_titles:
        node = root
        for ch in title:
            if ch not in node["children"]:
                node["children"][ch] = {"children": {}, "is_terminal": False, "title": None}
            node = node["children"][ch]
        node["is_terminal"] = True
        node["title"] = title
    return root


def get_valid_continuations(trie: Dict[str, Any], prefix: str) -> Set[str]:
    """Given a prefix, return the set of next characters that are valid."""
    node = trie
    for ch in prefix:
        if ch not in node["children"]:
            return set()
        node = node["children"][ch]
    return set(node["children"].keys()) | ({"<END>"} if node["is_terminal"] else set())


def main():
    parser = argparse.ArgumentParser(description="Build a STAIR trie from a hierarchical ToC JSON file.")
    parser.add_argument("toc_file", help="Path to ToC JSON")
    parser.add_argument("-o", "--output", default="trie.json", help="Output trie JSON path")
    args = parser.parse_args()

    with open(args.toc_file, "r", encoding="utf-8") as f:
        toc = json.load(f)

    leaves = extract_leaves(toc)
    leaf_titles = [leaf["title"] for leaf in leaves]

    # Deduplicate while preserving order
    seen: Set[str] = set()
    unique_titles: List[str] = []
    for t in leaf_titles:
        if t not in seen:
            seen.add(t)
            unique_titles.append(t)

    trie = build_trie(unique_titles)

    output = {
        "document_title": toc.get("title", "Untitled"),
        "leaf_count": len(unique_titles),
        "leaves": leaves,
        "trie": trie,
        "valid_titles": unique_titles,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Built trie with {len(unique_titles)} leaves → {args.output}")


if __name__ == "__main__":
    main()
