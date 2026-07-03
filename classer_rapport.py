"""
classer_rapport.py — Classe chaque article dans l'une des 3 parties du rapport.

Priorité descendante (un article tombe dans UNE seule partie) :
  Partie 3 — Décisions / sanctions juridiques et autorités européennes
  Partie 1 — Actualités françaises (CNIL, publications, revue de presse FR)
  Partie 2 — Actualités internationales (le reste)

Détection : mots-clés sur titre+resume+contenu, avec la source comme appui.
"""
import re

# --- Sources qui ancrent fortement une catégorie (filet de sécurité) ---
SOURCES_JURIDIQUE = {"cjue", "lex", "legifrance"}
SOURCES_FR        = {"cnil", "mathias avocat", "Bensoussan"}
SOURCES_INTL      = {"edpb", "gdprhub"}

# --- Marqueurs de contenu ---
MOTS_JURIDIQUE = [
    "arrêt", "décision", "sanction", "amende", "condamn", "jugement",
    "cjue", "tribunal", "cour de justice", "contentieux", "délibération sanction",
    "jorf", "eur-lex", "affaire c-", "ecli",
]
MOTS_FR = [
    "cnil", "france", "français", "française", "délibération",
    "légifrance", "journal officiel",
]
MOTS_INTL = [
    "edpb", "cepd", "european data protection", "international",
    "transfert", "pays tiers", "gdprhub", "irlande", "allemagne",
    "espagne", "italie", "portugal", "royaume-uni",
]


def _compte(texte: str, mots: list) -> int:
    return sum(1 for m in mots if re.search(re.escape(m), texte))


def classer(article: dict) -> int:
    """ Renvoie 1, 2 ou 3 : la partie du rapport où ranger l'article. """
    texte = " ".join(filter(None, [
        article.get("titre"), article.get("resume"), article.get("contenu"),
    ])).lower()
    src = article.get("source_id")

    j = _compte(texte, MOTS_JURIDIQUE) + (2 if src in SOURCES_JURIDIQUE else 0)
    f = _compte(texte, MOTS_FR)        + (2 if src in SOURCES_FR else 0)
    i = _compte(texte, MOTS_INTL)      + (2 if src in SOURCES_INTL else 0)

    # Priorité descendante : juridique d'abord, puis français, puis international.
    # Le juridique l'emporte s'il a un signal net (>=2), sinon on départage FR/INTL.
    if j >= 2 and j >= f:
        return 3
    if f >= i:
        return 1
    return 2


NOMS_PARTIES = {
    1: "Actualités françaises — CNIL, sanctions, publications & revue de presse",
    2: "Actualités internationales",
    3: "Décisions & sanctions juridiques — autorités européennes",
}
