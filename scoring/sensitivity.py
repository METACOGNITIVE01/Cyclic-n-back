"""§5.6 / T5 — Analyse de sensibilite a r_clone.

r_clone est la correlation entre un sub-test clone et l'original dont la norme
provient. Elle est INCONNUE : aucune donnee ne la mesure ici. Elle est donc un
parametre explicite de configuration, balaye de 0,70 a 0,90, et le rapport
affiche si la CONCLUSION change sur cette plage.

« Conclusion » est defini ici de facon operationnelle : ce qu'un lecteur
retiendrait effectivement du rapport. Un changement de la 3e decimale n'est pas
un changement de conclusion ; un changement de palier d'affichage, ou de la
fourchette arrondie a 5 points de QI, en est un.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from scoring.model import Observation
from scoring.pipeline import ResultatNoyau, scorer_noyau


def _arrondi(x: float, pas: int) -> float:
    return float(pas * round(x / pas))


def conclusion_qualitative(r: ResultatNoyau, pas_arrondi: int = 5) -> dict[str, Any]:
    """Ce qu'un lecteur retient. Volontairement grossier (§9 : pas de decimale)."""
    ii, ie = r.intervalle_interne, r.intervalle_externe
    return {
        "palier_affichage": r.palier,
        "profil_mal_resume": bool(r.ppp["drapeau_profil_mal_resume"]),
        "intervalle_interne_arrondi": [_arrondi(ii.bas, pas_arrondi),
                                       _arrondi(ii.haut, pas_arrondi)],
        "intervalle_externe_arrondi": [_arrondi(ie.bas, pas_arrondi),
                                       _arrondi(ie.haut, pas_arrondi)],
        "interne_contient_100": bool(ii.bas <= 100.0 <= ii.haut),
        "budget_incomplet": not r.budget.complet,
    }


def analyse_r_clone(observations: Sequence[Observation], *,
                    r_min: float = 0.70, r_max: float = 0.90, pas: float = 0.05,
                    pas_arrondi: int = 5, **kwargs_scorer) -> dict[str, Any]:
    """Balaye r_clone et dit si la conclusion change (T5)."""
    if not (0.0 < r_min <= r_max <= 1.0):
        raise ValueError("plage de r_clone invalide")
    valeurs = [round(v, 10) for v in
               np.arange(r_min, r_max + pas / 2.0, pas).tolist()]
    points: list[dict[str, Any]] = []
    for r in valeurs:
        res = scorer_noyau(observations, r_clone=r, **kwargs_scorer)
        points.append({
            "r_clone": r,
            "sigma_clone_qi": res.budget.clone.valeur,
            "sigma_total_qi": res.budget.sigma_total,
            "intervalle_interne": res.intervalle_interne.to_dict(),
            "intervalle_externe": res.intervalle_externe.to_dict(),
            "conclusion": conclusion_qualitative(res, pas_arrondi),
        })

    conclusions = [p["conclusion"] for p in points]
    change = any(c != conclusions[0] for c in conclusions[1:])
    differences = sorted({
        cle for c in conclusions[1:] for cle in c
        if c[cle] != conclusions[0][cle]
    })
    largeurs = [p["intervalle_interne"]["largeur"] for p in points]

    return {
        "parametre": "r_clone",
        "plage": [r_min, r_max], "pas": pas,
        "points": points,
        "conclusion_change": bool(change),
        "champs_qui_changent": differences,
        "reponse": (
            "OUI — la conclusion du rapport change sur la plage "
            f"r_clone = {r_min:g} a {r_max:g} (champs affectes : "
            + ", ".join(differences) + ")."
            if change else
            f"NON — la conclusion du rapport est stable sur toute la plage "
            f"r_clone = {r_min:g} a {r_max:g}."
        ),
        "largeur_interne_min_qi": float(min(largeurs)),
        "largeur_interne_max_qi": float(max(largeurs)),
        "note": ("r_clone n'est mesure par aucune donnee de ce projet. "
                 "Cette analyse dit ce que l'ignorance sur r_clone coute, "
                 "elle ne la leve pas."),
    }
