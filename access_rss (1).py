import feedparser
from normaliser import normaliser


def recup_rss(source: dict) -> list[dict]:
    """ Récupère et met en forme les sources rss

    `source` doit contenir: id, url_rss
    """
    nom = source.get("nom")
    url_rss = source.get("url_rss")
    if not url_rss:
        return []

    feed = feedparser.parse(url_rss)
    articles = []

    for entry in feed.entries:
        # langue : peut se trouver dans title_detail.language selon le flux
        langue = None
        title_detail = getattr(entry, "title_detail", None)
        if title_detail:
            langue = title_detail.get("language")

        brut = {
            "date": getattr(entry, "published", None),
            "auteur": getattr(entry, "author", None),
            "langue": langue,
            "titre": getattr(entry, "title", None),
            "resume": getattr(entry, "summary", None),
            "url": getattr(entry, "link", None),
        }
        try:
            articles.append(normaliser(brut, source["id"]))
        except ValueError:
            pass

    print(f"RSS-{nom} -> {len(articles)} articles récupérés")
    return articles
