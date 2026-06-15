#!/usr/bin/env python3
"""
main.py — Point d'entrée de la veille DPO

Usage:
    python main.py --init         Initialise la base et enregistre les sources
    python main.py --fetch        Récolte les articles de toutes les sources
    python main.py --coverage     Affiche la couverture par source
    python main.py --report       Exporte les articles en CSV (articles.csv)
"""

import argparse
import csv

from database import init_db, upsert_source, insert_article, get_coverage, get_articles
from access_rss import recup_rss
from access_api import recup_api, recup_jo
from config import (
    SOURCES,
    MAPPING_API,
    API_HEADERS,
    MOTS_CLES,
    PISTE_CLIENT_ID,
    PISTE_CLIENT_SECRET,
)


def cmd_init():
    init_db()
    for source in SOURCES:
        upsert_source(source)
    print(f"✓ {len(SOURCES)} sources enregistrées")


def cmd_fetch():
    total = 0
    for source in SOURCES:
        articles = []

        try:
            if source.get("url_rss"):
                articles += recup_rss(source)

            elif source["id"] == "legifrance":
                # Légifrance passe par OAuth (flux PISTE) + filtrage mots-clés
                articles += recup_jo(
                    source,
                    PISTE_CLIENT_ID,
                    PISTE_CLIENT_SECRET,
                    MOTS_CLES,
                )

            elif source.get("url_api"):
                mapping = MAPPING_API.get(source["id"], {})
                headers = API_HEADERS.get(source["id"], {})
                articles += recup_api(source, mapping, headers=headers)

        except Exception as e:
            print(f"✗ Erreur sur {source.get('nom', source['id'])} : {e}")
            continue

        for article in articles:
            insert_article(article)
        total += len(articles)

    print(f"\n✓ Fetch terminé — {total} articles traités")


def cmd_coverage():
    rows = get_coverage()
    print(f"\n{'Source':<22} {'Portée':<14} {'Pays':<6} {'Articles':>8}  {'Dernier ajout':<14}")
    print("-" * 70)
    for r in rows:
        print(
            f"{r['nom']:<22} {(r['portee'] or ''):<14} {(r['pays'] or ''):<6} "
            f"{r['nb_articles']:>8}  {r['dernier_ajout'] or 'N/A':<14}"
        )


def cmd_report(chemin: str = "articles.csv"):
    articles = get_articles()
    champs = ["titre", "auteur", "date_publication", "url"]
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(articles)
    print(f"✓ {len(articles)} articles exportés vers {chemin}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veille DPO")
    parser.add_argument("--init",     action="store_true", help="Initialise la base et les sources")
    parser.add_argument("--fetch",    action="store_true", help="Récolte les articles")
    parser.add_argument("--coverage", action="store_true", help="Couverture par source")
    parser.add_argument("--report",   action="store_true", help="Exporte les articles en CSV")
    args = parser.parse_args()

    if args.init:
        cmd_init()
    elif args.fetch:
        cmd_fetch()
    elif args.coverage:
        cmd_coverage()
    elif args.report:
        cmd_report()
    else:
        parser.print_help()
