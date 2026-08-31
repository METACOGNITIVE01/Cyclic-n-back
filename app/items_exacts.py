"""R4 — chemin ITEMS_EXACTS.

Les stimuli ICAR sont sous acces restreint (icar-project.org). Si un dossier
`icar_items/` fournit les items, ils sont utilises tels quels et le sub-test est
etiquete ITEMS_EXACTS. Sinon, le generateur prend le relais et le sub-test est
etiquete ITEMS_CLONES (§2). L'etiquette est portee jusque dans le rapport et
pilote la composante de non-equivalence du budget d'incertitude (§5.6).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scoring.battery import ModeItems
from scoring.provenance import sha256_fichier

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_ITEMS = RACINE / "icar_items"

#: nombre d'items attendus par echelle ICAR, d'apres la description publiee de
#: l'instrument (structure, pas norme).
ATTENDUS = {"C1": 11, "C2": 24, "K1": 9}

FICHIERS = {"C1": "matrix_reasoning.json",
            "C2": "three_dimensional_rotation.json",
            "K1": "letter_number_series.json"}


def disponibilite(code: str) -> dict[str, Any]:
    """Dit si le chemin ITEMS_EXACTS est ouvert pour ce sub-test, et pourquoi."""
    if code not in FICHIERS:
        return {"mode": ModeItems.CLONES.value, "disponible": False,
                "motif": f"{code} n'a pas de version ICAR exacte"}
    chemin = DOSSIER_ITEMS / FICHIERS[code]
    if not chemin.exists():
        return {
            "mode": ModeItems.CLONES.value, "disponible": False,
            "chemin_attendu": str(chemin.relative_to(RACINE)),
            "motif": ("les stimuli ICAR sont sous acces restreint (icar-project.org) "
                      "et ne sont pas fournis ici ; le generateur a regles prend le "
                      "relais et le sub-test est etiquete ITEMS_CLONES (R4)"),
        }
    try:
        items = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"mode": ModeItems.CLONES.value, "disponible": False,
                "motif": f"fichier illisible : {type(exc).__name__}: {exc}"}
    if not isinstance(items, list) or len(items) != ATTENDUS[code]:
        return {
            "mode": ModeItems.CLONES.value, "disponible": False,
            "motif": (f"{len(items) if isinstance(items, list) else '?'} items trouves, "
                      f"{ATTENDUS[code]} attendus : fichier incomplet, refuse plutot "
                      "que complete par des clones melanges (R4)"),
        }
    return {
        "mode": ModeItems.EXACTS.value, "disponible": True,
        "n_items": len(items),
        "fichier": str(chemin.relative_to(RACINE)),
        "sha256": sha256_fichier(chemin),
    }


def charger(code: str) -> list[dict[str, Any]]:
    d = disponibilite(code)
    if not d["disponible"]:
        raise FileNotFoundError(d["motif"])
    return json.loads((DOSSIER_ITEMS / FICHIERS[code]).read_text(encoding="utf-8"))
