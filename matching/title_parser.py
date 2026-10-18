"""Turn a messy store title into brand, model, RAM and storage.

'SAMSUNG Galaxy S24 5G (Onyx Black, 128 GB)  (8 GB RAM)'
   -> brand Samsung, model 'Galaxy S24', RAM 8, storage 128

Needs a list of known models (data/models.csv). Titles whose model is not in
the list, or that lack RAM or storage, go to a review queue instead of being guessed.
"""
import csv
import re

from rapidfuzz import fuzz, process

BRAND_ALIASES = {
    "samsung": "Samsung", "galaxy": "Samsung", "apple": "Apple", "iphone": "Apple",
    "oneplus": "OnePlus", "redmi": "Redmi", "xiaomi": "Xiaomi", "realme": "Realme",
    "vivo": "Vivo", "oppo": "Oppo", "google": "Google", "pixel": "Google",
    "nothing": "Nothing", "motorola": "Motorola", "moto": "Motorola",
    "iqoo": "iQOO", "poco": "Poco",
}
SPEC = re.compile(r"(?:\b(ram|storage|rom)\s*[:\-]?\s*)?(\d+)\s*(gb|tb)\b(?:\s*(ram|storage|rom|ssd))?", re.I)
AUTO_THRESHOLD = 0.8
# Words that mark a different, usually pricier, variant. If one appears in a title
# but is not part of the matched model name, the model is unknown, so we do not guess.
VARIANT_WORDS = {"ultra", "plus", "pro", "max", "fe", "lite", "mini", "prime", "edge",
                 "+", "pro+", "se", "neo", "turbo", "gt"}


def norm(text):
    text = text.lower().replace("one plus", "oneplus")
    text = re.sub(r"[(),\-/|:]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_models(path):
    models = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            models.setdefault(row["brand"], []).append(
                (row["model"], norm(row["model"]).split()))
    return models


def extract_specs(title):
    """Returns (ram_gb, storage_gb, title_without_specs)."""
    ram = storage = None
    unlabeled = []
    for m in SPEC.finditer(title):
        label = (m.group(4) or m.group(1) or "").lower()
        value = int(m.group(2)) * (1024 if m.group(3).lower() == "tb" else 1)
        if label == "ram":
            ram = value
        elif label in ("storage", "rom", "ssd"):
            storage = value
        else:
            unlabeled.append(value)
    unlabeled.sort()
    if ram is None and storage is None:
        if len(unlabeled) >= 2:
            ram, storage = unlabeled[0], unlabeled[-1]
        elif len(unlabeled) == 1 and unlabeled[0] >= 64:
            storage = unlabeled[0]          # one number: assume storage (RAM often missing)
    elif ram is None and unlabeled and unlabeled[0] <= 24:
        ram = unlabeled[0]
    elif storage is None and unlabeled:
        storage = unlabeled[-1]
    if ram is not None and not 1 <= ram <= 24:
        ram = None
    if storage is not None and storage < 16:
        storage = None
    cleaned = SPEC.sub(" ", title)
    return ram, storage, cleaned


def find_brand(tokens):
    keys = list(BRAND_ALIASES)
    for tok in tokens[:6]:
        if tok in BRAND_ALIASES:
            return BRAND_ALIASES[tok], 0
        if len(tok) >= 4:
            # typo tolerance, but the word must be nearly the same length
            near = [k for k in keys if abs(len(k) - len(tok)) <= 2]
            hit = process.extractOne(tok, near, scorer=fuzz.ratio, score_cutoff=80) if near else None
            if hit:
                return BRAND_ALIASES[hit[0]], 1
    return None, 0


def find_model(brand, tokens, models):
    best = None   # (token_count, -corrections, name, corrections)
    token_set = set(tokens)
    for name, mtokens in models.get(brand, []):
        corrections, ok = 0, True
        for mt in mtokens:
            if mt in token_set:
                continue
            if len(mt) >= 5 and any(fuzz.ratio(mt, t) >= 80 for t in tokens):
                corrections += 1
                continue
            ok = False
            break
        if ok:
            cand = (len(mtokens), -corrections, name, corrections)
            if best is None or cand[:2] > best[:2]:
                best = cand
    return (best[2], best[3], set(norm(best[2]).split())) if best else (None, 0, set())


def parse_title(title, models):
    ram, storage, cleaned = extract_specs(title)
    tokens = norm(cleaned).split()
    brand, c1 = find_brand(tokens)
    model, c2, model_tokens = find_model(brand, tokens, models) if brand else (None, 0, set())
    corrections = c1 + c2
    if model and {t for t in tokens if t not in model_tokens} & VARIANT_WORDS:
        model = None                        # unknown variant: send to review
    missing = [k for k, v in (("brand", brand), ("model", model),
                              ("ram", ram), ("storage", storage)) if v is None]
    return {"brand": brand, "model": model, "ram_gb": ram, "storage_gb": storage,
            "confidence": round(max(0.5, 1 - 0.1 * corrections), 2),
            "corrections": corrections, "missing": missing}
