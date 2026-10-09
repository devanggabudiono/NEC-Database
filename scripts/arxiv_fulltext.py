"""Unduh PDF arXiv untuk karya di data/works.csv dan ekstrak teks -> data/fulltext/<id>.txt.

Pakai:  python arxiv_fulltext.py [--limit 0]
Hanya versi arXiv (open access). Cache: PDF tidak diunduh ulang bila .txt sudah ada.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pymupdf
import pandas as pd
import requests

DATA = Path(__file__).resolve().parents[1] / "data"
FT = DATA / "fulltext"


def fname(arxiv_id: str) -> str:
    return arxiv_id.replace("/", "_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    ids = pd.read_csv(DATA / "works.csv")["arxiv_id"].dropna().unique().tolist()
    ids = ids[: a.limit] if a.limit else ids
    FT.mkdir(parents=True, exist_ok=True)
    status = []
    for i, aid in enumerate(ids):
        txt = FT / f"{fname(aid)}.txt"
        if txt.exists():
            status.append({"arxiv_id": aid, "status": "cached"})
            continue
        try:
            r = requests.get(f"https://arxiv.org/pdf/{aid}", timeout=120,
                             headers={"User-Agent": "nec-lit-harvest (research; mailto via OPENALEX_MAILTO)"})
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                status.append({"arxiv_id": aid, "status": f"http_{r.status_code}"})
                continue
            with pymupdf.open(stream=r.content, filetype="pdf") as doc:
                txt.write_text("\n".join(p.get_text() for p in doc))
            status.append({"arxiv_id": aid, "status": "ok"})
        except Exception as e:  # PDF rusak atau timeout; catat lalu lanjut
            status.append({"arxiv_id": aid, "status": f"error:{type(e).__name__}"})
        print(f"{i + 1}/{len(ids)} {aid} {status[-1]['status']}", file=sys.stderr, flush=True)
        time.sleep(3)
    df = pd.DataFrame(status)
    df.to_csv(DATA / "fulltext_status.csv", index=False)
    print(df.status.value_counts().to_string())


if __name__ == "__main__":
    main()
