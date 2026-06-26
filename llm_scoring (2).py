"""
llm_scoring.py — Score de pertinence DPO par LLM via le SDK OpenAI.

Utilise le SDK openai (style module) avec une base_url personnalisée.
Pour chaque article, on demande un score 0-10 + une raison, en JSON.

Échoue en douceur : si l'appel échoue, llm_score reste None (= non évalué).
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

# Configuration du SDK (style module) : clé + base_url du fournisseur tiers.
openai.api_key = LLM_API_KEY
openai.base_url = LLM_API_URL


def _charger(texte: str):
    """ json.loads + gestion du double encodage : si le résultat est encore
        une chaîne, on retente jusqu'à obtenir un objet (max 3 fois). """
    obj = json.loads(texte)
    for _ in range(3):
        if isinstance(obj, str):
            obj = json.loads(obj)
        else:
            break
    return obj


def _extraire_json(texte: str) -> dict | None:
    """ Extrait un objet JSON d'une réponse LLM, même imparfaite.

    Gère : blocs ```json, texte avant/après, guillemets simples,
    virgules traînantes, et double encodage (string contenant du JSON).
    Renvoie None si rien d'exploitable.
    """
    if not texte:
        return None

    # 1. retirer les fences markdown
    t = texte.replace("```json", "").replace("```", "").strip()

    # 2. tentative directe (avec gestion du double encodage)
    try:
        obj = _charger(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 3. isoler le premier bloc { ... } présent dans le texte
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    bloc = m.group(0)

    # 4. corrections courantes : guillemets simples -> doubles,
    #    virgule traînante avant } ou ]
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
        '{"score": <entier 0-10>, "raison": "une phrase courte en français"}'
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
                # Si ton fournisseur tiers ne supporte pas response_format,
                # commente la ligne suivante (le prompt demande déjà du JSON) :
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
            return score, raison

        except openai.RateLimitError as e:
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
    """ Ajoute llm_score (0-10 ou None) et llm_raison à l'article, en place. """
    if not LLM_ACTIVE:
        return article

    verdict = _demander_verdict(article.get("titre"), article.get("resume"))
    if verdict is not None:
        article["llm_score"], article["llm_raison"] = verdict
    return article
