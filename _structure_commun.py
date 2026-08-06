"""
helpers/_structure_commun.py
=============================
Fonctions internes partagées entre generation_structure.py et audit_structure.py.
Préfixé par "_" : pas destiné à être importé directement depuis l'extérieur
du package, seulement par les autres modules de helpers.
"""

from pathlib import Path
import yaml


def chemin_regles_par_defaut() -> Path:
    """
    Chemin par défaut vers rules.yaml, calculé depuis la position de ce fichier
    (helpers/ et controls/ sont deux dossiers frères à la racine du package).
    Utilisé uniquement si l'appelant ne fournit pas explicitement un chemin.
    """
    racine_package = Path(__file__).resolve().parent.parent
    return racine_package / "controls" / "control_structure" / "rules.yaml"


def charger_regles(chemin_regles: Path | None) -> dict:
    chemin = chemin_regles or chemin_regles_par_defaut()
    with open(chemin, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
