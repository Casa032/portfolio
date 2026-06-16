import requests
from .normalizer import normalize_article, strip_html


def fetch_api(source: dict, mapping: dict, params: dict = None, headers: dict = None) -> list[dict]:
    """
    Récupère et normalise les articles depuis une API JSON.

    Args:
        source  : dict source (id, url_api, ...)
        mapping : correspondance champs API → champs normalisés
                  ex: {"url": "link", "titre": "title", "date": "pubDate", "contenu": "excerpt"}
        params  : query params optionnels (pagination, clé API...)
        headers : headers HTTP optionnels

    Retourne une liste de dicts prêts pour insert_article().
    """
    url_api = source.get("url_api")
    if not url_api:
        return []

    resp = requests.get(url_api, params=params or {}, headers=headers or {}, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Supporte les formats {"items": [...]} ou directement [...]
    items = data if isinstance(data, list) else data.get("items") or data.get("results") or []

    articles = []
    for item in items:
        raw = {
            "url":     item.get(mapping.get("url", "url")),
            "titre":   item.get(mapping.get("titre", "title")),
            "date":    item.get(mapping.get("date", "date")),
            "contenu": item.get(mapping.get("contenu", "content")),
        }
        try:
            article = normalize_article(raw, source["id"])
            # Conserve le CELEX pour un enrichissement ultérieur (EUR-Lex)
            celex_field = mapping.get("celex", "celexNumber")
            if item.get(celex_field):
                article["celex"] = item.get(celex_field)
            articles.append(article)
        except ValueError:
            continue

    print(f"  [{source['id']}] API → {len(articles)} articles récupérés")
    return articles


LEGIFRANCE_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/search"

LEGIFRANCE_BODY = {
    "recherche": {
        "filtres": [{"valeur": "ORDONNANCE,ARRETE,LOI", "facette": "NATURE"},
                    {"dates": {"start": "2020-01-01"}, "facette": "DATE_SIGNATURE"}],
        "sort": "SIGNATURE_DATE_DESC",
        "fromAdvancedRecherche": False,
        "secondSort": "ID",
        "champs": [{"criteres": [{"proximite": 3, "valeur": "fonction publique",
                                  "operateur": "ET", "typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP"}],
                    "operateur": "ET", "typeChamp": "TITLE"}],
        "pageNumber": 1,
        "typePagination": "DEFAUT"
    },
    "fond": "LODA_DATE"
}


def fetch_legifrance(source: dict, token: str, body: dict = None) -> list[dict]:
    """
    Fetch depuis l'API Légifrance (POST JSON, OAuth2 Bearer).
    `token` : Bearer token obtenu via PISTE OAuth.
    `body`  : corps de requête personnalisé, sinon utilise LEGIFRANCE_BODY.
    """
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    resp = requests.post(
        source.get("url_api") or LEGIFRANCE_URL,
        json=body or LEGIFRANCE_BODY,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    articles = []
    for result in data.get("results", []):
        for title in result.get("titles", []):
            cid = title.get("cid", "")
            raw = {
                "url":     f"https://www.legifrance.gouv.fr/loda/id/{cid}" if cid else None,
                "titre":   title.get("title"),
                "date":    title.get("startDate"),
                "contenu": None,  # L'API search ne retourne pas le texte complet
            }
            try:
                articles.append(normalize_article(raw, source["id"]))
            except ValueError:
                continue

    print(f"  [{source['id']}] Légifrance → {len(articles)} textes récupérés")
    return articles


# ── Légifrance / Journal Officiel ─────────────────────────────────────────────

PISTE_TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
LEGIFRANCE_LAST_NJO_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/consult/lastNJo"


def get_legifrance_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        PISTE_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
            "scope":         "openid",
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _contient_mot_cle(texte: str, mots_cles: list) -> tuple:
    texte_lower = texte.lower()
    for mot in mots_cles:
        if mot.lower() in texte_lower:
            return True, mot
    return False, None


def _parcourir_tms(tms: list, titre_jo: str, date_jo: str, mots_cles: list, resultats: list):
    for item in tms:
        for lien in item.get("liensTxt", []):
            titre = lien.get("titre", "")
            found, mot = _contient_mot_cle(titre, mots_cles)
            if found:
                cid = lien.get("id", "")
                resultats.append({
                    "url":     f"https://www.legifrance.gouv.fr/jorf/id/{cid}",
                    "titre":   titre,
                    "date":    date_jo,
                    "contenu": None,
                })
        _parcourir_tms(item.get("tms", []), titre_jo, date_jo, mots_cles, resultats)


def fetch_jo(source: dict, client_id: str, client_secret: str, mots_cles: list, nb: int = 300) -> list[dict]:
    """
    Récupère les derniers JO et filtre par mots-clés.
    Retourne une liste de dicts normalisés prêts pour insert_article().
    """
    token = get_legifrance_token(client_id, client_secret)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "accept":        "application/json",
    }
    resp = requests.post(
        source.get("url_api") or LEGIFRANCE_LAST_NJO_URL,
        headers=headers,
        json={"nbElement": nb},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()

    resultats = []
    for container in result.get("containers", []):
        titre_jo = container.get("titre", "?")
        date_jo  = container.get("datePubli", "?")
        _parcourir_tms(
            container.get("structure", {}).get("tms", []),
            titre_jo, date_jo, mots_cles, resultats
        )

    articles = []
    for raw in resultats:
        try:
            articles.append(normalize_article(raw, source["id"]))
        except ValueError:
            continue

    print(f"  [{source['id']}] JO → {len(articles)} textes trouvés sur {nb} JO parcourus")
    return articles


# ── EUR-Lex : récupération du contenu via CELEX ────────────────────────────

def fetch_eurlex_contenu(celex_numbers: list, base_url: str, headers: dict = None) -> dict:
    """
    Récupère le contenu de plusieurs documents EUR-Lex en une requête.

    Args:
        celex_numbers : liste de CELEX number à récupérer
        base_url       : URL de base de l'API (ex: source["url_api"])
        headers        : headers HTTP optionnels (auth...)

    Retourne un dict {celex_number: contenu_str}.
    """
    url = base_url.rstrip("/") + "/api/v1/documentContent/batch"
    resp = requests.post(
        url,
        json={"celexNumber": celex_numbers},
        headers=headers or {},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # Adapte cette partie selon la forme exacte de la réponse une fois testée
    contenus = {}
    items = data if isinstance(data, list) else data.get("results") or data.get("items") or []
    for item in items:
        celex = item.get("celexNumber") or item.get("celex")
        contenu = item.get("content") or item.get("contenu") or item.get("text")
        if celex:
            contenus[celex] = contenu

    return contenus


def enrichir_articles_eurlex(articles: list, base_url: str, headers: dict = None, batch_size: int = 20):
    """
    Enrichit en place une liste d'articles normalisés (déjà filtrés) avec leur contenu EUR-Lex.
    Suppose que chaque article a un champ 'celex' stocké à part (à ajouter lors du fetch initial),
    ou que le CELEX peut être extrait de l'URL.
    """
    # Récupère les celex depuis les articles (à adapter selon où tu stockes le celex)
    celex_map = {a.get("celex"): a for a in articles if a.get("celex")}
    celex_numbers = list(celex_map.keys())

    for i in range(0, len(celex_numbers), batch_size):
        batch = celex_numbers[i:i + batch_size]
        contenus = fetch_eurlex_contenu(batch, base_url, headers=headers)
        for celex, contenu in contenus.items():
            if celex in celex_map:
                celex_map[celex]["contenu"] = strip_html(contenu)
