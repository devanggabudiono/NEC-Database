"""Full-text check of biomass-derived carbon papers for NEC signatures (Europe PMC open-access XML).

Usage:  python biomass_fulltext.py

Runs Europe PMC full-text queries (biomass carbon AND an NEC-related term), caches the XML in
data/biomass/fulltext/, and writes every sentence that carries an NEC term to
data/biomass/nec_fulltext_snippets.csv for manual curation.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from lxml import etree

DATA = Path(__file__).resolve().parents[1] / "data" / "biomass"
FT = DATA / "fulltext"
API = "https://www.ebi.ac.uk/europepmc/webservices/rest"
BIOMASS = ('("biomass-derived" OR "biomass derived" OR "derived from biomass" OR "biomass-based" OR biowaste OR '
           '"bio-waste" OR "agricultural waste" OR lignocellulosic OR "waste-derived" OR "peel-derived" OR '
           '"shell-derived" OR "husk-derived" OR "wood-derived" OR "lignin-derived" OR "cellulose-derived" OR '
           '"chitosan-derived" OR biochar)')
CARBON = '("activated carbon" OR "porous carbon" OR "hard carbon" OR biochar OR graphene OR "carbon dots" OR "derived carbon" OR carbonization)'
TERMS = {
    "quantum capacitance": '"quantum capacitance"',
    "negative capacitance": '"negative capacitance"',
    "compressibility": '"electronic compressibility" OR "electron compressibility" OR "negative compressibility" OR "compressibility of the electron"',
    "capacitance enhancement": '"capacitance enhancement" OR "anomalous capacitance" OR "abnormal capacitance" OR "capacitance anomaly"',
    "density of states": '"density of states" AND (capacitance OR "Fermi level")',
}
SNIP = re.compile(r"quantum capacitance|negative (?:differential )?capacitance|(?:electron(?:ic)?|negative) compressibility|"
                  r"compressibility of the electron|capacitance (?:enhancement|anomaly)|(?:anomalous|abnormal) capacitance|"
                  r"density of states|\bDOS\b", re.I)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def search(term: str) -> list[dict]:
    q = f"{BIOMASS} AND {CARBON} AND ({TERMS[term]}) AND OPEN_ACCESS:y AND IN_EPMC:y"
    params = {"query": q, "format": "json", "resultType": "lite", "pageSize": 1000, "cursorMark": "*"}
    out = []
    while True:
        d = requests.get(f"{API}/search", params=params, timeout=120).json()
        out += [{"pmcid": r.get("pmcid"), "doi": (r.get("doi") or "").lower() or None, "title": r.get("title"),
                 "year": r.get("pubYear"), "journal": r.get("journalTitle"), "term": term}
                for r in d["resultList"]["result"] if r.get("pmcid")]
        if not d["resultList"]["result"] or d.get("nextCursorMark") in (None, params["cursorMark"]):
            return out
        params["cursorMark"] = d["nextCursorMark"]


def fulltext(pmcid: str) -> str | None:
    f = FT / f"{pmcid}.txt"
    if f.exists():
        return f.read_text() or None
    r = requests.get(f"{API}/{pmcid}/fullTextXML", timeout=120)
    time.sleep(0.3)
    if r.status_code != 200:
        f.write_text("")
        return None
    root = etree.fromstring(r.content)
    for bad in root.iter("ref-list", "xref", "table-wrap", "fig"):
        if bad.tag == "xref":
            bad.text = ""
        else:
            bad.getparent().remove(bad)
    body = " ".join(" ".join(p.itertext()) for p in root.iter("p", "title", "abstract"))
    body = re.sub(r"\s+", " ", body)
    f.write_text(body)
    return body


def main() -> None:
    FT.mkdir(parents=True, exist_ok=True)
    hits = pd.DataFrame([h for t in TERMS for h in search(t)])
    print(hits.term.value_counts().to_string(), file=sys.stderr)
    works = hits.groupby("pmcid").agg({"doi": "first", "title": "first", "year": "first", "journal": "first",
                                      "term": lambda s: "; ".join(sorted(set(s)))}).reset_index()
    rows = []
    for i, w in enumerate(works.itertuples(), 1):
        text = fulltext(w.pmcid)
        print(f"  {i}/{len(works)} {w.pmcid} {'ok' if text else 'no text'}", file=sys.stderr, flush=True)
        if not text:
            continue
        for s in SENT.split(text):
            if SNIP.search(s):
                rows.append({"pmcid": w.pmcid, "doi": w.doi, "year": w.year, "title": w.title, "journal": w.journal,
                             "query_terms": w.term, "term": SNIP.search(s).group(0).lower(), "sentence": s[:600]})
    out = pd.DataFrame(rows)
    out.to_csv(DATA / "nec_fulltext_snippets.csv", index=False)
    works.to_csv(DATA / "nec_fulltext_works.csv", index=False)
    print(f"works {len(works)} | with snippets {out.pmcid.nunique()} | snippets {len(out)}")
    print(out.term.value_counts().to_string())


if __name__ == "__main__":
    main()
