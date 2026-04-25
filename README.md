# Extraction Tahdhib al-Kamal — RunPod

## Structure
```
rijal_extraction/
├── README.md
├── context/
│   ├── tahdhib_kamal.md   ← description du livre (référence)
│   └── schema.md          ← schéma JSON et règles d'extraction
├── data/
│   └── tahdhib_pages.csv  ← 19,002 pages du Tahdhib al-Kamal
├── output/                ← résultats générés ici
│   ├── tahdhib_extracted.jsonl
│   └── tahdhib_failed.json
└── extract_tahdhib.py     ← script principal
```

## Prérequis sur le serveur
- Ollama installé et qwen2.5:32b chargé
- Python 3.x avec `requests`

## Lancer l'extraction
```bash
python extract_tahdhib.py
```

Le script :
1. Lit les pages 2 par 2 (sliding window)
2. Envoie chaque paire au modèle via localhost:11434
3. Extrait tous les rawis trouvés dans le JSON retourné
4. Sauvegarde dans output/tahdhib_extracted.jsonl
5. En cas d'interruption : relancer la même commande, ça reprend automatiquement

## Récupérer les résultats
```bash
# Depuis ton PC via SCP/MobaXterm
scp user@runpod:/chemin/output/tahdhib_extracted.jsonl .
```

## Durée estimée
- ~110s par paire de pages
- ~19,000 pages / 2 = ~9,500 appels
- Total : ~290 heures (laisser tourner en tâche de fond)

## Format de sortie (tahdhib_extracted.jsonl)
Une ligne JSON par rawi :
```json
{"رقم_الترجمة": "١", "الاسم_الكامل": "...", "الشيوخ": [...], "أقوال_العلماء": [...], ...}
```
