"""
audit_arborescence.py
======================
Vérifie qu'un projet respecte l'arborescence fixe définie dans normes.yaml.
Parcourt l'arbre de règles en profondeur (récursif) : chaque élément peut
avoir des enfants, sur autant de niveaux que nécessaire.

Un projet est REJETÉ si un seul élément obligatoire manque, à n'importe
quel niveau de profondeur.

Usage :
    python audit_arborescence.py --racine ./projets --config normes.yaml
    python audit_arborescence.py --racine ./projets --config normes.yaml --csv rapport.csv
"""

import argparse
import csv
import os
import re
from pathlib import Path
from dataclasses import dataclass, field


# ------------------------------------------------------------------
# Structures de données
# ------------------------------------------------------------------

@dataclass
class ResultatAudit:
    projet: str
    anomalies: list = field(default_factory=list)   # liste de chemins relatifs manquants/obligatoires
    elements_interdits: list = field(default_factory=list)

    @property
    def conforme(self) -> bool:
        return not (self.anomalies or self.elements_interdits)

    @property
    def statut(self) -> str:
        return "ACCEPTÉ" if self.conforme else "REJETÉ"


# ------------------------------------------------------------------
# Chargement des règles
# ------------------------------------------------------------------

def charger_regles(chemin_config: str) -> dict:
    import yaml
    with open(chemin_config, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------
# Cœur de l'audit : parcours récursif de l'arbre de règles
# ------------------------------------------------------------------

def trouver_correspondance(contenu: list[str], element_regle: dict) -> str | None:
    """
    Cherche, parmi les fichiers/dossiers réellement présents (contenu),
    celui qui correspond à la règle (nom exact OU pattern).
    Retourne le nom trouvé, ou None si rien ne correspond.
    """
    if "nom" in element_regle:
        # Nom exact attendu
        return element_regle["nom"] if element_regle["nom"] in contenu else None

    if "nom_pattern" in element_regle:
        # Nom variable : on cherche le premier élément qui matche la regex
        regex = re.compile(element_regle["nom_pattern"])
        for nom_reel in contenu:
            if regex.match(nom_reel):
                return nom_reel
        return None

    raise ValueError(f"Règle mal définie, il manque 'nom' ou 'nom_pattern' : {element_regle}")


def verifier_noeud(chemin_courant: Path, element_regle: dict, chemin_relatif: str,
                    anomalies: list):
    """
    Vérifie un élément de l'arbre de règles (fichier ou dossier) et,
    si c'est un dossier trouvé, redescend dans ses enfants (récursivité).
    """
    contenu = os.listdir(chemin_courant) if chemin_courant.is_dir() else []
    nom_trouve = trouver_correspondance(contenu, element_regle)

    label = element_regle.get("nom") or element_regle.get("nom_pattern")
    chemin_affiche = f"{chemin_relatif}/{label}" if chemin_relatif else label

    if nom_trouve is None:
        if element_regle.get("obligatoire", True):
            anomalies.append(chemin_affiche)
        return  # rien à vérifier plus loin puisque l'élément n'existe pas

    # L'élément existe : si c'est un dossier avec des enfants, on continue à descendre
    if element_regle["type"] == "dossier":
        chemin_enfant = chemin_courant / nom_trouve
        for enfant in element_regle.get("enfants", []):
            verifier_noeud(chemin_enfant, enfant, chemin_affiche, anomalies)


def verifier_patterns_interdits(racine_projet: Path, patterns: list[str]) -> list[str]:
    trouves = []
    for pattern in patterns:
        matches = list(racine_projet.rglob(pattern))
        trouves.extend(str(m.relative_to(racine_projet)) for m in matches)
    return trouves


def auditer_projet(chemin_projet: Path, regles: dict) -> ResultatAudit:
    resultat = ResultatAudit(projet=chemin_projet.name)

    # 1. Vérifier que le NOM du dossier racine respecte la convention
    pattern_racine = regles.get("nom_projet_pattern")
    if pattern_racine and not re.match(pattern_racine, chemin_projet.name):
        resultat.anomalies.append(
            f"nom du dossier racine '{chemin_projet.name}' ne respecte pas {pattern_racine}"
        )

    # 2. Vérifier le CONTENU attendu à l'intérieur de la racine
    for element_regle in regles["arborescence"]:
        verifier_noeud(chemin_projet, element_regle, "", resultat.anomalies)

    resultat.elements_interdits = verifier_patterns_interdits(
        chemin_projet, regles.get("patterns_interdits", [])
    )
    return resultat


def auditer_tous_les_projets(dossier_racine: str, chemin_config: str) -> list[ResultatAudit]:
    regles = charger_regles(chemin_config)
    resultats = []
    for entree in sorted(Path(dossier_racine).iterdir()):
        if entree.is_dir():
            resultats.append(auditer_projet(entree, regles))
    return resultats


# ------------------------------------------------------------------
# Rapports
# ------------------------------------------------------------------

def generer_rapport_console(resultats: list[ResultatAudit]):
    nb_acceptes = sum(1 for r in resultats if r.conforme)
    print(f"\n{'='*60}")
    print(f"AUDIT ARBORESCENCE — {len(resultats)} projet(s), "
          f"{nb_acceptes} accepté(s), {len(resultats) - nb_acceptes} rejeté(s)")
    print(f"{'='*60}")

    for r in resultats:
        icone = "✅" if r.conforme else "❌"
        print(f"\n{icone} {r.projet} — {r.statut}")
        if r.anomalies:
            print("  Éléments obligatoires manquants :")
            for a in r.anomalies:
                print(f"    - {a}")
        if r.elements_interdits:
            print("  Éléments interdits présents :")
            for e in r.elements_interdits:
                print(f"    - {e}")


def generer_rapport_csv(resultats: list[ResultatAudit], chemin_csv: str):
    with open(chemin_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["projet", "statut", "anomalies", "elements_interdits"])
        for r in resultats:
            writer.writerow([
                r.projet,
                r.statut,
                " | ".join(r.anomalies),
                " | ".join(r.elements_interdits),
            ])
    print(f"\n📄 Rapport CSV exporté : {chemin_csv}")


# ------------------------------------------------------------------
# Point d'entrée
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Audit d'arborescence fixe des projets data")
    parser.add_argument("--racine", required=True, help="Dossier contenant tous les projets")
    parser.add_argument("--config", default="normes.yaml", help="Chemin vers normes.yaml")
    parser.add_argument("--csv", default=None, help="Chemin de sortie du rapport CSV (optionnel)")
    args = parser.parse_args()

    resultats = auditer_tous_les_projets(args.racine, args.config)
    generer_rapport_console(resultats)
    if args.csv:
        generer_rapport_csv(resultats, args.csv)


if __name__ == "__main__":
    main()
