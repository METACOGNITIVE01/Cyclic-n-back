#!/usr/bin/env python3
"""CRIB-1 §1 — Verification prealable a toute passation.

Recalcule les SHA-256, reverifie les comptes de lignes observes, et REFUSE de
lancer le test si un fichier manque ou a change.

Sortie : data/derived/verification.json + code de retour.
  0 = toutes les sources obligatoires sont presentes et intactes
  1 = au moins une source manque ou est alteree  -> passation refusee
  2 = manifeste absent (fetch_norms.py n'a jamais abouti) -> passation refusee

Ce script n'ecrit jamais de valeur normative et n'en repare aucune. Il constate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from scoring.provenance import sha256_fichier  # noqa: E402
from fetch_norms import compter_lignes_csv  # noqa: E402
from scoring.battery import BATTERIE  # noqa: E402

MANIFEST = RACINE / "data" / "raw" / "MANIFEST.json"
SOURCES = RACINE / "config" / "sources.json"
SORTIE = RACINE / "data" / "derived" / "verification.json"


class VerificationEchouee(RuntimeError):
    pass


def verifier_fichier(meta: dict[str, Any]) -> dict[str, Any]:
    chemin = RACINE / meta["chemin"]
    res: dict[str, Any] = {
        "chemin": meta["chemin"],
        "source_id": meta.get("source_id"),
        "sha256_attendu": meta.get("sha256"),
    }
    if not chemin.exists():
        res.update(statut="MANQUANT", motif="le fichier declare au manifeste est absent du disque")
        return res

    res["octets_observes"] = chemin.stat().st_size
    res["sha256_observe"] = sha256_fichier(chemin)
    if res["sha256_observe"] != meta.get("sha256"):
        res.update(statut="ALTERE",
                   motif="le SHA-256 recalcule differe de celui enregistre au telechargement")
        return res
    if meta.get("octets") is not None and res["octets_observes"] != meta["octets"]:
        res.update(statut="ALTERE", motif="taille en octets differente")
        return res

    if "csv" in meta:
        try:
            observe = compter_lignes_csv(chemin)
        except Exception as exc:  # noqa: BLE001
            res.update(statut="ILLISIBLE", motif=f"{type(exc).__name__}: {exc}")
            return res
        res["n_lignes_enregistre"] = meta["csv"].get("n_lignes_donnees")
        res["n_lignes_observe"] = observe["n_lignes_donnees"]
        res["colonnes_observees"] = observe["colonnes"]
        if res["n_lignes_observe"] != res["n_lignes_enregistre"]:
            res.update(statut="ALTERE",
                       motif=(f"{res['n_lignes_observe']} lignes observees contre "
                              f"{res['n_lignes_enregistre']} enregistrees"))
            return res

    res["statut"] = "OK"
    return res


def verifier(strict: bool = True) -> dict[str, Any]:
    horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
    config = json.loads(SOURCES.read_text(encoding="utf-8"))
    declarees = {s["id"]: s for s in config["sources"]}

    rapport: dict[str, Any] = {
        "verifie_le": horodatage,
        "manifeste": str(MANIFEST.relative_to(RACINE)),
        "fichiers": [],
        "sources": {},
        "sous_tests_non_scorables": {},
        "passation_autorisee": False,
    }

    if not MANIFEST.exists():
        rapport["erreur_fatale"] = (
            "data/raw/MANIFEST.json absent : fetch_norms.py n'a jamais abouti. "
            "Aucune norme n'est disponible. Passation refusee."
        )
        rapport["code_retour"] = 2
        _consequences(rapport, declarees, presentes=set())
        return rapport

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fichiers = manifest.get("fichiers", {})

    for meta in sorted(fichiers.values(), key=lambda m: m["chemin"]):
        rapport["fichiers"].append(verifier_fichier(meta))

    presentes: set[str] = set()
    for sid, decl in declarees.items():
        du_src = [f for f in rapport["fichiers"] if f["source_id"] == sid]
        echec_fetch = manifest.get("echecs", {}).get(sid)
        if not du_src:
            rapport["sources"][sid] = {
                "statut": "ABSENTE",
                "obligatoire": decl.get("obligatoire", True),
                "motif": (f"telechargement echoue ({echec_fetch['categorie']}) : "
                          f"{echec_fetch['motif'][:200]}") if echec_fetch
                         else "aucun fichier enregistre pour cette source",
                "url": (echec_fetch or {}).get("url", ""),
            }
            continue
        mauvais = [f for f in du_src if f["statut"] != "OK"]
        if mauvais:
            rapport["sources"][sid] = {
                "statut": "ALTEREE", "obligatoire": decl.get("obligatoire", True),
                "n_fichiers": len(du_src),
                "fichiers_en_faute": [{"chemin": f["chemin"], "statut": f["statut"],
                                       "motif": f.get("motif", "")} for f in mauvais],
            }
            continue

        entree: dict[str, Any] = {
            "statut": "OK", "obligatoire": decl.get("obligatoire", True),
            "n_fichiers": len(du_src),
            "n_lignes_total_observe": sum(f.get("n_lignes_observe", 0) for f in du_src),
        }
        advisory = decl.get("advisory_n_sujets")
        if advisory is not None:
            entree["advisory_n_sujets"] = advisory
            entree["advisory_source"] = decl.get("advisory_source", "")
            entree["_note"] = (
                "L'attente ci-dessus provient de l'enonce humain, pas d'un fichier. "
                "Elle sert de garde-fou de coherence et n'est jamais utilisee au scoring."
            )
        rapport["sources"][sid] = entree
        presentes.add(sid)

    _consequences(rapport, declarees, presentes)

    obligatoires_ko = [sid for sid, d in declarees.items()
                       if d.get("obligatoire", True) and sid not in presentes]
    if obligatoires_ko:
        rapport["passation_autorisee"] = False
        rapport["code_retour"] = 1
        rapport["motif_refus"] = (
            "sources obligatoires indisponibles : " + ", ".join(sorted(obligatoires_ko))
        )
    elif strict and any(f["statut"] != "OK" for f in rapport["fichiers"]):
        rapport["passation_autorisee"] = False
        rapport["code_retour"] = 1
        rapport["motif_refus"] = "au moins un fichier est altere ou manquant"
    else:
        rapport["passation_autorisee"] = True
        rapport["code_retour"] = 0
    return rapport


def _consequences(rapport: dict[str, Any], declarees: dict[str, Any],
                  presentes: set[str]) -> None:
    """Traduit l'indisponibilite des sources en sub-tests non scorables (R1)."""
    for code, st in BATTERIE.items():
        if st.source_norme not in presentes:
            rapport["sous_tests_non_scorables"][code] = {
                "nom": st.nom_fr,
                "canal": st.canal.value,
                "source_norme_manquante": st.source_norme,
                "consequence": ("passation possible ; AUCUN score normatif. "
                                "Le rapport affichera « pas de reference » et exclura "
                                "ce sub-test du score (R1)."),
            }


