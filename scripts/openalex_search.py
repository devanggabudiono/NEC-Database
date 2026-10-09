"""Cari artikel NEC (negative electron compressibility) di OpenAlex -> data/works_openalex.csv.

Pakai:  python openalex_search.py [--max 0] [--from-year 1985] [--to-year 2026]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parents[1] / "data"
# (field, query): title_and_abstract untuk presisi, fulltext untuk recall frasa persis.
QUERIES = [
    ("title_and_abstract", '"negative electron compressibility"'),
    ("title_and_abstract", '"negative electronic compressibility"'),
    ("title_and_abstract", '"negative compressibility" AND (electron OR 2DEG OR "two-dimensional electron" OR bilayer OR graphene OR interface OR "quantum capacitance")'),
    ("title_and_abstract", '"negative quantum capacitance"'),
    ("fulltext", '"negative electronic compressibility"'),
    ("fulltext", '"negative electron compressibility"'),
    ("fulltext", '"negative compressibility" AND ("two-dimensional electron" OR 2DEG OR "quantum capacitance" OR "electron gas")'),
]
FIELDS = "id,doi,title,publication_year,ids,open_access,primary_location,cited_by_count,type,abstract_inverted_index,locations"


def abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = {i: w for w, idx in inv.items() for i in idx}
    return " ".join(pos[i] for i in sorted(pos))


def arxiv_id(locs: list[dict]) -> str | None:
    for loc in locs:
        m = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:v\d+)?(?:\.pdf)?$", loc.get("landing_page_url") or loc.get("pdf_url") or "")
        if m:
            return m.group(1)
    return None


def fetch(field: str, query: str, a) -> list[dict]:
    filt = f"{field}.search:{query},publication_year:{a.from_year}-{a.to_year},type:article|preprint"
    params = {"filter": filt, "per-page": 200, "cursor": "*", "select": FIELDS}
    if os.environ.get("OPENALEX_MAILTO"):
        params["mailto"] = os.environ["OPENALEX_MAILTO"]
    rows = []
    while True:
        r = requests.get("https://api.openalex.org/works", params=params, timeout=60)
        r.raise_for_status()
        d = r.json()
        for w in d["results"]:
            src = (w.get("primary_location") or {}).get("source") or {}
            rows.append({
                "openalex_id": w["id"], "doi": (w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
                "title": w.get("title"), "year": w.get("publication_year"), "journal": src.get("display_name"),
                "pmcid": (w.get("ids") or {}).get("pmcid"), "is_oa": w["open_access"].get("is_oa"),
                "oa_url": w["open_access"].get("oa_url"), "cited_by_count": w.get("cited_by_count"),
                "abstract": abstract(w.get("abstract_inverted_index")),
                "arxiv_id": arxiv_id(w.get("locations") or []), "query": f"{field}:{query}",
            })
        print(f"  {len(rows)}/{d['meta']['count']}", file=sys.stderr, flush=True)
        nxt = d["meta"].get("next_cursor")
        if not nxt or not d["results"] or (a.max and len(rows) >= a.max):
            return rows
        params["cursor"] = nxt
        time.sleep(0.2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="maks artikel per query (0 = semua)")
    ap.add_argument("--from-year", type=int, default=1985)
    ap.add_argument("--to-year", type=int, default=2026)
    a = ap.parse_args()
    rows = []
    for f, q in QUERIES:
        print(f, q, file=sys.stderr)
        rows += fetch(f, q, a)
    df = pd.DataFrame(rows)
    df["dkey"] = df["doi"].fillna(df["openalex_id"])
    df = df.sort_values("query", ascending=False).drop_duplicates("dkey").drop(columns="dkey")
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA / "works_openalex.csv", index=False)
    print(f"tersimpan {len(df)} artikel | OA {df.is_oa.sum()} | PMCID {df.pmcid.notna().sum()} | abstrak {df.abstract.notna().sum()}")


if __name__ == "__main__":
    main()
