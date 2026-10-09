"""Build the NEC database from the manual curation file.

Usage:  python scripts/build_database.py

Input   curation/nec_curation.csv   one row per screened work (source of truth, edit by hand)
Output  database/nec_entries.csv     one row per (work, material) with NEC evidence
        database/nec_systems.csv     one row per material system, evidence counted
        database/nec_candidates_unverified.csv   strong candidates whose text could not be checked
        database/nec_database.json   systems with their entries nested

Verdict codes in the curation file:
  E   NEC reported experimentally for this material
  T   NEC calculated or predicted for this specific material
  P   NEC proposed as an interpretation (indirect evidence)
  D   disputed or not observed (claim refuted, or NEC looked for and absent)
  M   generic theoretical model (Hubbard, jellium, 2DEG), not a specific material
  R   review or perspective
  X   NEC only mentioned in introduction or references
  N   not electronic NEC (mechanical, biological, astrophysical, cold atoms, ferroelectric negative capacitance)
  DUP duplicate of another work (preprint, APS abstract, cover)
  U   strong candidate from title, full text not accessible
  NT  no text available, not checked (most likely X)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "curation" / "nec_curation.csv"
OUT = ROOT / "database"
EVIDENCE = {"E": "experiment", "T": "theory", "P": "indirect", "D": "disputed"}
ENTRY_COLS = ["entry_id", "system", "material", "material_class", "evidence", "method", "regime",
              "year", "doi", "arxiv_id", "openalex_id", "title", "journal", "note", "work_id"]


def system_name(material: pd.Series) -> pd.Series:
    # "monolayer graphene (Ag adatoms)" -> "monolayer graphene"; nested parentheses allowed.
    return material.str.replace(r"\s+\([^()]*(?:\([^()]*\)[^()]*)*\)$", "", regex=True).str.strip()


def ref(row) -> str:
    if isinstance(row.doi, str):
        return f"doi:{row.doi}"
    return f"arXiv:{row.arxiv_id}" if isinstance(row.arxiv_id, str) else f"openalex:{row.openalex_id}"


def main() -> None:
    cur = pd.read_csv(CURATION, dtype=str)
    cur["year"] = cur["year"].astype(int)
    OUT.mkdir(exist_ok=True)

    ent = cur[cur.verdict.isin(EVIDENCE)].copy()
    ent["evidence"] = ent.verdict.map(EVIDENCE)
    ent["system"] = system_name(ent.material)
    ent = ent.sort_values(["material_class", "system", "year", "work_id"]).reset_index(drop=True)
    ent["entry_id"] = [f"NEC-{i + 1:04d}" for i in range(len(ent))]
    ent[ENTRY_COLS].to_csv(OUT / "nec_entries.csv", index=False)

    ent["ref"] = ent.apply(ref, axis=1)
    count = lambda kind: ("evidence", lambda s: int((s == kind).sum()))
    sysdf = ent.groupby(["material_class", "system"]).agg(
        n_experiment=count("experiment"), n_theory=count("theory"),
        n_indirect=count("indirect"), n_disputed=count("disputed"),
        first_year=("year", "min"), last_year=("year", "max"),
        methods=("method", lambda s: "; ".join(sorted(set(s.dropna())))),
        regimes=("regime", lambda s: "; ".join(sorted(set(s.dropna())))),
        refs=("ref", lambda s: " ; ".join(s)),
    ).reset_index()
    # Status per system: contested when refutations match the experimental reports, otherwise the strongest evidence.
    sysdf["status"] = sysdf.apply(
        lambda r: "contested" if r.n_experiment and r.n_disputed >= r.n_experiment
        else "experimental" if r.n_experiment else "theoretical" if r.n_theory
        else "indirect" if r.n_indirect else "disputed", axis=1)
    sysdf = sysdf.sort_values(["material_class", "n_experiment", "n_theory"], ascending=[True, False, False])
    sysdf.to_csv(OUT / "nec_systems.csv", index=False)

    cand = cur[cur.verdict == "U"][["work_id", "material", "material_class", "note", "year", "doi", "arxiv_id",
                                     "openalex_id", "title", "journal"]].sort_values("year")
    cand.to_csv(OUT / "nec_candidates_unverified.csv", index=False)

    systems = []
    for (cls, name), g in ent.groupby(["material_class", "system"], sort=True):
        s = sysdf[(sysdf.material_class == cls) & (sysdf.system == name)].iloc[0]
        systems.append({
            "system": name, "material_class": cls, "status": s.status,
            "counts": {k: int(s[f"n_{k}"]) for k in ("experiment", "theory", "indirect", "disputed")},
            "entries": [
                {k: (None if pd.isna(v) else v) for k, v in e.items()}
                for e in g[[c for c in ENTRY_COLS if c not in ("system", "material_class")]]
                .astype(object).to_dict("records")
            ],
        })
    meta = {
        "name": "NEC-Database",
        "description": "Materials reported to show negative electronic compressibility (NEC), curated from the literature",
        "built": date.today().isoformat(),
        "screened_works": int(len(cur)),
        "verdict_counts": cur.verdict.value_counts().to_dict(),
        "systems": systems,
    }
    (OUT / "nec_database.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))

    print(f"screened {len(cur)} works | entries {len(ent)} | systems {len(sysdf)} | unverified candidates {len(cand)}")
    print(sysdf.status.value_counts().to_string())


if __name__ == "__main__":
    main()
