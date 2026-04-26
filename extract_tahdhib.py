"""
Extraction Tahdhib al-Kamal → JSONL
Input  : data/tahdhib_pages.csv
Output : output/tahdhib_extracted.jsonl
         output/tahdhib_failed.json

Lancer : python extract_tahdhib.py
Reprendre après interruption : relancer la même commande (skip automatique)
"""

import csv
import json
import re
import time
import sys
import io
import requests
from pathlib import Path

# Ecrire dans stdout ET dans le fichier log simultanement
class TeeLogger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "a", encoding="utf-8")
    def write(self, msg):
        self.terminal.write(msg)
        self.log.write(msg)
        self.log.flush()
    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
csv.field_size_limit(10_000_000)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
OLLAMA_URL       = "http://localhost:11434"   # local sur RunPod
MODEL            = "qwen2.5:32b"
NUM_CTX          = 4096
TIMEOUT          = 600
MAX_RETRIES      = 3
DELAY_OK         = 0.3
DELAY_FAIL       = 10.0
CHECKPOINT_EVERY = 50

BASE_DIR      = Path(__file__).parent
INPUT_CSV     = BASE_DIR / "data/tahdhib_pages.csv"
OUTPUT_DIR    = BASE_DIR / "output"
OUTPUT_JSONL  = OUTPUT_DIR / "tahdhib_extracted.jsonl"
OUTPUT_FAILED = OUTPUT_DIR / "tahdhib_failed.json"
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """أنت أداة استخراج بيانات من كتاب تهذيب الكمال في أسماء الرجال.
مهمتك الوحيدة : استخراج المعلومات الموجودة في النص — لا تضف شيئاً من عندك أبداً.

قواعد صارمة:
١. استخرج فقط ما هو مكتوب صراحة في النص
٢. إذا لم يُذكر شيء في النص، اترك الحقل فارغاً [] أو ""
٣. لا تستنتج ولا تكمل ولا تخمن
٤. انقل الأسماء والأقوال كما هي في النص بالضبط
٥. الحكم على الراوي يجب أن يكون منسوباً لعالم محدد مذكور في النص
٦. النص قد يحتوي على ترجمة واحدة أو أكثر — استخرج كل ترجمة كاملة وجدتها"""

USER_TEMPLATE = """النص يحتوي على ترجمات رواة من تهذيب الكمال. كل ترجمة تبدأ بـ: رقم - كتب: اسم

استخرج كل الترجمات الكاملة الموجودة في النص بهذا الشكل JSON فقط:

{{
  "rawis": [
    {{
      "رقم_الترجمة": "الرقم العربي في بداية الترجمة",
      "الاسم_الكامل": "كما في النص",
      "الكنية": "إن وُجدت وإلا فارغ",
      "النسبة": "إن وُجدت وإلا فارغ",
      "الكتب": ["اختصارات الكتب بعد الرقم مباشرة"],
      "الشيوخ": ["أسماء بعد رَوَى عَن"],
      "التلاميذ": ["أسماء بعد رَوَى عَنه"],
      "أقوال_العلماء": [{{"العالم": "", "القول": ""}}],
      "وفاته": "إن ذُكر وإلا فارغ"
    }}
  ]
}}

النص (صفحتان متتاليتان):
{text}"""


def load_pages():
    pages = []
    with open(INPUT_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pages.append((int(row["page_num"] or 0), row["body_ar"].strip()))
    pages.sort()
    return [body for _, body in pages]


def clean(text):
    return re.sub(r"<[^>]+>", "", text)


def call_llm_streaming(text):
    prompt = USER_TEMPLATE.format(text=text)
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "format": "json",
            "stream": True,
            "options": {"temperature": 0.0, "num_ctx": NUM_CTX},
        },
        timeout=TIMEOUT,
        stream=True,
    )
    r.raise_for_status()

    content = ""
    for line in r.iter_lines():
        if line:
            chunk = json.loads(line)
            content += chunk.get("message", {}).get("content", "")
            if chunk.get("done"):
                break

    return json.loads(content)


def call_with_retry(text, page_idx):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return call_llm_streaming(text)
        except Exception as e:
            print(f"\n    ✗ Tentative {attempt}/{MAX_RETRIES} : {str(e)[:80]}")
            if attempt < MAX_RETRIES:
                time.sleep(DELAY_FAIL)
    raise Exception(f"Echec après {MAX_RETRIES} tentatives (pages {page_idx}-{page_idx+1})")


