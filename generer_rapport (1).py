"""
generer_rapport.py — Génère le rapport de veille PPTX depuis la base.

Usage :
    python generer_rapport.py [--top N] [--seuil S]

  --top N   : nombre max d'articles par partie (défaut 8)
  --seuil S : score LLM minimum pour retenir un article (défaut 6)

Produit rapport_veille.pptx (3 parties, sommaires cliquables).
"""
import json
import subprocess
import sys
import os
import zipfile

from database import get_connection
from classer_rapport import classer, NOMS_PARTIES


def rezip_pptx(chemin: str):
    """ Recompresse le .pptx (DEFLATE, sans stubs de dossiers).

    pptxgenjs écrit un ZIP non compressé avec des entrées de dossiers vides,
    ce qui fait que certains lecteurs signalent le fichier comme endommagé.
    On réécrit l'archive proprement, contenu inchangé.
    """
    with zipfile.ZipFile(chemin, "r") as zin:
        entries = [(info, zin.read(info.filename))
                   for info in zin.infolist() if not info.is_dir()]
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in entries:
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.external_attr = info.external_attr
            zout.writestr(out, data, zipfile.ZIP_DEFLATED)


def meilleur_score(a: dict) -> int:
    """ Score de tri : LLM s'il existe, sinon lexical. """
    if a.get("llm_score") is not None:
        return a["llm_score"]
    return a.get("score_pertinence") or 0


def collecter(top: int, seuil: int) -> dict:
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute("""
            SELECT a.*, s.nom AS source_nom
            FROM articles a JOIN sources s ON s.id = a.source_id
        """)]
    finally:
        conn.close()

    # filtre pertinence : LLM >= seuil, ou (pas de LLM) lexical > 0
    retenus = []
    for a in rows:
        if a.get("llm_score") is not None:
            if a["llm_score"] >= seuil:
                retenus.append(a)
        elif (a.get("score_pertinence") or 0) > 0:
            retenus.append(a)

    # répartition dans les 3 parties
    parties = {1: [], 2: [], 3: []}
    for a in retenus:
        parties[classer(a)].append(a)

    # tri par score décroissant + limite top N par partie
    for p in parties:
        parties[p].sort(key=meilleur_score, reverse=True)
        parties[p] = parties[p][:top]

    return parties


def main(top: int = 8, seuil: int = 6):
    parties = collecter(top, seuil)

    # prépare les données pour le script Node
    data = {
        "titre": "Veille juridique DPO",
        "parties": [
            {"num": p, "nom": NOMS_PARTIES[p], "articles": [
                {
                    "titre": a.get("titre") or "Sans titre",
                    "source": a.get("source_nom") or "",
                    "date": a.get("date_publication") or "",
                    "url": a.get("url") or "",
                    "score": meilleur_score(a),
                    "raison": a.get("llm_raison") or a.get("score_details") or "",
                }
                for a in parties[p]
            ]}
            for p in (1, 2, 3)
        ],
    }

    with open("donnees_rapport.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    for p in data["parties"]:
        print(f"Partie {p['num']} : {len(p['articles'])} articles")

    # génère le pptx via Node
    env = dict(os.environ, NODE_PATH="/home/claude/.npm-global/lib/node_modules")
    subprocess.run(["node", "build_pptx.js"], check=True, env=env)

    # recompresse le fichier (sinon "fichier endommagé" à l'ouverture)
    rezip_pptx("rapport_veille.pptx")
    print("✓ rapport_veille.pptx généré")


if __name__ == "__main__":
    top = 8
    seuil = 6
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    if "--seuil" in sys.argv:
        seuil = int(sys.argv[sys.argv.index("--seuil") + 1])
    main(top, seuil)