def imprimer(rapport: dict[str, Any]) -> None:
    print("=" * 74)
    print("CRIB-1 — verification des normes avant passation")
    print("=" * 74)
    if "erreur_fatale" in rapport:
        print(f"\nERREUR FATALE : {rapport['erreur_fatale']}\n")
    else:
        print(f"\nFichiers verifies : {len(rapport['fichiers'])}")
        for f in rapport["fichiers"]:
            marque = "OK " if f["statut"] == "OK" else "!! "
            print(f"  {marque}{f['chemin']}  [{f['statut']}]")
            if f["statut"] != "OK":
                print(f"      {f.get('motif','')}")

    print("\nSources :")
    for sid, s in sorted(rapport["sources"].items()):
        obl = "obligatoire" if s.get("obligatoire") else "facultative"
        print(f"  {sid:<12} {s['statut']:<9} ({obl})")
        if s.get("motif"):
            print(f"      {s['motif'][:160]}")

    nsc = rapport["sous_tests_non_scorables"]
    if nsc:
        print(f"\nSub-tests SANS REFERENCE ({len(nsc)}) — exclus du score, jamais inventes :")
        for code, d in sorted(nsc.items()):
            print(f"  {code:<7} {d['nom']:<44} (source {d['source_norme_manquante']})")

    print("\n" + "-" * 74)
    if rapport["passation_autorisee"]:
        print("PASSATION AUTORISEE : toutes les sources obligatoires sont intactes.")
    else:
        print("PASSATION REFUSEE.")
        print(f"  motif : {rapport.get('motif_refus') or rapport.get('erreur_fatale')}")
        print("  La passation brute reste possible avec --autoriser-passation-sans-norme,")
        print("  mais aucun score normatif ne sera produit.")
    print("-" * 74)


def main() -> int:
    ap = argparse.ArgumentParser(description="CRIB-1 — verification des normes")
    ap.add_argument("--json", action="store_true", help="sortie JSON uniquement")
    ap.add_argument("--non-strict", action="store_true",
                    help="tolerer un fichier facultatif altere")
    args = ap.parse_args()

    rapport = verifier(strict=not args.non_strict)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps(rapport, indent=2, ensure_ascii=False, sort_keys=True),
                      encoding="utf-8")
    if args.json:
        print(json.dumps(rapport, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        imprimer(rapport)
        print(f"\nRapport ecrit : {SORTIE.relative_to(RACINE)}")
    return int(rapport["code_retour"])


if __name__ == "__main__":
    raise SystemExit(main())
