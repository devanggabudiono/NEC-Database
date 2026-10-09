"""Cari preprint NEC di arXiv (API Atom) -> data/works_arxiv.csv.

Pakai:  python arxiv_search.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests
from lxml import etree

DATA = Path(__file__).resolve().parents[1] / "data"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
QUERIES = [
    'abs:"negative compressibility"',
    'abs:"negative electronic compressibility"',
    'abs:"negative electron compressibility"',
    'abs:"negative quantum capacitance"',
    'abs:"negative inverse compressibility"',
]


def fetch(q: str) -> list[dict]:
    rows, start = [], 0
    while True:
        r = requests.get("https://export.arxiv.org/api/query",
                         params={"search_query": q, "start": start, "max_results": 200}, timeout=120)
        r.raise_for_status()
        root = etree.fromstring(r.content)
        entries = root.findall("a:entry", NS)
        for e in entries:
            t = lambda p: " ".join((e.findtext(p, default="", namespaces=NS)).split())
            rows.append({
                "arxiv_id": t("a:id").rsplit("/abs/", 1)[-1], "doi": (t("arxiv:doi") or "").lower() or None,
                "title": t("a:title"), "year": int(t("a:published")[:4]), "journal": t("arxiv:journal_ref") or None,
                "category": e.find("arxiv:primary_category", NS).get("term"), "abstract": t("a:summary"), "query": q,
            })
        total = int(root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults"))
        print(f"  {len(rows)}/{total}", file=sys.stderr, flush=True)
        start += 200
        if start >= total or not entries:
            return rows
        time.sleep(3)


def main() -> None:
    rows = []
    for q in QUERIES:
        print(q, file=sys.stderr)
        rows += fetch(q)
        time.sleep(3)
    df = pd.DataFrame(rows)
    df["base"] = df.arxiv_id.str.replace(r"v\d+$", "", regex=True)
    df = df.drop_duplicates("base").drop(columns="base")
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA / "works_arxiv.csv", index=False)
    print(f"tersimpan {len(df)} preprint | kategori: {df.category.value_counts().head(8).to_dict()}")


if __name__ == "__main__":
    main()
