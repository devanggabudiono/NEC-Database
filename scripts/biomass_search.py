"""Harvest articles on biomass-derived carbon materials -> data/biomass/works_{epmc,s2}.csv and works.csv.

Usage:  python biomass_search.py [--source epmc s2] [--max 0]

Sources (no API key needed):
  epmc  Europe PMC REST search, title+abstract fields, abstracts included
  s2    Semantic Scholar bulk search (title+abstract), abstracts when the publisher allows
OpenAlex is left out because its anonymous daily budget is shared per IP and runs out quickly.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parents[1] / "data" / "biomass"

# Biomass side: generic words plus the common precursors (shells, husks, peels, wood, algae, waste).
SOURCE_TERMS = ["biomass", "biowaste", "bio-waste", "agricultural waste", "agro-waste", "agricultural residue",
                "lignocellulosic", "waste-derived", "food waste", "husk", "peel", "bagasse", "lignin", "cellulose",
                "chitosan", "chitin", "wood-derived", "bamboo", "coconut", "sawdust", "straw", "seaweed", "algae",
                "nutshell", "shell-derived", "leaves-derived", "fruit-derived", "plant-derived", "bio-derived",
                "biomass-derived", "sustainable carbon"]
# Carbon side: material forms and the processing words that signal a carbon product.
CARBON_TERMS = ["activated carbon", "porous carbon", "hard carbon", "biochar", "hydrochar", "carbon dots",
                "carbon quantum dots", "graphene", "graphitic carbon", "carbon nanosheets", "carbon nanotubes",
                "carbon nanofibers", "carbon aerogel", "carbon fiber", "carbon spheres", "carbonization",
                "carbonized", "derived carbon", "carbon material", "pyrolytic carbon", "turbostratic"]


def epmc_query() -> str:
    a = " OR ".join(f'ABSTRACT:"{t}" OR TITLE:"{t}"' for t in SOURCE_TERMS)
    b = " OR ".join(f'ABSTRACT:"{t}" OR TITLE:"{t}"' for t in CARBON_TERMS)
    return f"({a}) AND ({b})"


def s2_query() -> str:
    q = lambda t: f'"{t}"' if " " in t or "-" in t else t
    return f'({" | ".join(map(q, SOURCE_TERMS))}) + ({" | ".join(map(q, CARBON_TERMS))})'


def get(url: str, params: dict, tries: int = 8) -> dict:
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code}, retry", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  {e}, retry", file=sys.stderr)
        time.sleep(min(60, 5 * 2 ** i))
    raise RuntimeError(f"gave up on {url}")


def epmc(a) -> pd.DataFrame:
    params = {"query": epmc_query(), "format": "json", "resultType": "core", "pageSize": 1000, "cursorMark": "*"}
    rows = []
    while True:
        d = get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params)
        for w in d["resultList"]["result"]:
            rows.append({
                "doi": (w.get("doi") or "").lower() or None, "title": w.get("title"), "year": w.get("pubYear"),
                "journal": ((w.get("journalInfo") or {}).get("journal") or {}).get("title") or w.get("bookOrReportDetails", {}).get("publisher"),
                "pub_types": "; ".join((w.get("pubTypeList") or {}).get("pubType", [])),
                "abstract": re.sub(r"<[^>]+>", " ", w.get("abstractText") or "") or None,
                "pmid": w.get("pmid"), "pmcid": w.get("pmcid"), "is_oa": w.get("isOpenAccess") == "Y",
                "epmc_id": f"{w.get('source')}:{w.get('id')}", "source": "epmc",
            })
        print(f"  epmc {len(rows)}/{d['hitCount']}", file=sys.stderr, flush=True)
        nxt = d.get("nextCursorMark")
        if not d["resultList"]["result"] or nxt == params["cursorMark"] or (a.max and len(rows) >= a.max):
            return pd.DataFrame(rows)
        params["cursorMark"] = nxt


def s2(a) -> pd.DataFrame:
    params = {"query": s2_query(), "fields": "title,abstract,year,externalIds,venue,publicationTypes,openAccessPdf"}
    rows = []
    while True:
        d = get("https://api.semanticscholar.org/graph/v1/paper/search/bulk", params)
        for w in d.get("data", []):
            ids = w.get("externalIds") or {}
            rows.append({
                "doi": (ids.get("DOI") or "").lower() or None, "title": w.get("title"), "year": w.get("year"),
                "journal": w.get("venue") or None, "pub_types": "; ".join(w.get("publicationTypes") or []),
                "abstract": w.get("abstract"), "pmid": ids.get("PubMed"),
                "pmcid": f"PMC{ids['PubMedCentral']}" if ids.get("PubMedCentral") else None,
                "is_oa": bool((w.get("openAccessPdf") or {}).get("url")), "s2_id": w.get("paperId"),
                "arxiv_id": ids.get("ArXiv"), "source": "s2",
            })
        print(f"  s2 {len(rows)}/{d.get('total')}", file=sys.stderr, flush=True)
        if not d.get("token") or (a.max and len(rows) >= a.max):
            return pd.DataFrame(rows)
        params["token"] = d["token"]
        time.sleep(1.5)


def merge() -> pd.DataFrame:
    parts = [pd.read_csv(p, dtype=str) for p in (DATA / "works_epmc.csv", DATA / "works_s2.csv") if p.exists()]
    df = pd.concat(parts, ignore_index=True)
    df["tkey"] = df.title.fillna("").str.lower().str.replace(r"[^a-z0-9]", "", regex=True).str[:120]
    df["has_abs"] = df.abstract.notna()
    # Prefer the record that carries an abstract, then Europe PMC (it has PMCIDs for full text).
    df = df.sort_values(["has_abs", "source"], ascending=[False, True])
    filled = df.groupby(df.doi.fillna(df.tkey)).agg(
        {c: "first" for c in df.columns if c not in ("doi",)} | {"source": lambda s: "+".join(sorted(set(s)))})
    filled["doi"] = filled.index.where(filled.index.str.startswith("10."), None)
    filled = filled.reset_index(drop=True)
    filled = filled[filled.tkey.str.len() > 0].drop_duplicates("tkey")
    filled = filled.sort_values(["year", "title"]).reset_index(drop=True)
    filled.insert(0, "work_id", [f"B{i + 1:05d}" for i in range(len(filled))])
    return filled.drop(columns=["tkey", "has_abs"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", nargs="*", default=["epmc", "s2"])
    ap.add_argument("--max", type=int, default=0, help="max works per source (0 = all)")
    ap.add_argument("--merge-only", action="store_true")
    a = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    if not a.merge_only:
        for name in a.source:
            df = {"epmc": epmc, "s2": s2}[name](a)
            df.to_csv(DATA / f"works_{name}.csv", index=False)
            print(f"{name}: {len(df)} works, abstracts {df.abstract.notna().sum()}")
    df = merge()
    df.to_csv(DATA / "works.csv", index=False)
    print(f"merged: {len(df)} works | abstracts {df.abstract.notna().sum()} | PMCID {df.pmcid.notna().sum()}")


if __name__ == "__main__":
    main()
