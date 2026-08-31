"""§4.4 — Norme UK Biobank, champ 20016 (Fluid intelligence score).

Score brut sur 13 -> RANG dans la distribution publiee.

Interdits explicites (§4.4, §9) :
  * AUCUNE correction d'age. L'echantillon a 40-69 ans ; l'extrapolation vers
    21 ans n'est pas identifiable a partir de cette source.
  * AUCUN QI n'en est tire.
  * Le rang est rapporte avec la mention explicite du groupe d'age de reference.

Toutes les valeurs viennent de data/raw/ukb_20016/field_20016_extraits.json,
lui-meme extrait du HTML telecharge et conserve a cote (R1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from scoring.provenance import (NoReferenceError, ProvenanceRecord,
                                ProvenanceRegistry, id_norme)

GROUPE_AGE_REFERENCE = "40-69"
SCORE_MAX = 13


@dataclass
class DistributionUKB:
    n: float
    table_frequence: dict[int, float] | None
    moyenne: float | None
    ecart_type: float | None
    mediane: float | None
    fichier: str
    sha256: str
    provenance_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "N": self.n, "moyenne": self.moyenne, "ecart_type": self.ecart_type,
            "mediane": self.mediane,
            "table_frequence": ({str(k): v for k, v in self.table_frequence.items()}
                                if self.table_frequence else None),
            "fichier": self.fichier, "sha256": self.sha256,
            "groupe_age_reference": GROUPE_AGE_REFERENCE,
            "provenance_ids": self.provenance_ids,
        }


def charger_distribution(registry: ProvenanceRegistry) -> DistributionUKB:
    fichiers = [m for m in registry.fichiers_de("UKB_20016")
                if m["nom"] == "field_20016_extraits.json"]
    if not fichiers:
        raise NoReferenceError(
            "UKB_20016",
            "aucun extrait du champ 20016 telecharge : K2 ne peut pas etre "
            "positionne et sort du rapport normatif (R1)")
    meta = fichiers[0]
    chemin = registry.racine / meta["chemin"]
    d = json.loads(chemin.read_text(encoding="utf-8"))

    if d.get("N") is None:
        raise NoReferenceError(
            "UKB_20016:N",
            "la page telechargee ne fournit pas d'effectif exploitable ; "
            "aucun rang ne peut etre calcule")

    table = d.get("table_frequence_0_13")
    table_i = {int(k): float(v) for k, v in table.items()} if table else None

    pids: list[str] = []
    for cle in ("N", "moyenne", "ecart_type", "mediane"):
        if d.get(cle) is not None:
            pid = id_norme("UKB_20016", meta["chemin"], cle, -1)
            registry.enregistrer(ProvenanceRecord(
                provenance_id=pid, source_id="UKB_20016", fichier=meta["chemin"],
                sha256=meta["sha256"], colonne=cle, index_ligne=-1,
                valeur=float(d[cle]),
                description=(f"{cle} du champ 20016, extrait de la page publiee "
                             f"(groupe d'age {GROUPE_AGE_REFERENCE})"),
                url=d.get("_url", "")))
            pids.append(pid)
    if table_i:
        for score, effectif in sorted(table_i.items()):
            pid = id_norme("UKB_20016", meta["chemin"], f"frequence_score_{score}", score)
            registry.enregistrer(ProvenanceRecord(
                provenance_id=pid, source_id="UKB_20016", fichier=meta["chemin"],
                sha256=meta["sha256"], colonne=f"frequence_score_{score}",
                index_ligne=score, valeur=float(effectif),
                description=f"effectif du score brut {score}/13 (champ 20016)",
                url=d.get("_url", "")))
            pids.append(pid)

    return DistributionUKB(
        n=float(d["N"]), table_frequence=table_i, moyenne=d.get("moyenne"),
        ecart_type=d.get("ecart_type"), mediane=d.get("mediane"),
        fichier=meta["chemin"], sha256=meta["sha256"], provenance_ids=pids)


def rang(brut: int, dist: DistributionUKB, arrondi_percentile: int = 5
         ) -> dict[str, Any]:
    """Rang du score brut dans la distribution publiee. Aucun QI, aucune correction."""
    if not (0 <= brut <= SCORE_MAX):
        raise ValueError(f"score brut hors 0-{SCORE_MAX} : {brut}")
    if not dist.table_frequence:
        raise NoReferenceError(
            "UKB_20016:table_frequence",
            "la page telechargee ne publie pas de table de frequence par valeur "
            "0-13 : le rang n'est pas calculable. Le score brut est rapporte seul.")

    total = sum(dist.table_frequence.values())
    if total <= 0:
        raise NoReferenceError("UKB_20016:table_frequence", "table de frequence vide")
    en_dessous = sum(v for k, v in dist.table_frequence.items() if k < brut)
    egaux = dist.table_frequence.get(brut, 0.0)
    # Rang moyen (correction de continuite pour les scores discrets).
    p = (en_dessous + 0.5 * egaux) / total
    p_arrondi = arrondi_percentile * round(p * 100 / arrondi_percentile)

    return {
        "score_brut": brut, "score_max": SCORE_MAX,
        "rang_percentile_arrondi": int(p_arrondi),
        "pas_arrondi": arrondi_percentile,
        "groupe_age_reference": GROUPE_AGE_REFERENCE,
        "correction_age_appliquee": False,
        "qi_derive": None,
        "mentions_obligatoires": [
            f"Rang etabli dans un echantillon de {GROUPE_AGE_REFERENCE} ans. "
            "Le sujet a 21 ans : ce rang N'EST PAS un rang parmi ses pairs d'age.",
            "Aucune correction d'age n'est appliquee : l'extrapolation de "
            f"{GROUPE_AGE_REFERENCE} ans vers 21 ans n'est pas identifiable a partir "
            "de cette source (§4.4).",
            "Aucun QI n'est derive de ce score.",
            "Items en anglais, limite stricte de 2 minutes, fidelite test-retest faible.",
        ],
        "provenance_ids": list(dist.provenance_ids),
        "N_reference": dist.n,
    }
