import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
#--------------------------------------------------------------------#


def comp_id(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()


def nettoyer_html(texte: str) -> str | None:
    """ Supprime les balises html"""
    if not texte:
        return None
    return re.sub(r"<[^>]+>", "", texte).strip()


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
        "auteur": brut.get("auteur"),
        "date_publication": parse_date(brut.get("date")),
        "langue": brut.get("langue"),
        "titre": (brut.get("titre") or "Sans titre").strip(),
        "resume": extrait_sections(
            nettoyer_html(brut.get("resume")) or "Pas de résumé disponible"
        ),
        "url": url,
        "created_at": datetime.now().strftime('%Y/%m/%d')
    }
