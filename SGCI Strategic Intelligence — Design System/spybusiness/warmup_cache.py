"""
Script de préchauffage du cache Q5 pour toutes les banques.
Lance directement les appels Groq sans passer par Flask.
"""
import sys, os, json, hashlib, time, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "dash_app"))

# Charger .env
BACK_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "BACK")
with open(os.path.join(BACK_DIR, ".env"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            if k.strip() and v.strip():
                os.environ.setdefault(k.strip(), v.strip())

import db
from cb_axes import AXES, AXE_COLORS, AXE_ICONS, prefilter_gaps, group_by_axe

CACHE_FILE = os.path.join(HERE, "cb_analyses_cache.json")

def load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def groq_call(prompt, cache_key, cache, max_tokens=1000):
    if cache_key in cache and cache[cache_key]:
        print(f"    [cache] {cache_key[-16:]}")
        return cache[cache_key]

    groq_keys = [k for k in [
        os.getenv("GROQ_API_KEY_11",""), os.getenv("GROQ_API_KEY_12",""),
        os.getenv("GROQ_API_KEY_9",""),  os.getenv("GROQ_API_KEY_10",""),
        os.getenv("GROQ_API_KEY_8",""),  os.getenv("GROQ_API_KEY_5",""),
        os.getenv("GROQ_API_KEY_6",""),  os.getenv("GROQ_API_KEY_7",""),
        os.getenv("GROQ_API_KEY",""),    os.getenv("GROQ_API_KEY_2",""),
        os.getenv("GROQ_API_KEY_3",""),  os.getenv("GROQ_API_KEY_4",""),
    ] if k]

    from groq import Groq
    for key in groq_keys:
        try:
            client = Groq(api_key=key)
            resp = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=0.3, reasoning_effort="low",
            )
            result = resp.choices[0].message.content.strip()
            cache[cache_key] = result
            save_cache(cache)
            time.sleep(2)  # RPM respect
            return result
        except Exception as e:
            print(f"    key err: {str(e)[:60]}")
            time.sleep(2)
            continue
    return None

_OCR_CONCAT = re.compile(r'[a-zàâçéèêëîïôùûü][A-ZÀÂÇÉÈÊËÎÏÔÙÛÜ]')
def ocr_ok(p):
    lib = p.get("libelle", "")
    return not (len(lib) > 30 and _OCR_CONCAT.search(lib))

def extract_gaps(analyse):
    gaps = []
    in_section = False
    in_synth = False
    for line in (analyse or "").splitlines():
        line = line.strip()
        up = line.upper()
        if "GAPS" in up and ("CONFIRM" in up or ":" in line):
            in_section = True; in_synth = False; continue
        if "SYNTH" in up:
            in_section = False; in_synth = True; continue
        if in_section and (line.startswith("•") or line.startswith("-")):
            name = line.lstrip("•- ⚠").split("—")[0].split(":")[0].strip()
            if name and len(name) >= 4:
                gaps.append(name)
    if not gaps and analyse:
        in_synth = False
        for line in analyse.splitlines():
            line = line.strip()
            if "SYNTH" in line.upper():
                in_synth = True; continue
            if not in_synth and (line.startswith("•") or line.startswith("-")):
                name = line.lstrip("•- ⚠").split("—")[0].split(":")[0].strip()
                if name and len(name) >= 4:
                    gaps.append(name)
    return gaps

def process_bank(banque, segment="Particuliers", annee=2026, semestre="S1"):
    print(f"\n{'='*50}")
    print(f"  {banque} — {segment} {annee} {semestre}")
    print(f"{'='*50}")

    cache = load_cache()
    all_data = db.cb_libelles_tous(annee, semestre, segment)
    sgci = [p for p in all_data.get("SGCI", []) if ocr_ok(p)]
    bank_prods = [p for p in all_data.get(banque, []) if ocr_ok(p)]

    if not bank_prods:
        print(f"  Aucun produit pour {banque}")
        return

    cands = prefilter_gaps(bank_prods, sgci, cutoff=0.70)
    cand_by_axe = group_by_axe(cands)
    sgci_by_axe  = group_by_axe(sgci)

    print(f"  {len(bank_prods)} produits -> {len(cands)} candidats")

    total_gaps = 0
    for axe_id in range(1, 9):
        axe_cands = cand_by_axe.get(axe_id, [])
        if not axe_cands:
            continue

        axe_sgci = sgci_by_axe.get(axe_id, [])
        cands_txt = "\n".join(
            f"  - {p['libelle']}"
            + (" [GRATUIT]" if p.get("est_gratuit") else
               f" [{p['montant']:,.0f} F]" if p.get("montant", 0) > 0 else "")
            for p in axe_cands[:35]
        )
        sgci_txt = " | ".join(p["libelle"] for p in axe_sgci[:30]) or "(aucun)"
        hash_key  = hashlib.md5((cands_txt + sgci_txt + banque).encode()).hexdigest()[:8]
        cache_key = f"q5_axe{axe_id}_{banque}_v3_{segment}_{hash_key}"

        # Skip si déjà en cache
        if cache_key in cache and cache[cache_key]:
            gaps = extract_gaps(cache[cache_key])
            print(f"  Axe {axe_id} [{AXES[axe_id]}]: {len(gaps)} gaps (cache)")
            total_gaps += len(gaps)
            continue

        prompt = f"""Tu es un analyste bancaire expert du marché ivoirien (UEMOA), segment {segment}.

AXE : {AXES[axe_id]}

Produits de {banque} sans équivalent évident chez SGCI (pré-filtrés) :
{cands_txt}

Ce que SGCI propose dans cet axe :
{sgci_txt}

MISSION : Parmi ces produits de {banque}, lesquels représentent un VRAI manque chez SGCI (absent fonctionnellement, même sous un nom différent) ?

RÈGLES :
✅ Confirme un gap seulement si SGCI n'a VRAIMENT rien d'équivalent dans cet axe
✅ Si SGCI a un produit similaire sous un nom différent -> signale [⚠ SGCI a peut-être l'équivalent]
✅ Sois critique : un virement générique n'est pas un gap si SGCI propose des virements

FORMAT :
GAPS CONFIRMÉS :
• [Nom exact du produit] — [5 mots max : ce que SGCI n'a pas]
• …

SYNTHÈSE RISQUE (2-3 phrases) : Ces gaps représentent-ils un VRAI danger pour SGCI sur cet axe ? SGCI est-elle globalement forte ou vulnérable ici ? Sur quels profils clients {banque} peut-elle vraiment mordre ?"""

        print(f"  Axe {axe_id} [{AXES[axe_id]}]: {len(axe_cands)} candidats -> appel Groq...")
        cache = load_cache()  # recharger en cas de modif concurrente
        analyse = groq_call(prompt, cache_key, cache)
        gaps = extract_gaps(analyse)
        print(f"    -> {len(gaps)} gaps confirmés")
        total_gaps += len(gaps)

    print(f"\n  TOTAL {banque}: {total_gaps} gaps")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--annee", type=int, default=2026)
    parser.add_argument("--semestre", default="S1")
    parser.add_argument("--segment", default="Particuliers")
    parser.add_argument("banks", nargs="*", default=["BACI","BICICI","BNI","ECOBANK","NSIA","SIB"])
    args = parser.parse_args()
    for bank in args.banks:
        process_bank(bank, segment=args.segment, annee=args.annee, semestre=args.semestre)
    print("\nCache warmup terminé.")
