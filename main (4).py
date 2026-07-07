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

from database import (init_db, upsert_source, insert_article, get_coverage,
                      get_articles, update_scores, get_articles_a_scorer)
from access_rss import recup_rss
from access_api import recup_api, recup_jo
from traducteur import traduire_article
from scoring import scorer_article
from llm_scoring import scorer_llm_article
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
            article = traduire_article(article)
            article = scorer_article(article)
            article = scorer_llm_article(article)
            insert_article(article)
        total += len(articles)

    print(f"\n✓ Fetch terminé — {total} articles traités")


def cmd_coverage():
    rows = get_coverage()
    print(f"\n{'Source':<22} {'Portée':<12} {'Pays':<5} {'Art.':>5} {'Nouv.':>6}  "
          f"{'1ère pub':<12} {'Dern. pub':<12} {'Dern. ajout':<12}")
    print("-" * 92)
    for r in rows:
        print(
            f"{r['nom']:<22} {(r['portee'] or ''):<12} {(r['pays'] or ''):<5} "
            f"{r['nb_articles']:>5} {r['nouveaux_aujourdhui']:>6}  "
            f"{(r['premiere_publication'] or 'N/A'):<12} "
            f"{(r['derniere_publication'] or 'N/A'):<12} "
            f"{(r['dernier_ajout'] or 'N/A'):<12}"
        )
    total_nouveaux = sum(r['nouveaux_aujourdhui'] for r in rows)
    print(f"\n{total_nouveaux} nouveaux articles aujourd'hui")


def cmd_report(chemin: str = "articles.csv", seuil: int = None):
    articles = get_articles()
    # tri par pertinence décroissante
    articles.sort(key=lambda a: a.get("score_pertinence") or 0, reverse=True)
    # filtre optionnel : ne garder que les articles au-dessus d'un seuil
    if seuil is not None:
        articles = [a for a in articles if (a.get("score_pertinence") or 0) >= seuil]

    champs = ["score_pertinence", "titre", "auteur", "date_publication", "url", "score_details"]
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(articles)
    suffixe = f" (score >= {seuil})" if seuil is not None else ""
    print(f"✓ {len(articles)} articles exportés vers {chemin}{suffixe}")


def _traiter_articles(articles, libelle):
    print(f"{len(articles)} articles à {libelle}")
    for i, article in enumerate(articles, 1):
        article = scorer_article(article)        # lexical (gratuit)
        article = scorer_llm_article(article)    # LLM (1 appel : score + résumé)
        update_scores(article)
        if i % 10 == 0:
            print(f"  ... {i}/{len(articles)}")
    print(f"✓ {len(articles)} articles traités")


def cmd_rescore():
    """ Traite seulement les articles pas encore scorés par le LLM. """
    _traiter_articles(get_articles_a_scorer(), "scorer")


def cmd_rescore_all():
    """ Re-traite TOUS les articles (score + résumé), même déjà scorés.
        À utiliser après un changement de prompt ou l'ajout d'un champ. """
    _traiter_articles(get_articles(), "re-traiter (complet)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Veille DPO")
    parser.add_argument("--init",     action="store_true", help="Initialise la base et les sources")
    parser.add_argument("--fetch",    action="store_true", help="Récolte les articles")
    parser.add_argument("--coverage", action="store_true", help="Couverture par source")
    parser.add_argument("--report",   action="store_true", help="Exporte les articles en CSV")
    parser.add_argument("--rescore",  action="store_true", help="Score les articles existants non scorés")
    parser.add_argument("--rescore-all", dest="rescore_all", action="store_true",
                        help="Re-traite TOUS les articles (score + résumé), même déjà scorés")
    args = parser.parse_args()

    if args.init:
        cmd_init()
    elif args.fetch:
        cmd_fetch()
    elif args.coverage:
        cmd_coverage()
    elif args.report:
        cmd_report()
    elif args.rescore:
        cmd_rescore()
    elif args.rescore_all:
        cmd_rescore_all()
    else:
        parser.print_help()
