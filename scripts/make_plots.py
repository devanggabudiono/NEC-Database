"""Figures for the NEC database and the biomass-derived carbon catalog.

Usage:  python make_plots.py

Output  figures/nec_systems.png               NEC evidence per material system
        biomass/figures/*.png                 biomass carbon catalog overview and NEC screening funnel
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BIO = ROOT / "biomass"
FIG_BIO = BIO / "figures"
FIG = ROOT / "figures"
plt.rcParams.update({"figure.dpi": 150, "savefig.bbox": "tight", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False})
EVID_COLORS = {"n_experiment": "#1b7837", "n_theory": "#2166ac", "n_indirect": "#f4a582", "n_disputed": "#b2182b"}


def split(s: pd.Series) -> pd.Series:
    return s.dropna().str.split("; ").explode()


def save(fig, path: Path) -> None:
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))


def nec_systems() -> None:
    s = pd.read_csv(ROOT / "database" / "nec_systems.csv")
    s["total"] = s[list(EVID_COLORS)].sum(axis=1)
    s = s.sort_values(["material_class", "total"], ascending=[False, True])
    fig, ax = plt.subplots(figsize=(7, 0.22 * len(s) + 1))
    left = np.zeros(len(s))
    for col, color in EVID_COLORS.items():
        ax.barh(range(len(s)), s[col], left=left, color=color, label=col[2:])
        left += s[col].to_numpy()
    ax.set_yticks(range(len(s)), [f"{n}  [{c}]" for n, c in zip(s.system, s.material_class)], fontsize=7)
    ax.set_xlabel("number of reports")
    ax.set_title(f"Negative electronic compressibility: evidence per material system ({len(s)} systems)")
    ax.legend(frameon=False, loc="lower right")
    save(fig, FIG / "nec_systems.png")


def per_year(m: pd.DataFrame) -> None:
    e = m[m.material_study & m.year.between(2000, 2026)]
    d = e[["year", "carbon_forms"]].assign(form=e.carbon_forms.str.split("; ")).explode("form", ignore_index=True)
    top = d.form.value_counts().index[:7]
    d["form"] = d.form.where(d.form.isin(top), "other")
    t = pd.crosstab(d.year.astype(int), d.form)[list(top) + ["other"]]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    t.plot.bar(stacked=True, ax=ax, width=0.85, colormap="tab10")
    ax.set_xlabel("")
    ax.set_ylabel("studies (a study can report several forms)")
    ax.set_title("Biomass-derived carbon: experimental studies per year by carbon form")
    ax.set_xticks(range(len(t)), [str(y) if y % 2 == 0 else "" for y in t.index], rotation=0)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    ax.annotate("2026: partial year", xy=(len(t) - 1, t.iloc[-1].sum()), xytext=(-90, 10),
                textcoords="offset points", fontsize=7, arrowprops={"arrowstyle": "-", "lw": 0.5})
    save(fig, FIG_BIO / "fig1_studies_per_year.png")


def top_precursors() -> None:
    p = pd.read_csv(BIO / "summary_precursors.csv")
    p = p[p.precursor != "biomass (unspecified)"].head(25).iloc[::-1]
    cats = sorted(p.category.unique())
    cmap = dict(zip(cats, plt.cm.tab20(np.linspace(0, 1, len(cats)))))
    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.barh(p.precursor, p.n_studies, color=[cmap[c] for c in p.category])
    ax.set_xlabel("experimental studies")
    ax.set_title("Top 25 named biomass precursors")
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=cmap[c]) for c in cats], cats, frameon=False, fontsize=7,
              loc="lower right")
    save(fig, FIG_BIO / "fig2_top_precursors.png")


def heatmap(path: Path, name: str, title: str, drop: tuple[str, ...] = ("none",)) -> None:
    t = pd.read_csv(BIO / path, index_col=0)
    t = t.drop(index=[i for i in drop if i in t.index], columns=[c for c in drop if c in t.columns])
    fig, ax = plt.subplots(figsize=(0.45 * t.shape[1] + 3, 0.35 * t.shape[0] + 2))
    im = ax.imshow(np.log10(t + 1), cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(t.shape[1]), t.columns, rotation=55, ha="right", fontsize=7)
    ax.set_yticks(range(t.shape[0]), t.index, fontsize=7)
    for (i, j), v in np.ndenumerate(t.to_numpy()):
        if v:
            ax.text(j, i, f"{v}", ha="center", va="center", fontsize=5.5,
                    color="white" if np.log10(v + 1) > 0.75 * np.log10(t.to_numpy().max() + 1) else "black")
    ax.spines[:].set_visible(False)
    fig.colorbar(im, ax=ax, label="log10(studies + 1)", shrink=0.7)
    ax.set_title(title)
    save(fig, FIG_BIO / name)


def bet_by_form(m: pd.DataFrame) -> None:
    e = m[m.material_study & m.bet_m2g.notna()]
    d = e[["bet_m2g"]].assign(form=e.carbon_forms.str.split("; ")).explode("form", ignore_index=True)
    order = d.groupby("form").bet_m2g.median().sort_values().index
    order = [f for f in order if (d.form == f).sum() >= 30]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.boxplot([d.bet_m2g[d.form == f] for f in order], orientation="horizontal", showfliers=False, widths=0.6)
    ax.set_yticks(range(1, len(order) + 1), [f"{f} (n={(d.form == f).sum()})" for f in order], fontsize=7)
    ax.set_xlabel("BET surface area (m²/g), headline value from abstract")
    ax.set_title("Surface area by carbon form (boxes: quartiles, whiskers: 1.5 IQR)")
    save(fig, FIG_BIO / "fig5_bet_by_form.png")


def bet_vs_capacitance(m: pd.DataFrame) -> None:
    e = m[m.material_study & m.applications.fillna("").str.contains("supercapacitor")
          & m.bet_m2g.notna() & m.spec_cap_Fg.between(20, 1000)]
    doped = e.dopants.fillna("").str.contains(r"\b[NSPBFO]\b")
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.scatter(e.bet_m2g[~doped], e.spec_cap_Fg[~doped], s=6, alpha=0.4, color="#7f7f7f", label=f"undoped / not stated (n={(~doped).sum()})")
    ax.scatter(e.bet_m2g[doped], e.spec_cap_Fg[doped], s=6, alpha=0.6, color="#d95f02", label=f"heteroatom-doped (n={doped.sum()})")
    ax.set_xlabel("BET surface area (m²/g)")
    ax.set_ylabel("specific capacitance (F/g)")
    r = np.corrcoef(e.bet_m2g, e.spec_cap_Fg)[0, 1]
    ax.set_title(f"Supercapacitor carbons from biomass: capacitance vs surface area (r = {r:.2f})")
    ax.legend(frameon=False, fontsize=7)
    save(fig, FIG_BIO / "fig6_bet_vs_capacitance.png")


def nec_funnel(m: pd.DataFrame) -> None:
    scr = pd.read_csv(BIO / "nec_screen.csv")
    works = pd.read_csv(ROOT / "data" / "biomass" / "works.csv", usecols=["work_id"])
    ft = pd.read_csv(ROOT / "data" / "biomass" / "nec_fulltext_works.csv", usecols=["pmcid"])
    strong = m.nec_flags.fillna("").str.contains("quantum capacitance|negative capacitance|compressibility|capacitance enhancement")
    steps = [("harvested works", len(works)), ("biomass-derived carbon (in scope)", len(m)),
             ("experimental material studies", int(m.material_study.sum())),
             ("NEC-adjacent term in abstract", int((m.nec_flags.fillna("") != "").sum())),
             ("QC / neg. capacitance / compressibility / enhancement", int(strong.sum())),
             ("full texts with an NEC term (separate search)", len(ft)), ("works curated by hand", len(scr)),
             ("quantum capacitance computed (DFT)", int((scr.verdict == "T-QC").sum())),
             ("NEC reported", int(scr.verdict.isin(["E", "T", "P"]).sum()))]
    labels, vals = zip(*steps)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    y = np.arange(len(vals))[::-1]
    colors = ["#4575b4"] * len(vals)
    colors[5], colors[-1] = "#74add1", "#d73027"  # full-text search runs in parallel to the abstract filter
    ax.barh(y, [max(v, 0.8) for v in vals], color=colors, log=True)
    for yi, v in zip(y, vals):
        ax.text(max(v, 0.8) * 1.15, yi, f"{v:,}", va="center", fontsize=8)
    ax.set_yticks(y, labels, fontsize=8)
    ax.set_xlim(0.5, len(works) * 6)
    ax.set_xlabel("works (log scale)")
    ax.set_title("Screening biomass-derived carbon for negative electronic compressibility")
    save(fig, FIG_BIO / "fig7_nec_screening_funnel.png")


def main() -> None:
    FIG.mkdir(exist_ok=True)
    FIG_BIO.mkdir(exist_ok=True)
    m = pd.read_csv(BIO / "biomass_carbon_materials.csv", dtype={"material_study": bool})
    m["year"] = pd.to_numeric(m.year, errors="coerce")
    nec_systems()
    per_year(m)
    top_precursors()
    heatmap("summary_category_form.csv", "fig3_category_vs_form.png", "Precursor category vs carbon form (experimental studies)")
    heatmap("summary_applications.csv", "fig4_form_vs_application.png", "Carbon form vs application (experimental studies)")
    bet_by_form(m)
    bet_vs_capacitance(m)
    nec_funnel(m)


if __name__ == "__main__":
    main()
