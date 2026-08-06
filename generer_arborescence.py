"""
generer_arborescence.py
========================
Construit le squelette d'un nouveau projet à partir de normes.yaml,
en créant tous les dossiers/fichiers obligatoires au bon endroit.

Pour les éléments à nom variable (nom_pattern), le nom réel est construit
à partir de "nom_template" (ex: "Espace_{nom_projet}") et du nom de
projet fourni en argument.

Usage :
    python generer_arborescence.py --nom-projet mon_super_projet --destination ./mes_projets --config normes.yaml
"""

import argparse
from pathlib import Path

import yaml


def charger_regles(chemin_config: str) -> dict:
    with open(chemin_config, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resoudre_nom(element_regle: dict, nom_projet: str) -> str:
    """
    Détermine le nom réel à créer pour un élément :
      - "nom" si fixe
      - "nom_template" rempli avec nom_projet si variable
    """
    if "nom" in element_regle:
        return element_regle["nom"]

    if "nom_template" in element_regle:
        return element_regle["nom_template"].format(nom_projet=nom_projet)

    raise ValueError(
        f"Impossible de déterminer un nom concret pour la règle {element_regle} : "
        f"il manque 'nom' ou 'nom_template' (nom_pattern seul ne suffit pas pour générer)."
    )


def creer_noeud(chemin_parent: Path, element_regle: dict, nom_projet: str, cree: list, ignores: list):
    """
    Crée récursivement un élément (fichier ou dossier) et ses enfants.
    """
    nom = resoudre_nom(element_regle, nom_projet)
    chemin = chemin_parent / nom

    if chemin.exists():
        ignores.append(str(chemin))
    else:
        if element_regle["type"] == "dossier":
            chemin.mkdir(parents=True)
        else:  # fichier
            chemin.touch()
        cree.append(str(chemin))

    if element_regle["type"] == "dossier":
        for enfant in element_regle.get("enfants", []):
            creer_noeud(chemin, enfant, nom_projet, cree, ignores)


def generer_projet(nom_projet: str, dossier_destination: str, chemin_config: str):
    regles = charger_regles(chemin_config)

    nom_racine = regles["nom_projet_template"].format(nom_projet=nom_projet)
    chemin_racine = Path(dossier_destination) / nom_racine

    cree = []
    ignores = []

    if chemin_racine.exists():
        print(f"⚠️  Le dossier {chemin_racine} existe déjà. Rien n'a été créé pour éviter d'écraser des données.")
        return

    chemin_racine.mkdir(parents=True)
    cree.append(str(chemin_racine))

    for element_regle in regles["arborescence"]:
        creer_noeud(chemin_racine, element_regle, nom_projet, cree, ignores)

    print(f"\n✅ Squelette créé : {chemin_racine}\n")
    print(f"{len(cree)} élément(s) créé(s) :")
    for c in cree:
        print(f"  + {c}")
    if ignores:
        print(f"\n{len(ignores)} élément(s) déjà existant(s), ignoré(s) :")
        for i in ignores:
            print(f"  = {i}")


def main():
    parser = argparse.ArgumentParser(description="Génère un squelette de projet conforme aux normes")
    parser.add_argument("--nom-projet", required=True, help="Nom du projet (ex: mon_super_projet)")
    parser.add_argument("--destination", required=True, help="Dossier où créer le projet")
    parser.add_argument("--config", default="normes.yaml", help="Chemin vers normes.yaml")
    args = parser.parse_args()

    generer_projet(args.nom_projet, args.destination, args.config)


if __name__ == "__main__":
    main()
