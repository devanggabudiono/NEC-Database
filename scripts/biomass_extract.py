"""Regex extraction of biomass-derived carbon materials from titles and abstracts.

Usage:  python biomass_extract.py

Input   data/biomass/works.csv          (from biomass_search.py)
Output  data/biomass/materials.csv      one row per work: precursor, carbon form, synthesis, doping,
                                        application, headline numbers, NEC-related flags
Rules
  - A work counts as a biomass carbon material when a precursor and a carbon form/process word appear in the
    same sentence or the neighbouring one (or both in the title).
  - Numbers are the largest value quoted in the abstract for each quantity, so they are headline values, not
    a full property table.
"""
from __future__ import annotations

import re
from multiprocessing import Pool
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "biomass"

# (canonical name, category, regex). Order matters only for readability; all matches are kept.
P = r"(?:s|es)?"
PRECURSORS = [
    # agricultural residues
    ("rice husk", "agricultural residue", rf"rice[- ]hu(?:sk|ll){P}"),
    ("rice straw", "agricultural residue", r"rice straw"),
    ("wheat straw/bran", "agricultural residue", r"wheat (?:straw|bran|husk)"),
    ("corn stalk/stover/cob", "agricultural residue", r"corn(?: |-)?(?:stalk|stover|cob|husk|straw|silk|stem|bract|leaves|leaf)s?|maize (?:straw|stalk|cob|stover)s?"),
    ("bagasse (sugarcane/other)", "agricultural residue", r"(?:sugar ?cane )?bagasse|sugarcane"),
    ("cotton stalk/linter", "agricultural residue", r"cotton (?:stalk|linter|seed hull)s?"),
    ("sorghum", "agricultural residue", r"sorghum"),
    ("soybean residue", "agricultural residue", r"soybean (?:straw|hull|pod|shell|residue|stalk|dreg|meal)s?|okara"),
    ("oil palm residue", "agricultural residue", r"(?:oil )?palm (?:kernel shell|shell|empty fruit bunch|frond|fiber|fibre|trunk|leaves|leaf)s?|empty fruit bunch"),
    ("cassava residue", "agricultural residue", r"cassava"),
    ("tobacco waste", "agricultural residue", r"tobacco (?:stem|stalk|waste|leaves|rob)s?"),
    ("hemp", "agricultural residue", r"hemp"),
    ("flax/jute/kenaf/sisal", "agricultural residue", r"flax|jute|kenaf|sisal|ramie"),
    ("sunflower residue", "agricultural residue", r"sunflower (?:seed shell|stalk|husk|head)s?"),
    ("rapeseed residue", "agricultural residue", r"rape(?:seed)? (?:straw|meal|shell|stalk)s?"),
    ("coffee waste", "food/beverage waste", r"(?:spent )?coffee (?:grounds?|husks?|residue|waste|silverskin|beans?)"),
    ("tea waste", "food/beverage waste", r"tea (?:waste|leaves|leaf|residue|seed shell)s?"),
    ("cocoa/cacao residue", "agricultural residue", r"coc(?:oa|ao) (?:pod|husk|shell|bean shell)s?"),
    ("grape residue", "food/beverage waste", r"grape (?:seed|pomace|marc|skin|stem)s?|vinasse"),
    ("olive residue", "food/beverage waste", r"olive (?:stone|pit|pomace|mill|kernel|tree pruning|leaves|husk)s?"),
    ("date palm residue", "agricultural residue", r"date (?:palm|seed|pit|stone)s?"),
    # nut and fruit shells/stones
    ("coconut shell/coir", "nut shell/fruit stone", r"coconut(?: shell| husk| coir| fiber| fibre| pith)?s?|coir"),
    ("walnut shell", "nut shell/fruit stone", r"walnut(?: shell)?s?"),
    ("almond shell", "nut shell/fruit stone", r"almond (?:shell|husk|skin)s?"),
    ("hazelnut shell", "nut shell/fruit stone", r"hazelnut(?: shell| husk)?s?"),
    ("pistachio shell", "nut shell/fruit stone", r"pistachio(?: shell| hull)?s?"),
    ("peanut shell", "nut shell/fruit stone", r"peanut(?: shell| hull| husk| skin)?s?"),
    ("other nut shells", "nut shell/fruit stone", r"(?:macadamia|cashew|chestnut|pecan|argan|pine nut|hickory|areca|betel|ginkgo)(?: nut)?(?: shell| husk)?s?|nut ?shells?"),
    ("fruit stones/seeds", "nut shell/fruit stone", r"(?:apricot|peach|cherry|plum|mango|tamarind|jujube|longan|lychee|litchi|avocado|loquat|jackfruit|durian|palm) (?:stone|pit|seed|kernel|shell)s?"),
    # fruit/vegetable peels
    ("citrus peel", "fruit/vegetable peel", r"(?:orange|citrus|lemon|lime|pomelo|grapefruit|mandarin|tangerine|shaddock)(?: peel| rind| skin| juice| pomace)s?"),
    ("banana peel/pseudostem", "fruit/vegetable peel", r"banana(?: peel| skin| pseudo-?stem| stem| leaves| leaf| fiber| fibre)?s?"),
    ("pomegranate peel", "fruit/vegetable peel", r"pomegranate(?: peel| husk| rind| seed)?s?"),
    ("other fruit peels", "fruit/vegetable peel", r"(?:watermelon|melon|pineapple|apple|mango|kiwi|durian|jackfruit|dragon fruit|pitaya|passion fruit|rambutan|mangosteen|papaya|lychee|longan) (?:peel|rind|skin|pomace|shell|crown)s?"),
    ("vegetable waste", "fruit/vegetable peel", r"(?:potato|onion|garlic|carrot|cabbage|pea|tomato|cucumber|pumpkin) (?:peel|skin|waste|pomace|stem|stalk|leaves|pod)s?"),
    # wood and forestry
    ("wood (generic)", "wood/forestry", r"(?:natural |waste |balsa |bass ?|lignocellulosic )?wood(?:y biomass| chips?| powder| waste| flour)?|timber"),
    ("pine", "wood/forestry", r"pine(?: cone| needle| bark| sawdust| wood| tree)?s?"),
    ("poplar/willow/birch/oak", "wood/forestry", r"poplar|willow|birch|oak|eucalyptus|beech|cedar|fir|spruce|paulownia|acacia|teak|mahogany"),
    ("bamboo", "wood/forestry", r"bamboo"),
    ("sawdust", "wood/forestry", r"saw ?dust"),
    ("bark", "wood/forestry", r"(?:tree )?bark"),
    # leaves, grasses, aquatic plants
    ("leaves (generic)", "leaves/grass/plant", r"(?:dead |fallen |dry |waste )?(?:tree |plant )?lea(?:f|ves)"),
    ("grass/reed", "leaves/grass/plant", r"(?:switch|elephant|napier|cogon|lemon|vetiver|alang-alang|bermuda|miscanthus)?grass(?:es)?|miscanthus|reeds?|cattail|typha|bulrush"),
    ("water hyacinth/aquatic plant", "leaves/grass/plant", r"water hyacinth|duckweed|lotus(?: leaf| leaves| stem| seedpod| root| seed)?|azolla|salvinia"),
    ("loofah/kapok/catkin", "leaves/grass/plant", r"lo(?:o|u)fah|luffa|kapok|catkin|platanus|plane tree|dandelion|cattail fiber"),
    ("cotton", "leaves/grass/plant", r"cotton(?! stalk| linter)"),
    ("seeds/pods (other plants)", "leaves/grass/plant", r"(?:lotus|sesame|pumpkin|sunflower|chia|flax|neem|moringa|jatropha|castor|karanja|mustard|cottonseed) (?:seed|pod|cake|husk|shell|meal)s?"),
    ("fungi/mushroom", "microbial/fungal", r"mushroom|fung(?:i|us|al)|mycelium|yeast|shiitake|enoki|pleurotus"),
    ("bacterial cellulose", "microbial/fungal", r"bacterial cellulose|nata de coco"),
    ("algae/seaweed", "algae/aquatic", r"(?:micro|macro)?alga(?:e|l)?|seaweed|kelp|spirulina|chlorella|enteromorpha|sargassum|ulva|laminaria|porphyra|diatom"),
    # animal-derived
    ("crustacean shell/chitin", "animal-derived", r"(?:crab|shrimp|prawn|lobster|crayfish|crawfish) (?:shell|waste|exoskeleton)s?|chitin"),
    ("chitosan", "isolated biopolymer", r"chitosan"),
    ("eggshell membrane/egg", "animal-derived", r"egg ?shell(?: membrane)?s?|egg (?:white|yolk)"),
    ("bone", "animal-derived", r"(?:animal |pig |cattle |chicken |fish |cow |bovine )?bones?"),
    ("hair/wool/feather", "animal-derived", r"(?:human |pig |dog |cat )?hair|wool|(?:chicken |duck )?feathers?|keratin"),
    ("silk/cocoon", "animal-derived", r"silk(?:worm)?(?: cocoon| fibroin)?|cocoons?|sericin"),
    ("fish scale/skin", "animal-derived", r"fish (?:scale|skin|waste|bone|gill)s?"),
    ("leather/gelatin/blood", "animal-derived", r"leather|gelatin|collagen|animal blood|pig blood|blood"),
    ("manure", "waste stream", r"(?:cow|cattle|pig|swine|chicken|poultry|horse|sheep|goat|dairy)? ?(?:manure|dung|litter)"),
    # isolated biopolymers and biomolecules
    ("lignin", "isolated biopolymer", r"(?:kraft |alkali |organosolv )?lignin(?:sulfonate|sulphonate)?s?"),
    ("cellulose/nanocellulose", "isolated biopolymer", r"(?:nano|micro)?cellulose(?: nanofibers?| nanocrystals?)?|cellulose acetate"),
    ("hemicellulose/xylan", "isolated biopolymer", r"hemicellulose|xylan|xylose"),
    ("starch", "isolated biopolymer", r"starch"),
    ("sugars (glucose/sucrose)", "isolated biopolymer", r"glucose|sucrose|fructose"),
    ("alginate/agar/carrageenan", "isolated biopolymer", r"alginate|agar(?:ose)?|carrageenan|pectin"),
    ("tannin", "isolated biopolymer", r"tannins?"),
    # waste streams
    ("food/kitchen waste", "waste stream", r"food waste|kitchen waste|food residue"),
    ("sewage sludge", "waste stream", r"(?:sewage |activated |paper |municipal )?sludge"),
    ("waste paper/pulp", "waste stream", r"waste paper|paper waste|cardboard|black liquor|pulp(?:ing)? (?:waste|residue|sludge)|newspaper"),
    ("cigarette butts", "waste stream", r"cigarette (?:butt|filter)s?"),
    ("distillers' grains/brewery waste", "waste stream", r"distillers'? grains?|spent grains?|brewer'?s? (?:spent )?grains?|brewery waste|vinasse"),
    ("municipal solid waste", "waste stream", r"municipal solid waste|MSW"),
    # generic
    ("biomass (unspecified)", "biomass (unspecified)", r"biomass|bio-?wastes?|agricultural (?:waste|residue|by-product)s?|agro-?(?:waste|residue|industrial waste)s?|lignocellulos(?:e|ic)"),
]
PREC_RE = [(n, c, re.compile(rf"\b(?:{r})\b", re.I)) for n, c, r in PRECURSORS]
# These words often mean something else (analyte, binder, soil input, "antifungal"), so they only count as a
# precursor when a carbon or derivation word sits within 60 characters.
AMBIGUOUS = {"sugars (glucose/sucrose)", "leather/gelatin/blood", "bone", "hair/wool/feather", "fungi/mushroom",
             "algae/aquatic", "cotton", "leaves (generic)", "grass/reed", "bark", "manure", "sewage sludge", "starch",
             "alginate/agar/carrageenan", "chitosan", "cellulose/nanocellulose", "hemicellulose/xylan", "tannin",
             "silk/cocoon", "eggshell membrane/egg", "wood (generic)", "pine", "poplar/willow/birch/oak", "algae/seaweed"}
