"""§4.2 — Post-stratification de l'echantillon SAPA.

« L'echantillon SAPA est auto-selectionne. Ne l'utilise jamais brut comme
reference de population. »

Procedure :
  1. restreindre la reference a la tranche 19-23 ans (avant redressement) ;
  2. redresser (raking / IPF) sur les marges age x sexe x niveau d'education
     vers les marges de la population generale francaise des 18-29 ans ;
  3. conserver delta = moyenne brute - moyenne redressee. Le rapport DOIT
     afficher delta (§4.2).

Si les marges INSEE ne sont pas telechargeables, on construit un scenario
« population moins etudiante » a partir des marges d'education du fichier de
codes demographiques ICAR, et on le DOCUMENTE comme tel : c'est un scenario,
pas la population francaise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from scoring.provenance import NoReferenceError

TRANCHE_AGE_REFERENCE = (19, 23)


@dataclass
class ResultatRedressement:
    poids: np.ndarray
    moyenne_brute: float
    moyenne_redressee: float
    delta: float
    sd_brute: float
    sd_redressee: float
    n_avant_restriction: int
    n_apres_restriction: int
    n_effectif_kish: float
    marges_cibles: dict[str, dict[str, float]]
    origine_marges: str
    est_scenario: bool
    convergence: bool
    n_iterations: int
    ecart_marges_final: float
    notes: list[str] = field(default_factory=list)

    @property
    def sd_delta(self) -> float:
        """Erreur-type de delta, propagee depuis l'effectif efficace de Kish."""
        if self.n_effectif_kish <= 1:
            return float("inf")
        return float(self.sd_redressee / np.sqrt(self.n_effectif_kish))

    def to_dict(self) -> dict[str, Any]:
        return {
            "moyenne_brute": self.moyenne_brute,
            "moyenne_redressee": self.moyenne_redressee,
            "delta": self.delta,
            "sd_delta": self.sd_delta,
            "sd_brute": self.sd_brute, "sd_redressee": self.sd_redressee,
            "n_avant_restriction": self.n_avant_restriction,
            "n_apres_restriction": self.n_apres_restriction,
            "tranche_age_reference": list(TRANCHE_AGE_REFERENCE),
            "n_effectif_kish": self.n_effectif_kish,
            "origine_marges": self.origine_marges,
            "est_scenario": self.est_scenario,
            "marges_cibles": self.marges_cibles,
            "convergence": self.convergence,
            "n_iterations": self.n_iterations,
            "ecart_marges_final": self.ecart_marges_final,
            "notes": self.notes,
        }


def restreindre_tranche_age(df: pd.DataFrame, colonne_age: str,
                            tranche: tuple[int, int] = TRANCHE_AGE_REFERENCE
                            ) -> pd.DataFrame:
    """§4.2 — restriction a 19-23 ans AVANT redressement."""
    a = pd.to_numeric(df[colonne_age], errors="coerce")
    return df[(a >= tranche[0]) & (a <= tranche[1])].copy()


def raking(df: pd.DataFrame, marges: dict[str, dict[str, float]], *,
           max_iter: int = 200, tol: float = 1e-8) -> tuple[np.ndarray, bool, int, float]:
    """Iterative proportional fitting sur les marges fournies.

    `marges` : {colonne: {modalite: proportion cible}}. Les proportions de
    chaque variable doivent sommer a 1.
    """
    for var, cible in marges.items():
        if var not in df.columns:
            raise NoReferenceError(
                f"raking:{var}",
                f"la variable de marge {var!r} est absente des donnees telechargees")
        total = sum(cible.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"marges de {var} : somme {total:.6f} != 1")

    n = len(df)
    if n == 0:
        raise NoReferenceError("raking", "echantillon vide apres restriction d'age")
    w = np.ones(n, dtype=float)

    colonnes = {var: df[var].astype(str).to_numpy() for var in marges}
    for it in range(1, max_iter + 1):
        divergence_marges = 0.0
        for var, cible in marges.items():
            vals = colonnes[var]
            for modalite, p_cible in cible.items():
                masque = vals == str(modalite)
                poids_mod = w[masque].sum()
                if poids_mod <= 0:
                    raise NoReferenceError(
                        f"raking:{var}={modalite}",
                        "modalite presente dans les marges cibles mais absente de "
                        "l'echantillon telecharge : redressement impossible")
                facteur = (p_cible * w.sum()) / poids_mod
                w[masque] *= facteur
            for modalite, p_cible in cible.items():
                obtenu = w[colonnes[var] == str(modalite)].sum() / w.sum()
                divergence_marges = max(divergence_marges, abs(obtenu - p_cible))
        if divergence_marges < tol:
            return w * n / w.sum(), True, it, divergence_marges
    return w * n / w.sum(), False, max_iter, divergence_marges


