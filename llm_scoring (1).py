"""
llm_scoring.py — Verdict de pertinence DPO par LLM (API compatible OpenAI).

Pour chaque article, on demande au modèle un verdict binaire pertinent/non
avec une courte raison. La réponse est demandée en JSON pour un parsing fiable.

Échoue en douceur : si l'API est indisponible, on laisse llm_pertinent à None
(= "non évalué") au lieu de planter le fetch.
"""
import json
import time
import requests

from config import (
    LLM_API_URL, LLM_API_KEY, LLM_MODELE, LLM_ACTIVE, LLM_PERIMETRE_DPO,
)

DELAI_LLM = 0.5
MAX_RETRIES_LLM = 3


def _demander_verdict(titre: str, resume: str) -> tuple[int, str] | None:
    """ Renvoie (score 0-10, raison) ou None si échec. """
    extrait = f"Titre : {titre or ''}\nRésumé : {resume or ''}".strip()
    if not extrait:
        return None

    systeme = (
        "Tu es un assistant de veille juridique spécialisé dans la protection des "
        "données personnelles (DPO). On te donne un article. Évalue sa pertinence "
        "pour le périmètre suivant :\n"
        f"{LLM_PERIMETRE_DPO}\n\n"
        "Attribue un score de pertinence entier de 0 à 10 :\n"
        "- 0 à 3 : hors périmètre ou lien très indirect\n"
        "- 4 à 6 : lien partiel, intérêt secondaire\n"
        "- 7 à 10 : clairement dans le périmètre DPO\n\n"
        "Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, de la forme :\n"
        '{\"score\": <entier 0-10>, \"raison\": \"une phrase courte en français\"}'
    )

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODELE,
        "messages": [
            {"role": "system", "content": systeme},
            {"role": "user", "content": extrait},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    for tentative in range(1, MAX_RETRIES_LLM + 1):
        time.sleep(DELAI_LLM)
        try:
            r = requests.post(LLM_API_URL, json=payload, headers=headers, timeout=60)
            if r.status_code == 429:
                attente = float(r.headers.get("Retry-After", DELAI_LLM * tentative * 2))
                print(f"  · 429 LLM, nouvelle tentative dans {attente:.0f}s "
                      f"({tentative}/{MAX_RETRIES_LLM})")
                time.sleep(attente)
                continue
            r.raise_for_status()
            contenu = r.json()["choices"][0]["message"]["content"].strip()
            contenu = contenu.replace("```json", "").replace("```", "").strip()
            verdict = json.loads(contenu)
            # score borné à 0-10, robuste si le modèle renvoie autre chose
            try:
                score = int(round(float(verdict.get("score"))))
            except (TypeError, ValueError):
                score = 0
            score = max(0, min(10, score))
            raison = str(verdict.get("raison", "")).strip()
            return score, raison
        except Exception as e:
            print(f"  ! verdict LLM indisponible : {e}")
            return None

    print("  ! verdict LLM abandonné après plusieurs 429")
    return None


def scorer_llm_article(article: dict) -> dict:
    """ Ajoute llm_score (0-10 ou None) et llm_raison à l'article, en place. """
    if not LLM_ACTIVE:
        return article

    verdict = _demander_verdict(article.get("titre"), article.get("resume"))
    if verdict is not None:
        article["llm_score"], article["llm_raison"] = verdict
    return article