NEAR = re.compile(r"derived|based|precursor|carbon source|carbon|char\b|biochar|hydrochar|pyroly|carboni[sz]|activat|graphen", re.I)
NOT_PREC = re.compile(r"carboxymethyl[- ]?cellulose|\bCMC\b|anti-?fungal|glucose (?:oxidase|sensor|detection|biosensor)|"
                      r"blood (?:glucose|sample|serum|cell)|bone (?:tissue|regeneration|repair)", re.I)

CARBON_FORMS = [
    ("activated carbon", r"activated carbons?|\bACs?\b"),
    ("hard carbon", r"hard carbons?|non-graphitizing carbon"),
    ("biochar", r"bio-?chars?"),
    ("hydrochar", r"hydro-?chars?"),
    ("carbon dots", r"carbon (?:quantum )?dots?|\bC(?:Q)?Ds\b|carbon nanodots?|graphene quantum dots?|\bGQDs\b"),
    ("graphene / graphene-like", r"graphene(?! quantum dots?)(?:[- ]like)?|few-layer graphene|laser-induced graphene|\bLIG\b|flash graphene"),
    ("graphitic carbon / graphite", r"graphiti[cz]\w*|graphite|turbostratic"),
    ("carbon nanosheets", r"carbon nano-?sheets?|2D carbon|two-dimensional carbon"),
    ("carbon nanotubes", r"carbon nanotubes?|\bCNTs?\b"),
    ("carbon nanofibers / fibers", r"carbon (?:nano)?fib(?:er|re)s?|\bCNFs?\b"),
    ("carbon aerogel / foam / sponge", r"carbon (?:aerogel|foam|sponge|monolith)s?|carbon cryogel"),
    ("carbon spheres", r"carbon (?:micro|nano)?spheres?"),
    ("porous carbon", r"(?:hierarchical(?:ly)?|micro|meso|macro|nano)?-?porous carbons?|\bHPCs?\b"),
    ("carbon (generic)", r"(?<!low-)(?<!low )carbon materials?|derived carbons?|carbonaceous materials?|carbonized|carbonised|carbonization|carbonisation|pyroly[sz]ed carbon|carbon electrodes?"),
]
FORM_RE = [(n, re.compile(r, re.I)) for n, r in CARBON_FORMS]

