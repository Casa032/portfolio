"""
scraper.py — Récupère le contenu complet d'un article et le nettoie.

Deux usages :
  - articles SANS contenu (flux RSS) : on télécharge la page (url) et on
    extrait le texte principal via trafilatura.
  - articles AVEC contenu (API) : on nettoie/normalise le texte existant.

Échoue en douceur : si le scraping échoue, on garde ce qu'on avait.
"""
import re
import time

import requests
import trafilatura

DELAI_SCRAPE = 1.0   # secondes entre deux téléchargements (politesse + anti-blocage)
TIMEOUT = 20
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _nettoyer_texte(texte: str) -> str | None:
    """ Normalise un texte : espaces, sauts de ligne, lignes vides multiples. """
    if not texte:
        return None
    t = texte.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() or None


def scraper_url(url: str) -> str | None:
    """ Télécharge la page et extrait le texte principal. None si échec. """
    if not url:
        return None
    try:
        time.sleep(DELAI_SCRAPE)
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        # trafilatura extrait le contenu principal (sans menus/pubs/footer)
        texte = trafilatura.extract(
            r.text, include_comments=False, include_tables=True,
            favor_precision=True,
        )
        return _nettoyer_texte(texte)
    except Exception as e:
        print(f"  ! scraping échoué {url} : {e}")
        return None


def enrichir_contenu(article: dict) -> dict:
    """ Complète/nettoie le champ contenu de l'article, en place.

    - pas de contenu -> on scrape l'url
    - contenu présent -> on le nettoie
    """
    contenu = article.get("contenu")
    if contenu and contenu.strip():
        # contenu déjà là (API) : on le nettoie juste
        article["contenu"] = _nettoyer_texte(contenu)
    else:
        # pas de contenu (RSS) : on tente le scraping
        scrappe = scraper_url(article.get("url"))
        if scrappe:
            article["contenu"] = scrappe
    return article
