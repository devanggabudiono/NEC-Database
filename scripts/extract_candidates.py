"""Ekstrak kandidat material NEC dari abstrak + teks penuh arXiv -> data/nec_candidates.csv, data/nec_materials.csv.

Pakai:  python extract_candidates.py
Berbasis aturan (regex + kamus). Material hanya dihitung bila muncul di kalimat yang sama atau
bertetangga (+-1 kalimat) dengan kata kunci NEC, supaya sebutan di pendahuluan/rujukan tidak terbawa.
Semua baris tetap perlu kurasi manual; kolom `confidence` membantu urutan pemeriksaan.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
FT = DATA / "fulltext"

NEC = re.compile(
    r"negative\s+(?:electron(?:ic)?\s+|inverse\s+|charge\s+|thermodynamic(?:al)?\s+)?compressibilit"
    r"|negative\s+quantum\s+capacitance|d\s*μ\s*/\s*dn\s*<\s*0|capacitance\s+enhancement"
    r"|negative\s+(?:density\s+of\s+states|thermodynamic\s+density\s+of\s+states)"
    r"|(?:inverse\s+)?compressibilit[^.]{0,80}(?:becomes?|turns?|is|are)\s+negative"
    r"|K\s*\^?\s*-\s*1[^.]{0,60}(?:becomes?|changes sign)",
    re.I,
)
# Konteks mekanik/biologis yang ikut terjaring frasa "negative compressibility".
MECH = re.compile(r"metamaterial|auxetic|lipid|membrane|foam|granular|bulk modulus|linear compressibility"
                  r"|negative thermal expansion|framework|elastic|mechanical|polymer|gel\b|origami", re.I)
ELEC = re.compile(r"electron|electronic|2DEG|2DHG|hole gas|carrier density|quantum capacitance|chemical potential"
                  r"|capacitance|Coulomb|exchange|correlat|Landau level|Fermi", re.I)
EXP = re.compile(r"\bwe (?:measure|observe|report|find experimental|demonstrate)|measured|experiment|ARPES"
                 r"|photoemission|capacitance measurement|single[- ]electron transistor|(?-i:\bSET\b)|penetration field"
                 r"|device|sample", re.I)
THEO = re.compile(r"\bwe (?:calculate|compute|propose|predict|show theoretically)|theor|Monte Carlo|Hubbard model"
                  r"|Hartree|DFT|density functional|mean[- ]field|numerical|model", re.I)

METHODS = {
    "capacitance": r"capacitance",
    "penetration_field": r"penetration field|field penetration",
    "SET_scanning": r"single[- ]electron transistor|(?-i:\bSET\b)",
    "ARPES": r"(?-i:ARPES)|photoemission",
    "core_level_XPS": r"core[- ]level|(?-i:XPS)",
    "transport_SdH": r"Shubnikov|(?-i:SdH)|magnetotransport",
    "Kelvin_probe": r"Kelvin probe|KPFM",
    "optical_exciton": r"exciton sensing|optical sensing|reflectance|photoluminescence",
    "STM_STS": r"(?-i:\bSTM\b|\bSTS\b)|scanning tunneling",
    "theory_numerics": r"Monte Carlo|Hartree|DFT|density functional|exact diagonali|mean[- ]field",
}

# Nama kanonik -> (kelas, regex). Urutan spesifik dulu agar "bilayer graphene" tidak cuma jadi "graphene".
MATERIALS: list[tuple[str, str, str]] = [
    ("GaAs/AlGaAs bilayer 2DEG", "III-V heterostructure", r"(?:double|bilayer|double[- ]layer|double quantum well)[^.]{0,60}(?:GaAs|2DEG|electron (?:gas|system))|GaAs[^.]{0,40}(?:double|bilayer) (?:quantum well|layer)"),
    ("GaAs 2D hole gas", "III-V heterostructure", r"(?:hole gas|2DHG|two-dimensional hole|holes?)[^.]{0,40}GaAs|GaAs[^.]{0,40}(?:hole gas|2DHG|holes)"),
    ("GaAs/AlGaAs 2DEG", "III-V heterostructure", r"GaAs|AlGaAs|Al\s*x\s*Ga"),
    ("InAs / InGaAs", "III-V heterostructure", r"(?-i:\bInAs\b|InGaAs)"),
    ("AlGaN/GaN 2DEG", "III-N heterostructure", r"AlGaN|(?-i:\bGaN\b)"),
    ("ZnO/MgZnO 2DEG", "oxide heterostructure", r"MgZnO|ZnO"),
    ("Si MOSFET / Si inversion layer", "Si/Ge", r"Si[- ]MOSFET|silicon MOSFET|Si inversion|silicon inversion|Si/SiO|(?-i:\bMOSFET)"),
    ("Si/SiGe quantum well", "Si/Ge", r"SiGe|Si/Si\s*Ge"),
    ("HgTe / CdTe quantum well", "II-VI heterostructure", r"HgTe|CdTe"),
    ("twisted bilayer graphene", "graphene", r"twisted bilayer graphene|magic[- ]angle|(?-i:\bTBG\b)|twisted (?:double|trilayer|multilayer) graphene"),
    ("bilayer graphene", "graphene", r"bilayer graphene|bi-layer graphene|(?-i:\bBLG\b)"),
    ("trilayer / multilayer graphene", "graphene", r"(?:trilayer|tri-layer|rhombohedral|few[- ]layer|multilayer) graphene|graphite"),
    ("monolayer graphene", "graphene", r"(?:single|mono)[- ]?layer graphene|graphene"),
    ("carbon nanotube", "1D carbon", r"carbon nanotube|(?-i:\bCNTs?\b)|nanotube"),
    ("hexagonal boron nitride (h-BN)", "2D insulator", r"(?-i:\bh-?BN\b)|hexagonal boron nitride|boron nitride"),
    ("MoS2", "TMD", r"MoS\s*2|molybdenum disulfide"),
    ("WSe2", "TMD", r"WSe\s*2|tungsten diselenide"),
    ("WS2", "TMD", r"WS\s*2\b|tungsten disulfide"),
    ("MoSe2", "TMD", r"MoSe\s*2"),
    ("MoTe2", "TMD", r"MoTe\s*2"),
    ("black phosphorus", "2D semiconductor", r"black phosphorus|phosphorene"),
    ("InSe", "2D semiconductor", r"(?-i:\bInSe\b)"),
    ("LaAlO3/SrTiO3 interface", "oxide interface", r"LaAlO\s*3|(?-i:LAO/STO|\bLAO\b)"),
    ("LaTiO3/SrTiO3 interface", "oxide interface", r"LaTiO\s*3"),
    ("SrTiO3 (surface / other)", "oxide", r"SrTiO\s*3|(?-i:\bSTO\b)"),
    ("KTaO3", "oxide", r"KTaO\s*3"),
    ("Sr3(Ir,Ru)2O7 / iridates", "oxide (5d)", r"Sr\s*3\s*\(?(?:Ir|Ru)|Ir\s*2\s*O\s*7|Sr\s*2\s*IrO|iridate"),
    ("ruthenates", "oxide (4d)", r"ruthenate|Ca\s*2\s*RuO|Sr\s*2\s*RuO"),
    ("cuprates", "oxide (cuprate)", r"cuprate|La\s*2\s*-\s*x\s*Sr|YBa\s*2\s*Cu|Bi\s*2\s*Sr\s*2|CuO\s*2"),
    ("manganites", "oxide (manganite)", r"manganite|LaMnO|La\s*1\s*-\s*x\s*(?:Sr|Ca)\s*x\s*MnO"),
    ("MXene (Ti carbonitride)", "MXene", r"(?-i:MXene)|Ti\s*3\s*C\s*N|titanium carbonitride"),
    ("Ta2NiSe5", "excitonic insulator", r"Ta\s*2\s*NiSe\s*5"),
    ("Bi2Se3 / Bi2Te3 (TI surface)", "topological insulator", r"Bi\s*2\s*Se\s*3|Bi\s*2\s*Te\s*3|topological insulator"),
    ("alkali metal fluid (expanded metal)", "metal", r"expand(?:ed|ing) metal|alkali metal|\bcesium\b|\brubidium\b"),
    ("semiconductor nanowire", "nanowire", r"nanowire"),
    ("quantum dot", "quantum dot", r"quantum dots?"),
    ("ionic liquid / electrolyte (EDL)", "electrolyte", r"ionic liquid|electrolyte|double layer capacit"),
    # Model/sistem generik: bukan material, tapi relevan untuk melacak kerangka teori.
    ("[model] 2D electron gas (generic)", "model", r"two[- ]dimensional electron (?:gas|system)|\b2DEG\b|jellium|electron gas"),
    ("[model] Hubbard / correlated lattice", "model", r"Hubbard|t-J model|Kondo lattice|double[- ]exchange|Anderson lattice"),
    ("[model] Wigner crystal / low-density", "model", r"Wigner"),
]
MAT_RE = [(n, c, re.compile(p, re.I)) for n, c, p in MATERIALS]
MAT_BY_NAME = {n: r for n, _, r in MAT_RE}
# Hindari dobel-hitung: bila nama spesifik cocok, buang nama umum di grup yang sama.
SUPERSEDES = {
    "GaAs/AlGaAs 2DEG": {"GaAs/AlGaAs bilayer 2DEG", "GaAs 2D hole gas"},
    "monolayer graphene": {"bilayer graphene", "twisted bilayer graphene", "trilayer / multilayer graphene"},
    "SrTiO3 (surface / other)": {"LaAlO3/SrTiO3 interface", "LaTiO3/SrTiO3 interface"},
}
DENS = re.compile(r"\d+(?:\.\d+)?\s*(?:×|x|\*|\\times)\s*10\s*\^?\s*\{?\s*[−-]?\d+\s*\}?\s*cm\s*\^?\s*\{?\s*[−-]\s*2", re.I)
TEMP = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:mK|K)\b")


def clean(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)
    # Abstrak sering membawa LaTeX/subscript: LaAlO(3), LaAlO$_3$, \ensuremath{...}.
    text = re.sub(r"\\(?:ensuremath|mathrm|mathit|text|rm)\b", "", text)
    text = re.sub(r"(?<=[A-Za-z)])\s*(?:\$?_\{?|\(|<sub>)\s*(\d+(?:\.\d+)?|x|y|δ)\s*(?:\)|</sub>|\}?\$?)", r"\1", text)
    text = re.sub(r"[{}$]", "", text)
    return " ".join(text.split())


def strip_refs(text: str) -> str:
    # Potong di heading rujukan terakhir (setelah 40% dokumen) agar judul rujukan tidak dihitung.
    hits = [m.start() for m in re.finditer(r"\b(?:References|REFERENCES|Bibliography)\b", text)]
    hits = [h for h in hits if h > 0.4 * len(text)]
    return text[: hits[-1]] if hits else text


def sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text)


def nec_windows(text: str) -> list[str]:
    s = sentences(text)
    return [" ".join(s[max(0, i - 1): i + 2]) for i, x in enumerate(s) if NEC.search(x)]


# Material yang biasanya hanya substrat/dielektrik/spacer; dibuang bila ada material aktif lain.
SUPPORT = {"hexagonal boron nitride (h-BN)"}


def materials_in(text: str) -> set[str]:
    found = {n for n, _, r in MAT_RE if r.search(text)}
    for general, specific in SUPERSEDES.items():
        if general in found and found & specific:
            found.discard(general)
    active = {m for m in found if not m.startswith("[model]")} - SUPPORT
    return found - SUPPORT if active else found


def fulltext(arxiv_id) -> str | None:
    if not isinstance(arxiv_id, str):
        return None
    p = FT / f"{arxiv_id.replace('/', '_')}.txt"
    return strip_refs(clean(p.read_text(errors="ignore"))) if p.exists() else None


def main() -> None:
    works = pd.read_csv(DATA / "works.csv")
    cls = {n: c for n, c, _ in MATERIALS}
    rows = []
    for w in works.itertuples():
        head = clean(f"{w.title or ''}. {w.abstract if isinstance(w.abstract, str) else ''}")
        ft = fulltext(w.arxiv_id)
        head_win, ft_win = nec_windows(head), nec_windows(ft) if ft else []
        ctx = " ".join(head_win + ft_win) or head
        mech, elec = len(MECH.findall(ctx)), len(ELEC.findall(ctx))
        domain = "electronic" if elec > mech else ("mechanical/other" if mech else "unclear")
        nexp, nth = len(EXP.findall(head + " " + ctx)), len(THEO.findall(head + " " + ctx))
        study = "experiment" if nexp > 1.5 * nth else ("theory" if nth > 1.5 * nexp else "mixed")
        methods = [k for k, p in METHODS.items() if re.search(p, ctx, re.I)]
        dens = sorted(set(m.group(0) for m in DENS.finditer(ctx)))[:6]
        temps = sorted(set(m.group(0) for m in TEMP.finditer(" ".join(head_win + ft_win))))[:6]
        # Material dari jendela NEC; bila abstrak menyatakan NEC, judul+abstrak dianggap konteks NEC juga.
        mats_head = materials_in(" ".join(head_win)) | (materials_in(head) if head_win else set())
        mats_ft = materials_in(" ".join(ft_win)) - mats_head
        base = {
            "work_id": w.work_id, "doi": w.doi, "arxiv_id": w.arxiv_id, "year": w.year, "title": w.title,
            "journal": w.journal, "domain": domain, "study_type": study, "nec_in_abstract": bool(head_win),
            "nec_in_fulltext": bool(ft_win), "has_fulltext": ft is not None, "methods": ";".join(methods),
            "densities_cm2": " | ".join(dens), "temperatures": " | ".join(temps),
        }
        if not mats_head and not mats_ft and (head_win or ft_win):
            # Fallback: NEC disebut tapi material tidak di kalimat yang sama; ambil dari judul/abstrak/awal teks.
            mats_ft = materials_in(head + " " + (ft or "")[: len(ft or "") // 3]) - {n for n in cls if n.startswith("[model]")}
            fallback = True
        else:
            fallback = False
        if not mats_head and not mats_ft:
            rows.append(base | {"material": None, "material_class": None, "confidence": "none",
                                "evidence": (head_win or ft_win or [""])[0][:600]})
            continue
        for m, src in [(m, "abstract") for m in mats_head] + [(m, "fulltext") for m in mats_ft]:
            win = head_win if src == "abstract" else ft_win
            mre = MAT_BY_NAME[m]
            same = [x for x in win if mre.search(x)]
            if src == "abstract" and any(NEC.search(s) and mre.search(s) for x in head_win for s in sentences(x)):
                conf = "high"
            elif src == "abstract" or (src == "fulltext" and len(same) >= 2):
                conf = "medium"
            else:
                conf = "low"
            if fallback or domain == "mechanical/other":
                conf = "low"
            rows.append(base | {"material": m, "material_class": cls[m], "confidence": conf,
                                "evidence": (same or win or [""])[0][:600]})
    cand = pd.DataFrame(rows)
    cand["needs_review"] = True
    cand.to_csv(DATA / "nec_candidates.csv", index=False)

    ok = cand[cand.material.notna() & (cand.domain == "electronic") & cand.confidence.isin(["high", "medium"])]
    summ = ok.groupby("material").agg(
        material_class=("material_class", "first"), n_works=("work_id", "nunique"),
        n_high=("confidence", lambda s: (s == "high").sum()),
        n_experiment=("study_type", lambda s: (s == "experiment").sum()),
        n_theory=("study_type", lambda s: (s == "theory").sum()),
        first_year=("year", "min"), last_year=("year", "max"),
        methods=("methods", lambda s: ";".join(sorted({m for x in s.dropna() for m in x.split(";") if m}))),
        refs=("doi", lambda s: " ; ".join(s.dropna().astype(str).unique()[:12])),
    ).sort_values(["n_works", "n_high"], ascending=False)
    summ.to_csv(DATA / "nec_materials.csv")
    print(f"karya {len(works)} | baris kandidat {len(cand)} | domain: {cand.drop_duplicates('work_id').domain.value_counts().to_dict()}")
    print(f"confidence: {cand.confidence.value_counts().to_dict()}")
    print(summ[["material_class", "n_works", "n_high", "n_experiment", "n_theory", "first_year", "last_year"]].to_string())


if __name__ == "__main__":
    main()