SYNTHESIS = [
    ("pyrolysis/carbonization", r"pyroly\w+|carboni[sz]\w+|calcin\w+"),
    ("hydrothermal", r"hydrothermal\w*|\bHTC\b|solvothermal"),
    ("chemical activation", r"(?:KOH|NaOH|ZnCl2|H3PO4|K2CO3|KHCO3|FeCl3|K2FeO4|CaCl2|MgCl2|KCl|NaCl|Na2CO3|KMnO4|H2SO4|HNO3)[- ]?activat\w+|activat\w+ (?:with|by|using) (?:KOH|NaOH|ZnCl2|H3PO4|K2CO3|KHCO3|FeCl3|K2FeO4)|chemical(?:ly)? activat\w+"),
    ("physical activation", r"(?:CO2|steam|physical(?:ly)?)[- ]activat\w+|activat\w+ (?:with|by|using|in) (?:CO2|steam|carbon dioxide)"),
    ("template", r"templat\w+"),
    ("microwave", r"microwave(?!\s+absor)"),
    ("flash Joule heating", r"flash (?:Joule )?heating|Joule heating|flash graphene"),
    ("laser", r"laser[- ](?:induced|scrib|irradiat|carboni)\w*"),
    ("catalytic graphitization", r"catalytic(?:ally)? graphiti\w+|(?:Fe|Ni|Co|K2FeO4)[- ]catalyz\w+ graphiti\w+"),
    ("ball milling", r"ball[- ]mill\w*"),
    ("freeze drying", r"freeze[- ]dr\w+|lyophili\w+"),
    ("electrospinning", r"electrospin\w*|electrospun"),
]
SYN_RE = [(n, re.compile(r, re.I)) for n, r in SYNTHESIS]
AGENT_RE = re.compile(r"\b(KOH|NaOH|ZnCl2|H3PO4|K2CO3|KHCO3|FeCl3|K2FeO4|CaCl2|MgCl2|Na2CO3|KMnO4|NaNH2|KHC8H4O4|C2K2O4|CO2|steam)\b")