def effectif_kish(w: np.ndarray) -> float:
    """Taille d'echantillon efficace : (somme w)^2 / somme w^2."""
    return float(w.sum() ** 2 / np.sum(w ** 2))


def redresser(df: pd.DataFrame, colonne_score: str, colonne_age: str,
              marges: dict[str, dict[str, float]], *,
              origine_marges: str, est_scenario: bool,
              tranche: tuple[int, int] = TRANCHE_AGE_REFERENCE
              ) -> ResultatRedressement:
    n0 = len(df)
    sous = restreindre_tranche_age(df, colonne_age, tranche)
    n1 = len(sous)
    if n1 < 100:
        raise NoReferenceError(
            "raking",
            f"{n1} sujets seulement dans la tranche {tranche[0]}-{tranche[1]} ans : "
            "reference trop mince, redressement refuse (R1)")

    y = pd.to_numeric(sous[colonne_score], errors="coerce").to_numpy(dtype=float)
    valide = np.isfinite(y)
    sous, y = sous[valide], y[valide]

    w, ok, it, ecart = raking(sous, marges)
    m_brute = float(np.mean(y))
    m_red = float(np.average(y, weights=w))
    sd_brute = float(np.std(y, ddof=1))
    var_red = float(np.average((y - m_red) ** 2, weights=w))
    notes: list[str] = []
    if est_scenario:
        notes.append(
            "Marges de scenario, PAS les marges de la population francaise : "
            "le redressement corrige la sur-representation etudiante de SAPA "
            "sans pretendre reproduire la population generale.")
    if not ok:
        notes.append(f"raking non converge apres {it} iterations "
                     f"(ecart de marge residuel {ecart:.2e})")

    return ResultatRedressement(
        poids=w, moyenne_brute=m_brute, moyenne_redressee=m_red,
        delta=m_brute - m_red, sd_brute=sd_brute,
        sd_redressee=float(np.sqrt(var_red)),
        n_avant_restriction=n0, n_apres_restriction=int(len(y)),
        n_effectif_kish=effectif_kish(w), marges_cibles=marges,
        origine_marges=origine_marges, est_scenario=est_scenario,
        convergence=ok, n_iterations=it, ecart_marges_final=ecart, notes=notes)


def marges_scenario_moins_etudiant(repartition_icar: dict[str, float],
                                   facteur_deplacement: float) -> dict[str, float]:
    """Scenario de repli documente (§4.2), a partir des marges ICAR observees.

    Deplace de la masse des niveaux d'education eleves vers les niveaux bas,
    d'un facteur EXPLICITE fourni par l'appelant. Ce n'est pas une estimation
    de la population francaise : c'est une hypothese de sensibilite.
    """
    if not (0.0 <= facteur_deplacement <= 1.0):
        raise ValueError("facteur_deplacement doit etre dans [0,1]")
    niveaux = list(repartition_icar)
    if len(niveaux) < 2:
        raise ValueError("au moins deux niveaux d'education requis")
    p = np.array([repartition_icar[k] for k in niveaux], dtype=float)
    p = p / p.sum()
    milieu = len(niveaux) // 2
    hauts, bas = slice(milieu, None), slice(0, milieu)
    transfert = p[hauts].sum() * facteur_deplacement
    p[hauts] *= (1.0 - facteur_deplacement)
    p[bas] += transfert * (p[bas] / p[bas].sum() if p[bas].sum() > 0
                           else np.full(milieu, 1.0 / milieu))
    return {k: float(v) for k, v in zip(niveaux, p / p.sum())}
