"""
Extraction Tahdhib al-Kamal → JSONL
Input  : data/tahdhib_pages.csv
Output : output/tahdhib_extracted.jsonl
         output/tahdhib_failed.json

Lancer : python3 extract_tahdhib.py
Reprendre apres interruption : relancer la meme commande (skip automatique)
"""

import csv
import json
import re
import time
import sys
import io
import requests
from pathlib import Path


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
OLLAMA_URL       = "http://localhost:11434"
MODEL            = "qwen2.5:32b"
NUM_CTX          = 8192
TIMEOUT          = 600
MAX_RETRIES      = 3
DELAY_FAIL       = 10.0
CHECKPOINT_EVERY = 50

BASE_DIR      = Path(__file__).parent
INPUT_CSV     = BASE_DIR / "data/tahdhib_pages.csv"
OUTPUT_DIR    = BASE_DIR / "output"
OUTPUT_JSONL  = OUTPUT_DIR / "tahdhib_extracted.jsonl"
OUTPUT_FAILED = OUTPUT_DIR / "tahdhib_failed.json"
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """أنت أداة استخراج بيانات من كتاب تهذيب الكمال في أسماء الرجال للمزي.

كل ترجمة راوٍ في هذا الكتاب تبدأ بهذا الشكل:
  [رقم] - [اختصارات كتب] : [اسم الراوي]

ثم تذكر:
  - شيوخه : بعد عبارة "رَوَى عَن" أو "روى عن"
  - تلاميذه : بعد عبارة "رَوَى عَنه" أو "روى عنه"
  - أقوال العلماء فيه : بعد "قال فلان: ..."
  - وفاته : تاريخ الوفاة إن ذُكر

مهمتك :
١. إذا كان النص يحتوي على ترجمات رواة → استخرجها بالكامل
٢. إذا كان النص مقدمة أو تمهيد أو سيرة أو غير ذلك → أرجع {"rawis": []}
٣. استخرج فقط ما هو مكتوب في النص — لا تضف ولا تخمن"""

USER_TEMPLATE = """هل يحتوي هذا النص على ترجمات رواة من تهذيب الكمال؟
إذا نعم، استخرجها. إذا لا، أرجع {"rawis": []}.

أرجع JSON فقط بهذا الشكل:
{
  "rawis": [
    {
      "رقم_الترجمة": "الرقم كما في النص",
      "الاسم_الكامل": "كما في النص",
      "الكنية": "إن وُجدت وإلا فارغ",
      "النسبة": "إن وُجدت وإلا فارغ",
      "الكتب": ["اختصارات الكتب فقط مثل بخ م س ق د ت"],
      "الشيوخ": ["أسماء بعد روى عن"],
      "التلاميذ": ["أسماء بعد روى عنه"],
      "أقوال_العلماء": [{"العالم": "اسمه", "القول": "نص قوله بالضبط"}],
      "وفاته": "نص الوفاة إن ذُكر"
    }
  ]
}

النص:
{text}"""


def load_context():
    ctx = ""
    for fname in ["tahdhib_kamal.md", "schema.md"]:
        p = BASE_DIR / "context" / fname
        if p.exists():
            ctx += p.read_text(encoding="utf-8") + "\n\n"
    return ctx.strip()