APPLICATIONS = [
    ("supercapacitor", r"super-?capacit\w+|ultracapacit\w+|electric(?:al)? double[- ]layer capacit\w+|\bEDLCs?\b|specific capacitance|pseudocapacit\w+"),
    ("Li-ion battery", r"lithium[- ]ion batter\w+|\bLIBs?\b|li-ion"),
    ("Na-ion battery", r"sodium[- ]ion\w*|\bSIBs?\b|na-ion|sodium storage"),
    ("K-ion battery", r"potassium[- ]ion\w*|\bPIBs?\b|k-ion|potassium storage"),
    ("Li-S / metal-S battery", r"lithium[- ]sulfur|li-s batter\w+|\bLSBs?\b|sulfur host"),
    ("Zn-ion / hybrid capacitor", r"zinc[- ]ion\w*|zn-ion|hybrid capacitor|\bZHSCs?\b|\bZIHCs?\b"),
    ("electrocatalysis (ORR/OER/HER/CO2RR)", r"oxygen reduction|\bORR\b|oxygen evolution|\bOER\b|hydrogen evolution|\bHER\b|CO2 reduction|CO2RR|electrocataly\w+|fuel cells?|zinc[- ]air|metal[- ]air"),
    ("adsorption / water treatment", r"adsor\w+|remov\w+ of|wastewater|dye|heavy metals?|pollutants?|antibiotics?"),
    ("CO2 / gas capture", r"CO2 (?:capture|uptake|adsorption)|carbon capture|gas (?:storage|adsorption)|H2 storage|hydrogen storage|methane storage"),
    ("capacitive deionization", r"capacitive deioni[sz]ation|\bCDI\b|desalination"),
    ("photocatalysis", r"photocatal\w+|photodegrad\w+"),
    ("sensing", r"\bsensors?\b|sensing|detection|biosensor\w*|electrochemical detection"),
    ("fluorescence / bioimaging", r"fluoresc\w+|bioimaging|photoluminescen\w+|quantum yield"),
    ("microwave absorption / EMI", r"microwave absor\w+|electromagnetic (?:wave|interference|shielding)|\bEMI\b"),
    ("solar steam / thermal", r"solar (?:steam|evaporat\w+|vapor\w*|desalination)|photothermal|interfacial evaporation|thermal (?:management|conductivity)|phase change"),
    ("soil / agronomy", r"\bsoils?\b|crops?|fertili[sz]\w+|plant growth|seedlings?|amendment"),
    ("catalyst support / catalysis", r"catalyst supports?|heterogeneous catal\w+|catalytic (?:conversion|oxidation|reduction|degradation)"),
    ("biomedical", r"drug delivery|antibacterial|antimicrobial|wound|cancer|tumou?r|biocompatib\w+"),
    ("energy fuel (gasification/bio-oil)", r"bio-?oil|syngas|gasification|biofuel|torrefaction|combustion"),
]
APP_RE = [(n, re.compile(r, re.I)) for n, r in APPLICATIONS]

