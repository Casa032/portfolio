"""
audit_arborescence.py
======================
Contrôle que chaque projet respecte l'arborescence normée définie dans normes.yaml.

Fonctionnement :
    1. Charge la grille de règles depuis normes.yaml (commun + sujets)
    2. Parcourt chaque sous-dossier de --racine (= un projet)
    3. Détecte le sujet du projet (fichier .sujet à la racine du projet)
    4. Fusionne les règles "commun" + règles du sujet détecté
    5. Vérifie fichiers/dossiers obligatoires, sous-structure, patterns interdits
    6. Affiche un rapport console + exporte un CSV

Usage :
    python audit_arborescence.py --racine ./projets --config normes.yaml
    python audit_arborescence.py --racine ./projets --config normes.yaml --csv rapport.csv
"""

import argparse
import csv
import os
from pathlib import Path
from dataclasses import dataclass, field

import yaml


# ------------------------------------------------------------------
# Structures de données
# ------------------------------------------------------------------

@dataclass
class ResultatAudit:
    projet: str
    sujet: str
    fichiers_manquants: list = field(default_factory=list)
    dossiers_manquants: list = field(default_factory=list)
    sous_structure_manquante: list = field(default_factory=list)
    recommandations_absentes: list = field(default_factory=list)
    elements_interdits: list = field(default_factory=list)

    @property
    def conforme(self) -> bool:
        return not (
            self.fichiers_manquants
            or self.dossiers_manquants
            or self.sous_structure_manquante
            or self.elements_interdits
        )


# ------------------------------------------------------------------
# Chargement et fusion des règles
# ------------------------------------------------------------------

def charger_regles(chemin_config: str) -> dict:
    with open(chemin_config, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fusionner_regles(regles: dict, sujet: str) -> dict:
    """
    Combine le bloc 'commun' avec le bloc du sujet demandé.
    Les listes (fichiers/dossiers obligatoires, etc.) sont concaténées.
    La sous_structure est fusionnée dossier par dossier.
    """
    commun = regles.get("commun", {})
    bloc_sujet = regles.get("sujets", {}).get(sujet, {})

    fusion = {
        "fichiers_obligatoires": list(set(
            commun.get("fichiers_obligatoires", []) + bloc_sujet.get("fichiers_obligatoires", [])
        )),
        "dossiers_obligatoires": list(set(
            commun.get("dossiers_obligatoires", []) + bloc_sujet.get("dossiers_obligatoires", [])
        )),
        "fichiers_recommandes": list(set(
            commun.get("fichiers_recommandes", [])
        )),
        "patterns_interdits": list(set(
            commun.get("patterns_interdits", [])
        )),
        "sous_structure": {**commun.get("sous_structure", {}), **bloc_sujet.get("sous_structure", {})},
    }
    return fusion


def detecter_sujet(chemin_projet: Path) -> str | None:
    """Lit le fichier .sujet à la racine du projet (contient juste 'finance', 'marketing', 'ia'...)."""
    fichier_sujet = chemin_projet / ".sujet"
    if fichier_sujet.exists():
        return fichier_sujet.read_text(encoding="utf-8").strip().lower()
    return None


# ------------------------------------------------------------------
# Audit d'un projet
# ------------------------------------------------------------------

def auditer_projet(chemin_projet: Path, regles: dict) -> ResultatAudit | None:
    sujet = detecter_sujet(chemin_projet)

    if sujet is None:
        print(f"⚠️  {chemin_projet.name} : pas de fichier .sujet trouvé -> ignoré")
        return None

    if sujet not in regles.get("sujets", {}):
        print(f"⚠️  {chemin_projet.name} : sujet '{sujet}' inconnu dans normes.yaml -> ignoré")
        return None

    regles_effectives = fusionner_regles(regles, sujet)
    resultat = ResultatAudit(projet=chemin_projet.name, sujet=sujet)
    contenu_racine = set(os.listdir(chemin_projet))

    for fichier in regles_effectives["fichiers_obligatoires"]:
        if fichier not in contenu_racine:
            resultat.fichiers_manquants.append(fichier)

    for dossier in regles_effectives["dossiers_obligatoires"]:
        if not (chemin_projet / dossier).is_dir():
            resultat.dossiers_manquants.append(dossier)

    for fichier in regles_effectives["fichiers_recommandes"]:
        if fichier not in contenu_racine:
            resultat.recommandations_absentes.append(fichier)

    for dossier_parent, contraintes in regles_effectives["sous_structure"].items():
        chemin_parent = chemin_projet / dossier_parent
        if chemin_parent.is_dir():
            for sous_dossier in contraintes.get("dossiers_obligatoires", []):
                if not (chemin_parent / sous_dossier).is_dir():
                    resultat.sous_structure_manquante.append(f"{dossier_parent}/{sous_dossier}")

    for pattern in regles_effectives["patterns_interdits"]:
        matches = list(chemin_projet.rglob(pattern))
        if matches:
            resultat.elements_interdits.extend(
                str(m.relative_to(chemin_projet)) for m in matches
            )

    return resultat


def auditer_tous_les_projets(dossier_racine: str, chemin_config: str) -> list[ResultatAudit]:
    regles = charger_regles(chemin_config)
    resultats = []
    for entree in sorted(Path(dossier_racine).iterdir()):
        if entree.is_dir():
            r = auditer_projet(entree, regles)
            if r is not None:
                resultats.append(r)
    return resultats


# ------------------------------------------------------------------
# Rapports
# ------------------------------------------------------------------

def generer_rapport_console(resultats: list[ResultatAudit]):
    nb_conformes = sum(1 for r in resultats if r.conforme)
    print(f"\n{'='*60}")
    print(f"AUDIT ARBORESCENCE — {len(resultats)} projet(s) analysé(s), "
          f"{nb_conformes} conforme(s)")
    print(f"{'='*60}")

    for r in resultats:
        statut = "✅ Conforme" if r.conforme else "❌ Non conforme"
        print(f"\n{r.projet} [sujet: {r.sujet}] — {statut}")
        if r.fichiers_manquants:
            print(f"  Fichiers obligatoires manquants : {r.fichiers_manquants}")
        if r.dossiers_manquants:
            print(f"  Dossiers obligatoires manquants : {r.dossiers_manquants}")
        if r.sous_structure_manquante:
            print(f"  Sous-structure manquante        : {r.sous_structure_manquante}")
        if r.elements_interdits:
            print(f"  Éléments interdits présents     : {r.elements_interdits}")
        if r.recommandations_absentes:
            print(f"  Recommandé mais absent (info)   : {r.recommandations_absentes}")


def generer_rapport_csv(resultats: list[ResultatAudit], chemin_csv: str):
    with open(chemin_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "projet", "sujet", "conforme",
            "fichiers_manquants", "dossiers_manquants",
            "sous_structure_manquante", "elements_interdits",
            "recommandations_absentes",
        ])
        for r in resultats:
            writer.writerow([
                r.projet, r.sujet, "OUI" if r.conforme else "NON",
                " | ".join(r.fichiers_manquants),
                " | ".join(r.dossiers_manquants),
                " | ".join(r.sous_structure_manquante),
                " | ".join(r.elements_interdits),
                " | ".join(r.recommandations_absentes),
            ])
    print(f"\n📄 Rapport CSV exporté : {chemin_csv}")


# ------------------------------------------------------------------
# Point d'entrée
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Audit d'arborescence des projets data science")
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
