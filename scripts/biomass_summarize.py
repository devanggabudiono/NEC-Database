"""Publish the biomass-derived carbon catalog and its summaries.

Usage:  python biomass_summarize.py

Input   data/biomass/materials.csv     (from biomass_extract.py, local only)
        biomass/nec_screen.csv         (manual NEC screening, edited by hand)
Output  biomass/biomass_carbon_materials.csv   in-scope works with extracted fields (no abstract text)
        biomass/summary_precursors.csv         one row per precursor
        biomass/summary_category_form.csv      precursor category x carbon form (experimental studies)
        biomass/summary_applications.csv       carbon form x application (experimental studies)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from biomass_extract import PRECURSORS

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "biomass" / "materials.csv"
OUT = ROOT / "biomass"
KEEP = ["work_id", "year", "title", "journal", "doi", "pmcid", "study_type", "material_study", "precursors",
        "precursor_categories", "carbon_forms", "synthesis", "activation_agents", "max_temp_C", "dopants",
        "applications", "bet_m2g", "spec_cap_Fg", "capacity_mAhg", "id_ig", "conductivity_S_cm", "nec_flags"]


def top(s: pd.Series, n: int = 3) -> str:
    v = s.dropna().str.split("; ").explode()
    return "; ".join(f"{k} ({c})" for k, c in v[v != ""].value_counts().head(n).items())


def main() -> None:
    m = pd.read_csv(SRC, dtype=str)
    m = m[m.in_scope == "True"].copy()
    for c in ("bet_m2g", "spec_cap_Fg", "capacity_mAhg", "id_ig"):
        m[c] = pd.to_numeric(m[c])
    m["year"] = pd.to_numeric(m.year, errors="coerce").astype("Int64")
    m["material_study"] = m.material_study == "True"
    OUT.mkdir(exist_ok=True)
    m.sort_values(["year", "work_id"])[KEEP].to_csv(OUT / "biomass_carbon_materials.csv", index=False)

    exp = m[m.material_study]
    long = exp.assign(precursor=exp.precursors.str.split("; ")).explode("precursor")
    cat = {n: c for n, c, _ in PRECURSORS}
    summ = long.groupby("precursor").agg(
        n_studies=("work_id", "nunique"), first_year=("year", "min"), last_year=("year", "max"),
        top_carbon_forms=("carbon_forms", top), top_applications=("applications", top),
        top_dopants=("dopants", top), n_with_bet=("bet_m2g", "count"),
        median_bet_m2g=("bet_m2g", "median"), max_bet_m2g=("bet_m2g", "max"),
        median_spec_cap_Fg=("spec_cap_Fg", "median"), max_spec_cap_Fg=("spec_cap_Fg", "max"),
        max_capacity_mAhg=("capacity_mAhg", "max"),
        n_nec_related_terms=("nec_flags", lambda s: int(s.fillna("").str.contains("quantum capacitance|negative capacitance|compressibility").sum())),
    ).reset_index()
    summ.insert(1, "category", summ.precursor.map(cat))
    summ.sort_values("n_studies", ascending=False).round(1).to_csv(OUT / "summary_precursors.csv", index=False)

    def cross(a: str, b: str) -> pd.DataFrame:
        d = exp[["work_id", a, b]].copy()
        for c in (a, b):
            d[c] = d[c].fillna("none").str.split("; ")
            d = d.explode(c, ignore_index=True)
        t = pd.crosstab(d[a], d[b])
        return t.loc[t.sum(axis=1).sort_values(ascending=False).index, t.sum().sort_values(ascending=False).index]

    cross("precursor_categories", "carbon_forms").to_csv(OUT / "summary_category_form.csv")
    cross("carbon_forms", "applications").to_csv(OUT / "summary_applications.csv")
    print(f"in scope {len(m)} | experimental material studies {len(exp)} | precursors {len(summ)}")


if __name__ == "__main__":
    main()