DOPE_RE = re.compile(r"((?:\b(?:[NSPBFO]|nitrogen|sulfur|sulphur|phosphorus|boron|fluorine|oxygen)\b(?:\s*,\s*|\s*/\s*|\s*-\s*|\s+and\s+)?){1,4})\s*-?\s*(?:co-?|tri-?|dual-?)?-?\s*dop(?:ed|ing)", re.I)
ELEM = {"n": "N", "nitrogen": "N", "s": "S", "sulfur": "S", "sulphur": "S", "p": "P", "phosphorus": "P",
        "b": "B", "boron": "B", "f": "F", "fluorine": "F", "o": "O", "oxygen": "O"}

# NEC-related electronic signatures worth a full-text look.
NEC_FLAGS = [
    ("quantum capacitance", r"quantum capacitance"),
    ("negative capacitance", r"negative (?:differential )?capacitance"),
    ("compressibility", r"(?:electron(?:ic)?|negative) compressibility"),
    ("capacitance enhancement", r"(?:anomalous|enhanced|giant|abnormal) (?:capacitance|capacitive)|capacitance enhancement"),
    ("density of states", r"density of states|\bDOS\b"),
    ("Fermi level / work function", r"fermi level|work function|kelvin probe|\bKPFM\b|\bUPS\b|ultraviolet photoelectron"),
    ("space-charge / Mott-Schottky", r"space[- ]charge (?:capacit\w+|layer)|mott[- ]schottky"),
    ("DFT", r"density functional theory|\bDFT\b|first[- ]principles|ab initio"),
]
NEC_RE = [(n, re.compile(r, re.I)) for n, r in NEC_FLAGS]

