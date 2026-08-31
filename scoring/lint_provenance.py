"""T4 — Lint de provenance.

Deux verifications independantes :

  1. SOURCE — aucun litteral numerique ne peut etre affecte a un identifiant a
     consonance normative dans scoring/, report/, app/, fetch_norms.py ou
     verify_norms.py, sauf exception justifiee dans config/lint_provenance.json.

  2. SORTIE — dans un rapport JSON produit, toute valeur declaree normative
     (section `normes_employees`) doit porter un `provenance_id` present dans
     l'annexe de provenance, et reciproquement.

Utilisable en ligne de commande :  python3 -m scoring.lint_provenance
"""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parent.parent
CONFIG = RACINE / "config" / "lint_provenance.json"


@dataclass(frozen=True)
class Violation:
    fichier: str
    ligne: int
    identifiant: str
    valeur: str
    regle: str

    def __str__(self) -> str:
        return (f"{self.fichier}:{self.ligne}  {self.identifiant} = {self.valeur}"
                f"   [{self.regle}]")


def charger_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _est_normatif(identifiant: str, mots: set[str]) -> bool:
    parties = {p for p in identifiant.lower().replace("-", "_").split("_") if p}
    return bool(parties & mots)


def _litteral_numerique(noeud: ast.AST) -> str | None:
    """Renvoie une representation si le noeud est un nombre ou un conteneur de nombres."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)) \
            and not isinstance(noeud.value, bool):
        return repr(noeud.value)
    if isinstance(noeud, ast.UnaryOp) and isinstance(noeud.op, (ast.USub, ast.UAdd)):
        interne = _litteral_numerique(noeud.operand)
        return f"-{interne}" if interne else None
    if isinstance(noeud, (ast.List, ast.Tuple, ast.Set)):
        vals = [_litteral_numerique(e) for e in noeud.elts]
        if vals and all(v is not None for v in vals):
            return "[" + ", ".join(v for v in vals if v) + "]"
    if isinstance(noeud, ast.Dict):
        vals = [_litteral_numerique(v) for v in noeud.values]
        if vals and all(v is not None for v in vals):
            return "{...valeurs numeriques...}"
    return None


def scanner_fichier(chemin: Path, mots: set[str], exceptions: set[str]
                    ) -> list[Violation]:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    rel = str(chemin.relative_to(RACINE))
    viols: list[Violation] = []

    def verifier(nom: str, valeur_noeud: ast.AST, ligne: int, regle: str) -> None:
        if nom in exceptions or not _est_normatif(nom, mots):
            return
        rep = _litteral_numerique(valeur_noeud)
        if rep is not None:
            viols.append(Violation(rel, ligne, nom, rep, regle))

    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign):
            for cible in n.targets:
                if isinstance(cible, ast.Name):
                    verifier(cible.id, n.value, n.lineno, "affectation")
                elif isinstance(cible, ast.Attribute):
                    verifier(cible.attr, n.value, n.lineno, "affectation d'attribut")
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value:
            verifier(n.target.id, n.value, n.lineno, "affectation annotee")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            paires = list(zip(a.posonlyargs + a.args, [None] * (
                len(a.posonlyargs) + len(a.args) - len(a.defaults)) + list(a.defaults)))
            paires += list(zip(a.kwonlyargs, a.kw_defaults))
            for arg, defaut in paires:
                if defaut is not None:
                    verifier(arg.arg, defaut, getattr(defaut, "lineno", n.lineno),
                             "valeur par defaut d'argument")
        elif isinstance(n, ast.Dict):
            for cle, val in zip(n.keys, n.values):
                if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
                    verifier(cle.value, val, getattr(val, "lineno", n.lineno),
                             "cle de dictionnaire")
    return viols


def scanner_source(config: dict[str, Any] | None = None) -> list[Violation]:
    config = config or charger_config()
    mots = {m.lower() for m in config["mots_normatifs"]}
    exceptions = {e["identifiant"] for e in config["exceptions"]}
    exclus = {RACINE / p for p in config["modules_exclus"]}

    cibles: list[Path] = []
    for d in config["repertoires_scannes"]:
        cibles.extend(sorted((RACINE / d).rglob("*.py")))
    for f in config["fichiers_scannes"]:
        p = RACINE / f
        if p.exists():
            cibles.append(p)

    viols: list[Violation] = []
    for chemin in cibles:
        if chemin in exclus:
            continue
        viols.extend(scanner_fichier(chemin, mots, exceptions))
    return viols


def verifier_sortie(rapport: dict[str, Any]) -> list[str]:
    """Verifie la coherence provenance <-> normes employees d'un rapport JSON."""
    erreurs: list[str] = []
    annexe = rapport.get("annexe_provenance", [])
    ids_annexe = {e.get("provenance_id") for e in annexe}
    employees = rapport.get("normes_employees", [])

    for i, n in enumerate(employees):
        pid = n.get("provenance_id")
        if not pid:
            erreurs.append(
                f"normes_employees[{i}] ({n.get('description','?')}) : "
                "valeur normative sans provenance_id")
        elif pid not in ids_annexe:
            erreurs.append(
                f"normes_employees[{i}] : provenance_id {pid!r} absent de l'annexe")

    ids_employees = {n.get("provenance_id") for n in employees}
    for pid in sorted(ids_annexe - ids_employees):
        erreurs.append(f"annexe_provenance : {pid!r} liste mais jamais employe")

    for e in annexe:
        for champ in ("fichier", "sha256", "colonne", "index_ligne"):
            if e.get(champ) in (None, ""):
                erreurs.append(
                    f"annexe_provenance[{e.get('provenance_id','?')}] : "
                    f"champ de tracabilite '{champ}' vide")
    return erreurs


def main() -> int:
    config = charger_config()
    viols = scanner_source(config)
    print(f"T4 — lint de provenance sur {len(config['repertoires_scannes'])} "
          f"repertoire(s) + {len(config['fichiers_scannes'])} fichier(s)")
    print(f"  modules exclus (justifies) : {len(config['modules_exclus'])}")
    print(f"  exceptions declarees       : {len(config['exceptions'])}")
    if viols:
        print(f"\n{len(viols)} VIOLATION(S) :")
        for v in viols:
            print(f"  {v}")
        return 1
    print("\nAucune valeur normative en dur dans le code source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
