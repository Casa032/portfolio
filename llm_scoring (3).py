"""
llm_scoring.py — Score de pertinence DPO + résumé structuré, via le SDK OpenAI.

Un seul appel LLM par article renvoie : score 0-10, raison courte, et un
résumé structuré exploitable dans le rapport DPO. Utilise le contenu complet
si disponible (API), sinon le résumé du flux (RSS).

Échoue en douceur : si l'appel échoue, les champs llm_* restent None.
"""
import json
import re
import time

import openai

from config import (
    LLM_API_URL, LLM_API_KEY, LLM_MODELE, LLM_ACTIVE, LLM_PERIMETRE_DPO,
)

DELAI_LLM = 0.5
MAX_RETRIES_LLM = 3

openai.api_key = LLM_API_KEY
openai.base_url = LLM_API_URL


def _charger(texte: str):
    obj = json.loads(texte)
    for _ in range(3):
        if isinstance(obj, str):
            obj = json.loads(obj)
        else:
            break
    return obj


def _extraire_json(texte: str) -> dict | None:
    if not texte:
        return None
    t = texte.replace("```json", "").replace("```", "").strip()
    try:
        obj = _charger(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    bloc = m.group(0)
    candidats = [
        bloc,
        bloc.replace("'", '"'),
        re.sub(r",\s*([}\]])", r"\1", bloc),
        re.sub(r",\s*([}\]])", r"\1", bloc.replace("'", '"')),
    ]
    for c in candidats:
        try:
            obj = _charger(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _demander_verdict(titre: str, texte: str):
    """ Renvoie (score 0-10, raison, resume_structure) ou None si échec. """
    extrait = f"Titre : {titre or ''}\n\nTexte : {texte or ''}".strip()
    if not extrait:
        return None
    extrait = extrait[:6000]  # borne la taille (contenu juridique long)

    systeme = (
        "Tu es un assistant de veille juridique spécialisé dans la protection des "
        "données personnelles (DPO). On te donne un article. Fais deux choses :\n\n"
        "1) Évalue sa pertinence pour le périmètre suivant :\n"
        f"{LLM_PERIMETRE_DPO}\n"
        "Attribue un score entier de 0 à 10 (0-3 hors périmètre, 4-6 lien partiel, "
        "7-10 clairement pertinent).\n\n"
        "2) Rédige un résumé structuré, clair et factuel, en français, exploitable "
        "dans un rapport DPO. Structure-le ainsi (une ligne par champ, omets un "
        "champ si l'information est absente) :\n"
        "- Autorité/Juridiction : ...\n"
        "- Type : (loi, décision, sanction, ligne directrice, arrêt...)\n"
        "- Objet : 1 à 2 phrases sur le fond\n"
        "- Portée : (contraignante / indicative)\n"
        "- À retenir pour le DPO : 1 phrase d'impact concret\n\n"
        "Réponds UNIQUEMENT par un objet JSON valide, sans texte autour :\n"
        '{"score": <entier 0-10>, "raison": "phrase courte", '
        '"resume_structure": "le résumé structuré multi-lignes"}'
    )

    for tentative in range(1, MAX_RETRIES_LLM + 1):
        time.sleep(DELAI_LLM)
        try:
            resp = openai.chat.completions.create(
                model=LLM_MODELE,
                messages=[
                    {"role": "system", "content": systeme},
                    {"role": "user", "content": extrait},
                ],
                temperature=0,
                # Si ton fournisseur ne supporte pas response_format, commente :
                response_format={"type": "json_object"},
            )
            contenu = resp.choices[0].message.content.strip()
            verdict = _extraire_json(contenu)
            if verdict is None:
                print(f"  ! réponse LLM non parsable : {contenu[:120]!r}")
                return None
            try:
                score = int(round(float(verdict.get("score"))))
            except (TypeError, ValueError):
                score = 0
            score = max(0, min(10, score))
            raison = str(verdict.get("raison", "")).strip()
            resume_struct = str(verdict.get("resume_structure", "")).strip()
            return score, raison, resume_struct

        except openai.RateLimitError:
            attente = DELAI_LLM * tentative * 2
            print(f"  · 429 LLM, nouvelle tentative dans {attente:.0f}s "
                  f"({tentative}/{MAX_RETRIES_LLM})")
            time.sleep(attente)
            continue
        except Exception as e:
            print(f"  ! verdict LLM indisponible : {e}")
            return None

    print("  ! verdict LLM abandonné après plusieurs 429")
    return None


def scorer_llm_article(article: dict) -> dict:
    """ Ajoute llm_score, llm_raison et llm_resume à l'article, en place.

    Utilise le contenu complet si disponible (API), sinon le résumé (RSS).
    """
    if not LLM_ACTIVE:
        return article
    texte = article.get("contenu") or article.get("resume") or ""
    verdict = _demander_verdict(article.get("titre"), texte)
    if verdict is not None:
        article["llm_score"], article["llm_raison"], article["llm_resume"] = verdict
    return article
