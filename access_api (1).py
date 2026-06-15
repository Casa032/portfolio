import re
import requests
from normaliser import normaliser


def recup_api(source: dict, mapping: dict, params: dict = None, headers: dict = None) -> list[dict]:
    """ Récupère et normalise les articles depuis les sources API
    Args:
       source: dict décrivant la source (id, nom, url_api...)
       mapping: correspondance champs API -> champs internes
       params: query params HTTP
       headers: en-têtes HTTP
    """
    nom = source.get("nom")
    url_api = source.get("url_api")
    if not url_api:
        return []

    resp = requests.get(url_api, params=params or {}, headers=headers or {}, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items = data if isinstance(data, list) else data.get("items") or data.get("results") or []

    articles = []
    for item in items:
        brut = {
            "date": item.get(mapping.get("date", "date")),
            "auteur": item.get(mapping.get("auteur", "auteur")),
            "langue": item.get(mapping.get("langue", "langue")),
            "titre": item.get(mapping.get("titre", "titre")),
            "resume": item.get(mapping.get("resume", "resume")),
            "url": item.get(mapping.get("url", "url")),
        }
        try:
            articles.append(normaliser(brut, source["id"]))
        except ValueError:
            pass

    print(f"API-{nom} -> {len(articles)} articles récupérés")
    return articles


# ------------------- Partie légifrance ---------------------------------------#

def get_piste_token(client_id: str, client_secret: str) -> str:
    URL = 'https://oauth.piste.gouv.fr/api/oauth/token'
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "openid",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    response = requests.post(URL, headers=headers, data=data, timeout=30)
    response.raise_for_status()
    return response.json()['access_token']


def _contient_mot_cle(texte: str, mots_cles: list) -> tuple:
    if not texte:
        return False, None
    texte_lower = texte.lower()
    for mot in mots_cles:
        if re.search(re.escape(mot.lower()), texte_lower):
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
                    "date": date_jo,
                    "auteur": lien.get("ministere", ""),
                    "langue": "FR",
                    "titre": titre,
                    "resume": None,
                    "url": f"https://www.legifrance.gouv.fr/jorf/id/{cid}",
                })
        # récursion sur les sous-niveaux de CET item
        _parcourir_tms(item.get("tms", []), titre_jo, date_jo, mots_cles, resultats)


def recup_jo(source: dict, client_id: str, client_secret: str, mots_cles: list, nb: int = 300) -> list[dict]:
    """
    Récupère les derniers JO et filtre par mots-clés
    """
    nom = source.get("nom")
    token = get_piste_token(client_id, client_secret)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    payload = {"nbElement": nb}

    r = requests.post(
        "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/consult/lastNJo",
        headers=headers,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()

    resultats = []
    for container in result.get("containers", []):
        titre_jo = container.get("titre", None)
        date_jo = container.get("datePubli", None)
        _parcourir_tms(
            container.get("structure", {}).get("tms", []),
            titre_jo, date_jo, mots_cles, resultats
        )

    articles = []
    for brut in resultats:
        try:
            articles.append(normaliser(brut, source["id"]))
        except ValueError:
            pass

    print(f"API-{nom} -> {len(articles)} articles récupérés")
    return articles