def load_pages():
    pages = []
    with open(INPUT_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pages.append((int(row["page_num"] or 0), row["body_ar"].strip()))
    pages.sort()
    return [body for _, body in pages]


def clean(text):
    return re.sub(r"<[^>]+>", "", text)


def call_llm(text, context):
    system = SYSTEM_PROMPT + "\n\n---\n\n" + context
    prompt = USER_TEMPLATE.format(text=text)
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
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
            try:
                chunk = json.loads(line)
            except Exception as e:
                print(f"    DEBUG ligne brute : {repr(line[:200])}", flush=True)
                raise e
            if not isinstance(chunk, dict):
                print(f"    DEBUG chunk pas dict : {repr(chunk)[:100]}", flush=True)
                raise Exception(f"chunk inattendu : {repr(chunk)[:80]}")
            content += chunk.get("message", {}).get("content", "")
            if chunk.get("done"):
                break

    try:
        result = json.loads(content)
    except Exception as je:
        print(f"    DEBUG content brut : {repr(content[:200])}", flush=True)
        raise je
    if not isinstance(result, dict):
        print(f"    DEBUG result type={type(result)} val={repr(result)[:100]}", flush=True)
        return {"rawis": []}
    return result


def call_with_retry(text, context, page_idx):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return call_llm(text, context)
        except Exception as e:
            print(f"    ! Tentative {attempt}/{MAX_RETRIES} echouee : {str(e)[:80]}", flush=True)
            if attempt < MAX_RETRIES:
                time.sleep(DELAY_FAIL)
    raise Exception(f"Echec apres {MAX_RETRIES} tentatives (pages {page_idx}-{page_idx+1})")


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
    LOG_FILE = OUTPUT_DIR / "extraction.log"
    sys.stdout = TeeLogger(LOG_FILE)

    print(f"\n{'='*60}", flush=True)
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')} UTC] DEMARRAGE", flush=True)
    print(f"  Modele : {MODEL} | Contexte : {NUM_CTX} tokens", flush=True)
    print(f"{'='*60}\n", flush=True)

    context = load_context()
    print(f"  Contexte charge : {len(context)} chars depuis context/", flush=True)

    pages = load_pages()
    total_pages = len(pages)
    print(f"  {total_pages:,} pages chargees", flush=True)

    already_done = load_already_done()
    print(f"  {len(already_done)} rawis deja extraits — reprise si > 0\n", flush=True)

    failed = []
    if OUTPUT_FAILED.exists():
        with open(OUTPUT_FAILED, encoding="utf-8") as f:
            failed = json.load(f)

    out_file = open(OUTPUT_JSONL, "a", encoding="utf-8")
    processed_rawis = 0
    processed_windows = 0

    try:
        for i in range(0, total_pages - 1, 2):
            text = clean(pages[i] + " " + pages[i + 1])
            pct = (i + 1) / total_pages * 100
            ts = time.strftime("%H:%M:%S")

            print(f"\n[{ts} UTC] Pages {i+1}-{i+2} / {total_pages} ({pct:.1f}%)", flush=True)
            print(f"  Apercu : {text[:100].strip()}", flush=True)
            print(f"  Envoi au modele ({len(text)} chars)...", flush=True)

            t0 = time.time()
            try:
                result = call_with_retry(text, context, i)
                rawis = result.get("rawis", [])
                elapsed = time.time() - t0
                ts2 = time.strftime("%H:%M:%S")

                if not rawis:
                    print(f"  [{ts2} UTC] Reponse {elapsed:.0f}s — pas de rawi (preface/intro)", flush=True)
                else:
                    print(f"  [{ts2} UTC] Reponse {elapsed:.0f}s — {len(rawis)} rawi(s) trouve(s)", flush=True)

                for rawi in rawis:
                    raqm = str(rawi.get("رقم_الترجمة", ""))
                    nom = rawi.get("الاسم_الكامل", "?")
                    shuyukh = len(rawi.get("الشيوخ", []))
                    talamidh = len(rawi.get("التلاميذ", []))
                    scholars = len(rawi.get("أقوال_العلماء", []))

                    if raqm and raqm not in already_done:
                        rawi["_pages"] = f"{i+1}-{i+2}"
                        out_file.write(json.dumps(rawi, ensure_ascii=False) + "\n")
                        out_file.flush()
                        already_done.add(raqm)
                        processed_rawis += 1
                        print(f"  + #{raqm} {nom} | {shuyukh} shuyukh | {talamidh} talamidh | {scholars} avis", flush=True)
                    elif raqm:
                        print(f"  ~ SKIP #{raqm} (deja extrait)", flush=True)

                processed_windows += 1

            except Exception as e:
                elapsed = time.time() - t0
                print(f"  ! ECHEC {elapsed:.0f}s : {str(e)[:100]}", flush=True)
                failed.append({"pages": f"{i+1}-{i+2}", "error": str(e)})
                with open(OUTPUT_FAILED, "w", encoding="utf-8") as ff:
                    json.dump(failed, ff, ensure_ascii=False, indent=2)

            if (processed_windows + 1) % CHECKPOINT_EVERY == 0:
                print(f"\n  === CHECKPOINT {processed_rawis} rawis extraits, {len(failed)} echecs ===\n", flush=True)

    finally:
        out_file.close()

    print(f"\n{'='*60}")
    print(f"TERMINE : {processed_rawis:,} rawis extraits")
    print(f"Echecs  : {len(failed)} fenetres")


if __name__ == "__main__":
    main()
