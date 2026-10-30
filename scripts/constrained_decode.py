#!/usr/bin/env python3
"""
constrained_decode.py — Example constrained-generation wrapper for STAIR
retrieval. Given a pre-built trie (from build_toc_trie.py) and a (ToC, query)
prompt, simulate prefix-constrained decoding that only permits valid leaf
titles.

In a real deployment this wraps a model's logits processor to zero out tokens
that are not valid continuations under the trie. Here we demonstrate the
constraint logic deterministically with a simple scoring stub so the contract
is clear.

Usage:
    python3 constrained_decode.py trie.json "your query here"
"""

import json
import sys
import argparse
from typing import Dict, List, Set, Any, Tuple


def load_trie(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def next_valid_chars(trie_node: Dict[str, Any], prefix: str) -> Set[str]:
    node = trie_node
    for ch in prefix:
        if ch not in node["children"]:
            return set()
        node = node["children"][ch]
    allowed = set(node["children"].keys())
    if node["is_terminal"]:
        allowed.add("<END>")
    return allowed


def is_valid_title(trie: Dict[str, Any], candidate: str) -> bool:
    node = trie
    for ch in candidate:
        if ch not in node["children"]:
            return False
        node = node["children"][ch]
    return node.get("is_terminal", False)


def _tokenize(text: str) -> Set[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    import re
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {tok for tok in cleaned.split() if tok}


def score_title(query: str, title: str, full_path: str) -> float:
    """
    Placeholder relevance scorer. Replace with model log-probability in production.
    Uses token-overlap with substring boost as a deterministic stand-in.
    """
    q_tokens = _tokenize(query)
    t_tokens = _tokenize(title + " " + full_path)
    q_lower = query.lower()
    # Primary score: token overlap ratio
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens) / len(q_tokens)
    # Substring boost: if a query term appears in the title as a substring
    substring_bonus = 0.0
    title_lower = title.lower()
    for qt in q_tokens:
        if qt in title_lower:
            substring_bonus += 0.2
    return min(overlap + substring_bonus, 1.0)


def constrained_rank(trie_data: Dict[str, Any], query: str, top_k: int = 3) -> List[Tuple[str, float]]:
    """Return top-k leaf titles ranked by relevance, ensuring all are valid."""
    valid_titles = trie_data["valid_titles"]
    leaves_by_title = {leaf["title"]: leaf for leaf in trie_data["leaves"]}

    scored: List[Tuple[str, float]] = []
    for title in valid_titles:
        leaf = leaves_by_title.get(title, {"full_path": title})
        assert is_valid_title(trie_data["trie"], title), f"Title {title!r} failed trie validation"
        scored.append((title, score_title(query, title, leaf.get("full_path", title))))

    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:top_k]


def main():
    parser = argparse.ArgumentParser(description="STAIR constrained decode example")
    parser.add_argument("trie_file", help="Path to trie.json from build_toc_trie.py")
    parser.add_argument("query", help="User query")
    parser.add_argument("-k", "--top-k", type=int, default=3, help="Number of top results")
    args = parser.parse_args()

    trie_data = load_trie(args.trie_file)
    results = constrained_rank(trie_data, args.query, top_k=args.top_k)

    print(f"Query: {args.query}")
    print(f"Corpus: {trie_data['document_title']} ({trie_data['leaf_count']} sections)")
    print("-" * 60)
    for rank, (title, score) in enumerate(results, 1):
        leaf_info = next((l for l in trie_data["leaves"] if l["title"] == title), {})
        print(f"#{rank}  [{score:.3f}]  {title}")
        if leaf_info.get("full_path"):
            print(f"       path: {leaf_info['full_path']}")


if __name__ == "__main__":
    main()
