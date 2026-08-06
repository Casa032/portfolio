"""
helpers/generation_structure.py
=================================
Fonction pure : construit le squelette d'un projet à partir des règles
définies dans controls/control_structure/rules.yaml.

Ne fait aucun print ni aucune sortie console : retourne un objet
ResultatGeneration, c'est à l'appelant de décider quoi en faire
(afficher, logger, ignorer, tester).
"""

from pathlib import Path
from dataclasses import dataclass, field

from helpers._structure_commun import charger_regles


@dataclass
class ResultatGeneration:
    chemin_racine: Path
    elements_crees: list = field(default_factory=list)
    elements_ignores: list = field(default_factory=list)


def _resoudre_nom(element_regle: dict, nom_projet: str) -> str:
    if "nom" in element_regle:
        return element_regle["nom"]
    if "nom_template" in element_regle:
        return element_regle["nom_template"].format(nom_projet=nom_projet)
    raise ValueError(
        f"Règle sans 'nom' ni 'nom_template', génération impossible : {element_regle}"
    )


def _creer_noeud(chemin_parent: Path, element_regle: dict, nom_projet: str,
                  resultat: ResultatGeneration):
    nom = _resoudre_nom(element_regle, nom_projet)
    chemin = chemin_parent / nom

    if chemin.exists():
        resultat.elements_ignores.append(chemin)
    else:
        if element_regle["type"] == "dossier":
            chemin.mkdir(parents=True)
        else:
            chemin.touch()
        resultat.elements_crees.append(chemin)

    if element_regle["type"] == "dossier":
        for enfant in element_regle.get("enfants", []):
            _creer_noeud(chemin, enfant, nom_projet, resultat)


def generer_structure(nom_projet: str, destination: Path,
                       chemin_regles: Path | None = None) -> ResultatGeneration:
    """
    Génère le squelette conforme d'un projet.

    Args:
        nom_projet: nom métier du projet (ex: "demo_fraude"), utilisé pour
                     construire les noms variables (Espace_demo_fraude, ...).
        destination: dossier dans lequel créer le projet.
        chemin_regles: chemin explicite vers rules.yaml. Si None, résolu
                        automatiquement par rapport à la position du package.

    Returns:
        ResultatGeneration listant ce qui a été créé et ce qui existait déjà.

    Raises:
        FileExistsError: si le dossier racine du projet existe déjà
                          (pas d'écrasement silencieux).
    """
    regles = charger_regles(chemin_regles)

    nom_racine = regles["nom_projet_template"].format(nom_projet=nom_projet)
    chemin_racine = Path(destination) / nom_racine

    if chemin_racine.exists():
        raise FileExistsError(
            f"Le dossier {chemin_racine} existe déjà, génération annulée pour éviter d'écraser des données."
        )

    chemin_racine.mkdir(parents=True)
    resultat = ResultatGeneration(chemin_racine=chemin_racine, elements_crees=[chemin_racine])

    for element_regle in regles["arborescence"]:
        _creer_noeud(chemin_racine, element_regle, nom_projet, resultat)

    return resultat
