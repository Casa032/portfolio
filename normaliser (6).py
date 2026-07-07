import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, parse_qs, unquote
#--------------------------------------------------------------------#


def cle_dedup(url: str) -> str:
    """ Dérive une clé canonique stable à partir d'une URL.

    Objectif : deux URLs qui pointent vers le MÊME document doivent
    produire la même clé, malgré les paramètres volatils (qid, session)
    ou la langue. On s'appuie sur les identifiants stables connus.
    """
    u = url.strip()

    # Eur-lex : identifiant CELEX (ex. ?uri=CELEX:62025CC0354)
    # présent soit dans le param uri, soit directement dans le chemin.
    decode = unquote(u)
    m = re.search(r"CELEX[:%]?3?A?[:]?\s*([0-9A-Z]+)", decode, re.IGNORECASE)
    if m:
        return f"celex:{m.group(1).upper()}"

    # Légifrance : identifiant JORF / CID (ex. /jorf/id/JORFTEXT000012345678)
    m = re.search(r"(JORF[A-Z]*\d+|LEGITEXT\d+|[A-Z]{4}\d{16,})", decode)
    if m:
        return f"legi:{m.group(1).upper()}"

    # Par défaut : URL nettoyée (sans qid/session/tracking, sans slash final)
    parts = urlsplit(u)
    qs = parse_qs(parts.query)
    drop = {"qid", "utm_source", "utm_medium", "utm_campaign", "utm_content",
            "utm_term", "fbclid", "gclid", "ref", "source"}
    qs_clean = sorted((k, v) for k, v in qs.items() if k.lower() not in drop)
    base = f"{parts.netloc.lower()}{parts.path.rstrip('/')}"
    if qs_clean:
        base += "?" + "&".join(f"{k}={','.join(v)}" for k, v in qs_clean)
    return base


def comp_id(url: str) -> str:
    return hashlib.md5(cle_dedup(url).encode()).hexdigest()


def nettoyer_html(texte: str) -> str | None:
    """ Nettoie un texte issu d'un flux : balises HTML, entités, échappements.

    Gère deux cas de \\n :
      - vrais sauts de ligne : on les garde mais on évite les répétitions
      - \\n littéraux (double échappement) : on les retransforme en vrai saut
    """
    if not texte:
        return None

    import html

    # 1. Double échappement éventuel : "\\n" / "\\t" littéraux -> vrais caractères
    texte = texte.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "")

    # 2. Balises de saut de ligne HTML -> \n avant de retirer le reste
    texte = re.sub(r"<\s*br\s*/?\s*>", "\n", texte, flags=re.IGNORECASE)
    texte = re.sub(r"</\s*p\s*>", "\n", texte, flags=re.IGNORECASE)

    # 3. Suppression des balises restantes
    texte = re.sub(r"<[^>]+>", "", texte)

    # 4. Décodage des entités HTML (&eacute; &nbsp; &amp; ...)
    texte = html.unescape(texte)

    # 5. Normalisation des espaces : pas plus de 2 sauts de ligne consécutifs,
    #    espaces multiples réduits, espaces en bord de ligne supprimés
    texte = texte.replace("\xa0", " ")               # nbsp insécable -> espace
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r" *\n *", "\n", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)

    return texte.strip() or None


def extrait_sections(text: str) -> str | None:
    if not text:
        return None
    faits_match = re.search(r"^={2,3}\s?Facts\s?={2,3}$", text, re.MULTILINE)
    decisions_match = re.search(r"^={2,3}\s?Holding\s?={2,3}\s*", text, re.MULTILINE)

    faits = ''
    description = ''
    if faits_match:
        description = text[:faits_match.start()].strip()
        end = decisions_match.start() if decisions_match else len(text)
        faits = text[faits_match.end():end].strip()

    decisions = ""
    if decisions_match:
        next_section = re.search(
            r"^={2,3}\s?Comment\s?={2,3}$",
            text[decisions_match.end():], re.MULTILINE
        )
        end = decisions_match.end() + next_section.start() if next_section else len(text)
        decisions = text[decisions_match.end():end].strip()

    parts = []
    if description:
        entete = re.sub(r"={2,3}\s?English\s?Summary\s?={2,3}$", " ", description)
        parts.append(entete)
    if faits:
        parts.append(f"Facts:\n {faits}")
    if decisions:
        parts.append(f"Holding: \n{decisions}")

    # Si aucune section reconnue, on renvoie le texte nettoyé d'origine
    return "\n\n".join(parts) or text or None


def parse_date(date: str) -> str | None:
    if not date:
        return None
    if not isinstance(date, str):
        date = str(date)
    try:
        return parsedate_to_datetime(date).strftime("%m/%d/%Y")
    except Exception:
        pass

    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return None


def _texte(valeur) -> str | None:
    """ Garantit une valeur stockable par SQLite : str ou None.

    Les flux RSS/API renvoient parfois des listes, dicts ou objets
    (ex. plusieurs auteurs, détails de langue). On les ramène à une chaîne.
    """
    if valeur is None:
        return None
    if isinstance(valeur, str):
        return valeur.strip() or None
    if isinstance(valeur, (list, tuple, set)):
        return ", ".join(_texte(v) or "" for v in valeur).strip(", ") or None
    if isinstance(valeur, dict):
        # cas feedparser : on tente les clés usuelles, sinon repr
        for cle in ("name", "value", "language", "term"):
            if cle in valeur:
                return _texte(valeur[cle])
        return None
    return str(valeur)


def normaliser(brut: dict, source_id: str) -> dict:
    """ Pour uniformiser la sortie des articles

    Champs attendus
        - url      (obligatoire)
        - titre    (obligatoire)
        - date     (optionnel)
        - resume   (optionnel)
    """

    url = (brut.get("url") or "").strip()
    if not url:
        raise ValueError("Le chemin n'a pas été trouvé")

    return {
        "id": comp_id(url),
        "source_id": source_id,
        "auteur": _texte(brut.get("auteur")),
        "date_publication": parse_date(brut.get("date")),
        "langue": _texte(brut.get("langue")),
        "titre": (_texte(brut.get("titre")) or "Sans titre"),
        "resume": extrait_sections(
            nettoyer_html(_texte(brut.get("resume")) or "") or "Pas de résumé disponible"
        ),
        "contenu": nettoyer_html(_texte(brut.get("contenu"))),
        "score_pertinence": 0,
        "score_details": None,
        "llm_score": None,
        "llm_raison": None,
        "llm_resume": None,
        "url": url,
        "created_at": datetime.now().strftime('%Y/%m/%d')
    }
