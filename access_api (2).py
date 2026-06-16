import re
import requests
from normaliser import normaliser, cle_dedup


def recup_contenu_celex(celex: str, headers: dict = None) -> str | None:
    """ Récupère le texte intégral d'un document Eur-lex via son CELEX.

    POST avec l'identifiant dans le corps JSON.
    Réponse : { ..., "content": { "fullText": "...", "tables": [...], ... } }
    """
    if not celex:
        return None

    # >>> À COMPLÉTER avec ta doc Eur-lex :
    URL_DETAIL = "https://lex-api.com/api/v1/documents/content"   # <-- endpoint détail
    payload = {"celex": celex}                                     # <-- nom du champ attendu

    try:
        r = requests.post(URL_DETAIL, json=payload, headers=headers or {}, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("content", {}).get("fullText")
    except Exception as e:
        print(f"  ! contenu CELEX {celex} indisponible : {e}")
        return None


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
        url = item.get(mapping.get("url", "url"))
        brut = {
            "date": item.get(mapping.get("date", "date")),
            "auteur": item.get(mapping.get("auteur", "auteur")),
            "langue": item.get(mapping.get("langue", "langue")),
            "titre": item.get(mapping.get("titre", "titre")),
            "resume": item.get(mapping.get("resume", "resume")),
            "url": url,
        }

        # Seconde requête : contenu intégral via le CELEX.
        # On lit le champ celexNumber de la réponse (identifiant exact, avec
        # son éventuel suffixe ex. "(01)"), et non l'URL d'où le suffixe se perd.
        celex = item.get(mapping.get("celex", "celexNumber"))
        if celex:
            brut["contenu"] = recup_contenu_celex(celex, headers=headers)

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


def recup_contenu_jorf(cid: str, token: str) -> str | None:
    """ Récupère le texte d'un document JORF Légifrance via son identifiant.

    POST avec l'identifiant dans le corps JSON.
    """
    if not cid:
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    # >>> À COMPLÉTER avec ta doc PISTE/Légifrance :
    URL_DETAIL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/consult/jorf"  # <-- endpoint détail
    payload = {"textCid": cid}                                                            # <-- nom du champ attendu

    try:
        r = requests.post(URL_DETAIL, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        # >>> À ADAPTER : clé(s) où se trouve le texte dans la réponse
        return data.get("texte") or data.get("contenu") or data.get("content")
    except Exception as e:
        print(f"  ! contenu JORF {cid} indisponible : {e}")
        return None


def _parcourir_tms(tms: list, titre_jo: str, date_jo: str, mots_cles: list, resultats: list, token: str = None):
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
                    "contenu": recup_contenu_jorf(cid, token) if token else None,
                    "url": f"https://www.legifrance.gouv.fr/jorf/id/{cid}",
                })
        # récursion sur les sous-niveaux de CET item
        _parcourir_tms(item.get("tms", []), titre_jo, date_jo, mots_cles, resultats, token)


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
            titre_jo, date_jo, mots_cles, resultats, token
        )

    articles = []
    for brut in resultats:
        try:
            articles.append(normaliser(brut, source["id"]))
        except ValueError:
            pass

    print(f"API-{nom} -> {len(articles)} articles récupérés")
    return articles