EXPERIMENT_RE = re.compile(r"\b(?:synthesi[sz]ed|prepared|fabricated|obtained|produced|derived|carboni[sz]ed|activated|pyroly[sz]ed|"
                           r"characteri[sz]ed|XRD|Raman|XPS|BET|SEM|TEM|FTIR|measured|exhibit\w*|deliver\w*|achiev\w*)\b", re.I)
REVIEW_RE = re.compile(r"\b(?:review|overview|perspective|progress in|advances in|recent developments|state of the art|roadmap|"
                       r"summari[sz]es?|this chapter|mini-review|bibliometric)\b", re.I)
NUM = r"(\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
PER_G = r"[\s·∙•⋅.]*(?:g\s*(?:\^\s*)?(?:-|−|–|⁻)\s*(?:1|¹)|/\s*g)\b"
BET_RE = re.compile(NUM + r"\s*m\s*(?:\^\s*)?(?:2|²)" + PER_G)
CAP_RE = re.compile(NUM + r"\s*F" + PER_G)
MAH_RE = re.compile(NUM + r"\s*mA\s*[·∙•⋅.]?\s*h" + PER_G)
IDIG_RE = re.compile(r"I\s*\(?\s*D\s*\)?\s*/\s*I\s*\(?\s*G\s*\)?[^0-9]{0,40}?(\d+\.\d+)")
COND_RE = re.compile(r"(\d+(?:\.\d+)?(?:\s*[×x]\s*10\s*\^?\s*[-−–]?\s*\d+)?)\s*S\s*(cm|m)\s*(?:-\s*1|−\s*1|–\s*1|⁻¹|\^\s*-?1)")
TEMP_RE = re.compile(r"(\d{3,4})\s*(?:°|º|˚|degrees?\s*)\s*C\b")
DERIVED_RE = re.compile(r"-derived|derived from|-based carbon|carbon (?:source|precursor)|as (?:the |a )?(?:carbon )?precursor", re.I)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")