def load_already_done():
    done = set()
    if OUTPUT_JSONL.exists():
        with open(OUTPUT_JSONL, encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    raqm = obj.get("رقم_الترجمة", "")
                    if raqm:
                        done.add(str(raqm))
                except Exception:
                    pass
    return done


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Activer le log fichier
    LOG_FILE = OUTPUT_DIR / "extraction.log"
    sys.stdout = TeeLogger(LOG_FILE)

    print(f"\n{'='*60}", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] DEMARRAGE EXTRACTION", flush=True)
    print(f"  Modele  : {MODEL}", flush=True)
    print(f"  Log     : {LOG_FILE}", flush=True)
    print(f"  Output  : {OUTPUT_JSONL}", flush=True)
    print(f"{'='*60}\n", flush=True)

    print("Chargement des pages...")
    pages = load_pages()
    total_pages = len(pages)
    print(f"  {total_pages:,} pages chargées\n")

    already_done = load_already_done()
    if already_done:
        print(f"  {len(already_done)} rawis déjà extraits — reprise\n")

    failed = []
    if OUTPUT_FAILED.exists():
        with open(OUTPUT_FAILED, encoding="utf-8") as f:
            failed = json.load(f)

    out_file = open(OUTPUT_JSONL, "a", encoding="utf-8")
    processed_rawis = 0
    processed_windows = 0

    # Sliding window : page i + page i+1
    total_windows = total_pages - 1

    try:
        for i in range(0, total_pages - 1, 2):
            text = clean(pages[i] + " " + pages[i + 1])
            pct = (i + 1) / total_pages * 100
            ts = time.strftime("%H:%M:%S")

            print(f"\n[{ts} UTC] Pages {i+1}-{i+2} / {total_pages} ({pct:.1f}%)", flush=True)
            print(f"  Texte : {text[:120].strip()!r}", flush=True)
            print(f"  Envoi ({len(text)} chars)... en attente reponse", flush=True)

            t0 = time.time()
            try:
                result = call_with_retry(text, i)
                rawis = result.get("rawis", [])
                elapsed = time.time() - t0
                new_count = 0

                ts2 = time.strftime("%H:%M:%S")
                print(f"  [{ts2} UTC] OK {elapsed:.0f}s — {len(rawis)} rawi(s) detecte(s)", flush=True)

                for rawi in rawis:
                    raqm = str(rawi.get("رقم_الترجمة", ""))
                    nom = rawi.get("الاسم_الكامل", "?")
                    scholars = len(rawi.get("أقوال_العلماء", []))
                    shuyukh = len(rawi.get("الشيوخ", []))
                    talamidh = len(rawi.get("التلاميذ", []))

                    # Vrai rawi = codes livres courts (بخ م ق س د...) ET au moins 2 shuyukh
                    kutub = rawi.get("الكتب", [])
                    shuyukh_list = rawi.get("الشيوخ", [])
                    has_real_kutub = any(len(k.strip()) <= 4 for k in kutub)
                    has_shuyukh = len(shuyukh_list) >= 2
                    has_content = has_real_kutub or has_shuyukh

                    if not has_content:
                        print(f"  - IGNORE #{raqm} | {nom} (pas de كتب ni شيوخ — faux positif preface)", flush=True)
                    elif raqm and raqm not in already_done:
                        rawi["_pages"] = f"{i+1}-{i+2}"
                        out_file.write(json.dumps(rawi, ensure_ascii=False) + "\n")
                        out_file.flush()
                        already_done.add(raqm)
                        new_count += 1
                        processed_rawis += 1
                        print(f"  + SAUVEGARDE #{raqm} | {nom} | {shuyukh} shuyukh | {talamidh} talamidh | {scholars} avis scholars", flush=True)
                    elif raqm:
                        print(f"  ~ SKIP #{raqm} (deja extrait)", flush=True)

                if new_count == 0 and len(rawis) == 0:
                    print(f"  ! Aucun rawi complet trouve sur ces pages", flush=True)

                processed_windows += 1

            except Exception as e:
                elapsed = time.time() - t0
                print(f"  ! ECHEC apres {elapsed:.0f}s : {str(e)[:100]}", flush=True)
                failed.append({"pages": f"{i+1}-{i+2}", "error": str(e)})
                with open(OUTPUT_FAILED, "w", encoding="utf-8") as ff:
                    json.dump(failed, ff, ensure_ascii=False, indent=2)

            time.sleep(DELAY_OK)

            if (processed_windows + 1) % CHECKPOINT_EVERY == 0:
                ts = time.strftime("%H:%M:%S")
                print(f"\n[{ts}] === CHECKPOINT : {processed_rawis} rawis extraits, {len(failed)} echecs ===\n", flush=True)

    finally:
        out_file.close()

    print(f"\n{'='*60}")
    print(f"✓ {processed_rawis:,} rawis extraits → {OUTPUT_JSONL.name}")
    print(f"{'⚠' if failed else '✓'} {len(failed)} fenêtres échouées → {OUTPUT_FAILED.name}")


if __name__ == "__main__":
    main()
