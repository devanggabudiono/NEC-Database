"""Gabung hasil OpenAlex + arXiv, dedupe DOI lalu arXiv id -> data/works.csv.

Pakai:  python merge_works.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    oa = pd.read_csv(DATA / "works_openalex.csv").assign(source="openalex")
    ax = pd.read_csv(DATA / "works_arxiv.csv").assign(source="arxiv")
    for df in (oa, ax):
        df["arxiv_id"] = df["arxiv_id"].astype("string").str.replace(r"v\d+$", "", regex=True)
    df = pd.concat([oa, ax], ignore_index=True)
    # Isi DOI/abstrak yang kosong dari baris pasangan dengan arXiv id yang sama.
    for col in ("doi", "abstract", "journal"):
        df[col] = df[col].fillna(df.groupby("arxiv_id")[col].transform("first"))
    df["key"] = df["doi"].fillna("arxiv:" + df["arxiv_id"]).fillna(df["openalex_id"])
    agg = {c: "first" for c in df.columns if c not in ("key", "source", "query")}
    agg |= {"source": lambda s: "+".join(sorted(set(s))), "query": lambda s: " | ".join(sorted(set(s)))}
    out = df.groupby("key", sort=False).agg(agg).reset_index()
    # Satu arXiv id bisa muncul di dua DOI (preprint + versi jurnal); pertahankan yang ber-DOI jurnal.
    has = out["arxiv_id"].notna()
    out = pd.concat([out[~has], out[has].sort_values("journal", na_position="last").drop_duplicates("arxiv_id")])
    # Preprint dan versi jurnal kadang punya DOI berbeda tanpa arXiv id bersama; dedupe juga lewat judul.
    out["tkey"] = out["title"].fillna("").str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    out = pd.concat([out[out.tkey == ""], out[out.tkey != ""].sort_values("journal", na_position="last")
                     .drop_duplicates("tkey")]).drop(columns="tkey")
    out = out.sort_values(["year", "title"]).reset_index(drop=True)
    out.insert(0, "work_id", [f"W{i:04d}" for i in range(len(out))])
    out.to_csv(DATA / "works.csv", index=False)
    print(f"{len(out)} karya unik | dengan arXiv {out.arxiv_id.notna().sum()} | abstrak {out.abstract.notna().sum()}")
    print(out.source.value_counts().to_string())


if __name__ == "__main__":
    main()
