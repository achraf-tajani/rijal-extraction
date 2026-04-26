import json
from pathlib import Path

JSONL = Path(__file__).parent / "output/tahdhib_extracted.jsonl"

rawis = []
with open(JSONL, encoding="utf-8") as f:
    for line in f:
        try:
            rawis.append(json.loads(line))
        except Exception:
            pass

print(f"Total rawis : {len(rawis)}\n")

for r in rawis[:5]:
    print(f"#{r.get('رقم_الترجمة')} — {r.get('الاسم_الكامل')}")
    print(f"  Kunya    : {r.get('الكنية') or '—'}")
    print(f"  Nisba    : {r.get('النسبة') or '—'}")
    print(f"  Kutub    : {r.get('الكتب')}")
    print(f"  Shuyukh  : {len(r.get('الشيوخ', []))} | Talamidh : {len(r.get('التلاميذ', []))} | Avis : {len(r.get('أقوال_العلماء', []))}")
    print(f"  Wafat    : {r.get('وفاته') or '—'}")
    print()