def clean(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = t.replace(" ", " ").replace(" ", " ")
    t = re.sub(r"(?<=[A-Za-z)])\s*(?:_\{?|<sub>)\s*(\d+)\s*\}?", r"\1", t)
    return t


def num(s: str) -> float:
    return float(re.sub(r"[,\s]", "", s))


def maxnum(rx: re.Pattern, text: str, lo: float, hi: float) -> float | None:
    vals = [v for v in (num(m.group(1)) for m in rx.finditer(text)) if lo <= v <= hi]
    return max(vals) if vals else None


def cond(text: str) -> str | None:
    best = None
    for m in COND_RE.finditer(text):
        s = re.sub(r"\s+", "", m.group(1)).replace("−", "-").replace("–", "-")
        mm = re.match(r"([\d.]+)(?:[×x]10\^?(-?\d+))?", s)
        v = float(mm.group(1)) * 10 ** int(mm.group(2) or 0) * (0.01 if m.group(2) == "m" else 1)
        best = v if best is None else max(best, v)
    return None if best is None else f"{best:.3g}"


def found(rxs, text: str) -> list[str]:
    return [n for n, rx in rxs if rx.search(text)]


def precursor_hits(title: str, sents: list[str]) -> list[tuple[str, str]]:
    """Precursors that sit next to a carbon word: same sentence or the neighbouring one."""
    carbonish = [any(rx.search(s) for _, rx in FORM_RE) or bool(SYN_RE[0][1].search(s)) for s in sents]
    hits = {}
    for i, s in enumerate(sents):
        near = any(carbonish[max(0, i - 1): i + 2]) or (i == 0 and any(rx.search(title) for _, rx in FORM_RE))
        if not near:
            continue
        s2 = NOT_PREC.sub(" ", s)
        for n, c, rx in PREC_RE:
            for m in rx.finditer(s2):
                if n not in AMBIGUOUS or NEAR.search(s2[max(0, m.start() - 60): m.end() + 60].replace(m.group(0), " ")):
                    hits[n] = c
                    break
    return list(hits.items())


def row(w) -> dict:
    title, abst = clean(w.title), clean(w.abstract)
    text = f"{title}. {abst}"
    sents = [title] + SENT.split(abst) if abst else [title]
    prec = precursor_hits(title, sents)
    specific = [p for p in prec if p[1] != "biomass (unspecified)"]
    forms = found(FORM_RE, text)
    specific_forms = [f for f in forms if f != "carbon (generic)"]
    syn = found(SYN_RE, text)
    dop = sorted({ELEM[t.lower()] for m in DOPE_RE.finditer(text)
                  for t in re.findall(r"[A-Za-z]+", m.group(1)) if t.lower() in ELEM})
    if re.search(r"self-?dop(?:ed|ing)", text, re.I):
        dop.append("self-doped")
    apps = found(APP_RE, text)
    review = bool(re.search(r"review", w.pub_types or "", re.I)) or bool(REVIEW_RE.search(title)) or \
        bool(re.search(r"\b(?:this|the present) (?:review|chapter|perspective)\b", abst, re.I))
    exp = bool(EXPERIMENT_RE.search(abst))
    if not abst:
        exp = bool(re.search(r"\b(?:preparation|production|synthesis|fabrication|derived|from|activated|"
                             r"characteri[sz]ation|performance|carboni[sz]\w+|pyrolysis)\b", title, re.I))
    study = ("review" if review else "patent" if "Patent" in (w.pub_types or "") else
             "experimental" if exp else "theory/other" if abst else "unknown (no abstract)")
    temps = [int(t) for t in TEMP_RE.findall(text) if 300 <= int(t) <= 3200]
    nec = found(NEC_RE, text)
    snippet = None
    if nec:
        rx = dict(NEC_RE)[nec[0]]
        snippet = next((s.strip()[:300] for s in sents if rx.search(s)), None)
    # Carbon made from the biomass, not a biopolymer mixed with commercial CNT/graphene (chitosan/GO membranes etc.).
    made = {"pyrolysis/carbonization", "hydrothermal", "chemical activation", "physical activation", "flash Joule heating",
            "laser", "catalytic graphitization"} & set(syn) or \
        {"activated carbon", "hard carbon", "biochar", "hydrochar", "carbon dots", "porous carbon", "carbon nanosheets",
         "carbon aerogel / foam / sponge", "carbon spheres"} & set(forms) or DERIVED_RE.search(text)
    in_scope = bool(prec) and bool(forms) and bool(made)
    # Material study: an experimental paper that makes or characterises the carbon, not only a field trial with biochar.
    material_study = in_scope and study == "experimental" and bool(syn or specific_forms) and apps != ["soil / agronomy"]
    return {
        "work_id": w.work_id, "year": w.year, "title": title, "journal": w.journal, "doi": w.doi,
        "pmcid": w.pmcid, "is_oa": w.is_oa, "study_type": study, "in_scope": in_scope,
        "material_study": material_study,
        "precursors": "; ".join(n for n, _ in (specific or prec)),
        "precursor_categories": "; ".join(sorted({c for _, c in (specific or prec)})),
        "carbon_forms": "; ".join(specific_forms or forms),
        "synthesis": "; ".join(syn), "activation_agents": "; ".join(sorted(set(AGENT_RE.findall(text)))),
        "max_temp_C": max(temps) if temps else None, "dopants": "; ".join(dop),
        "applications": "; ".join(apps),
        "bet_m2g": maxnum(BET_RE, text, 1, 5000), "spec_cap_Fg": maxnum(CAP_RE, text, 1, 3000),
        "capacity_mAhg": maxnum(MAH_RE, text, 1, 5000), "id_ig": maxnum(IDIG_RE, text, 0.05, 5),
        "conductivity_S_cm": cond(text), "nec_flags": "; ".join(nec), "nec_snippet": snippet,
    }


def main() -> None:
    works = pd.read_csv(DATA / "works.csv", dtype=str)
    works[["title", "abstract", "pub_types"]] = works[["title", "abstract", "pub_types"]].fillna("")
    with Pool(8) as pool:
        out = pd.DataFrame(pool.map(row, [SimpleNamespace(**r) for r in works.to_dict("records")], chunksize=500))
    out.to_csv(DATA / "materials.csv", index=False)
    s = out[out.in_scope]
    print(f"works {len(out)} | in scope {len(s)} | material studies {out.material_study.sum()} | "
          f"NEC-flagged in scope {(s.nec_flags != '').sum()}")
    print(s.study_type.value_counts().to_string())


if __name__ == "__main__":
    main()
