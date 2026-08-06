"""
controls/control_structure/audit_structure.py
================================================
Vérifie qu'un projet existant respecte les règles définies dans rules.yaml
(colocalisé dans ce même dossier). Fonction pure : pas de print, retourne
un objet ResultatAudit, c'est à l'appelant de décider quoi en faire.
"""

import re
import os
from pathlib import Path
from dataclasses import dataclass, field

from helpers._structure_commun import charger_regles


@dataclass
class ResultatAudit:
    projet: str
    anomalies: list = field(default_factory=list)
    elements_interdits: list = field(default_factory=list)

    @property
    def conforme(self) -> bool:
        return not (self.anomalies or self.elements_interdits)

    @property
    def statut(self) -> str:
        return "ACCEPTE" if self.conforme else "REJETE"


def _trouver_correspondance(contenu: list[str], element_regle: dict) -> str | None:
    if "nom" in element_regle:
        return element_regle["nom"] if element_regle["nom"] in contenu else None
    if "nom_pattern" in element_regle:
        regex = re.compile(element_regle["nom_pattern"])
        for nom_reel in contenu:
            if regex.match(nom_reel):
                return nom_reel
        return None
    raise ValueError(f"Règle sans 'nom' ni 'nom_pattern', audit impossible : {element_regle}")


def _verifier_noeud(chemin_courant: Path, element_regle: dict, chemin_relatif: str,
                     anomalies: list):
    contenu = os.listdir(chemin_courant) if chemin_courant.is_dir() else []
    nom_trouve = _trouver_correspondance(contenu, element_regle)

    label = element_regle.get("nom") or element_regle.get("nom_pattern")
    chemin_affiche = f"{chemin_relatif}/{label}" if chemin_relatif else label

    if nom_trouve is None:
        if element_regle.get("obligatoire", True):
            anomalies.append(chemin_affiche)
        return

    if element_regle["type"] == "dossier":
        chemin_enfant = chemin_courant / nom_trouve
        for enfant in element_regle.get("enfants", []):
            _verifier_noeud(chemin_enfant, enfant, chemin_affiche, anomalies)


def _verifier_patterns_interdits(racine_projet: Path, patterns: list[str]) -> list[str]:
    trouves = []
    for pattern in patterns:
        matches = list(racine_projet.rglob(pattern))
        trouves.extend(str(m.relative_to(racine_projet)) for m in matches)
    return trouves


def auditer_structure(chemin_projet: Path, chemin_regles: Path | None = None) -> ResultatAudit:
    """
    Audite un seul projet et retourne un objet ResultatAudit.

    Args:
        chemin_projet: dossier racine du projet à auditer (ex: Espace_demo_fraude).
        chemin_regles: chemin explicite vers rules.yaml. Si None, résolu
                        automatiquement (rules.yaml colocalisé dans ce dossier).
    """
    chemin_projet = Path(chemin_projet)
    regles = charger_regles(chemin_regles)
    resultat = ResultatAudit(projet=chemin_projet.name)

    pattern_racine = regles.get("nom_projet_pattern")
    if pattern_racine and not re.match(pattern_racine, chemin_projet.name):
        resultat.anomalies.append(
            f"nom du dossier racine '{chemin_projet.name}' ne respecte pas {pattern_racine}"
        )

    for element_regle in regles["arborescence"]:
        _verifier_noeud(chemin_projet, element_regle, "", resultat.anomalies)

    resultat.elements_interdits = _verifier_patterns_interdits(
        chemin_projet, regles.get("patterns_interdits", [])
    )
    return resultat


def auditer_plusieurs_structures(dossier_racine: Path,
                                  chemin_regles: Path | None = None) -> list[ResultatAudit]:
    """Audite tous les sous-dossiers de dossier_racine (un sous-dossier = un projet)."""
    resultats = []
    for entree in sorted(Path(dossier_racine).iterdir()):
        if entree.is_dir():
            resultats.append(auditer_structure(entree, chemin_regles))
    return resultats
