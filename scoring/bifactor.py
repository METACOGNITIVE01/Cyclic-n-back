"""§5.1 — Structure bifactorielle : fixation des saturations.

    z_j = lambda_jg . theta_g + lambda_js . theta_s(j) + eps_j

« Les lambda ne sont pas estimables sur un sujet unique : fixe-les a partir des
correlations inter-sub-tests calculees sur les echantillons de reference
telecharges. » (§5.1)

Consequence directe de R1 : SANS matrice de correlation issue d'un fichier
telecharge, aucune saturation n'existe, et le sub-test SORT DU MODELE. Le
rapport le dit. Aucune saturation par defaut n'est fournie.

L'ajustement utilise `semopy`. Une verification independante par moindres
carres sur la matrice de correlation est calculee en parallele : si les deux
divergent, on le signale plutot que de choisir en silence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd

from scoring.battery import Domaine
from scoring.provenance import (NoReferenceError, ProvenanceRecord,
                                ProvenanceRegistry, id_norme)


@dataclass
class Saturations:
    codes: list[str]
    lambda_g: dict[str, float]
    lambda_s: dict[str, float]
    psi: dict[str, float]
    domaines: dict[str, Domaine]
    source: str
    fichier: str
    sha256: str
    n_reference: int
    provenance_ids: list[str] = field(default_factory=list)
    exclus: dict[str, str] = field(default_factory=dict)
    ajustement: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "codes": self.codes, "lambda_g": self.lambda_g,
            "lambda_s": self.lambda_s, "psi": self.psi,
            "domaines": {k: v.value for k, v in self.domaines.items()},
            "source": self.source, "fichier": self.fichier, "sha256": self.sha256,
            "n_reference": self.n_reference, "provenance_ids": self.provenance_ids,
            "exclus": self.exclus, "ajustement": self.ajustement, "notes": self.notes,
        }


def _description_modele(codes: Sequence[str],
                        domaines: dict[str, Domaine]) -> str:
    """Syntaxe semopy d'un modele bifactoriel orthogonal."""
    lignes = ["G =~ " + " + ".join(codes)]
    par_dom: dict[Domaine, list[str]] = {}
    for c in codes:
        par_dom.setdefault(domaines[c], []).append(c)
    for dom, membres in sorted(par_dom.items(), key=lambda kv: kv[0].value):
        if len(membres) >= 2:            # un domaine a un seul indicateur n'est pas identifie
            lignes.append(f"{dom.value} =~ " + " + ".join(membres))
    facteurs = ["G"] + [d.value for d, m in sorted(par_dom.items(),
                                                   key=lambda kv: kv[0].value)
                        if len(m) >= 2]
    for i, a in enumerate(facteurs):
        lignes.append(f"{a} ~~ 1*{a}")
        for b in facteurs[i + 1:]:
            lignes.append(f"{a} ~~ 0*{b}")   # theta_g et theta_s orthogonaux (§5.1)
    return "\n".join(lignes)


def _ajuster_moindres_carres(R: np.ndarray, codes: Sequence[str],
                             domaines: dict[str, Domaine]
                             ) -> tuple[np.ndarray, np.ndarray, float]:
    """Verification independante : minimise ||R - (lg lg' + somme_s ls ls')||
    hors diagonale."""
    from scipy.optimize import minimize
    J = len(codes)
    doms = sorted({domaines[c].value for c in codes})
    idx = {d: np.array([domaines[c].value == d for c in codes], dtype=float)
           for d in doms}
    hors_diag = ~np.eye(J, dtype=bool)

    def implique(p: np.ndarray) -> np.ndarray:
        lg, ls = p[:J], p[J:]
        M = np.outer(lg, lg)
        for d in doms:
            v = ls * idx[d]
            M = M + np.outer(v, v)
        return M

    def objectif(p: np.ndarray) -> float:
        return float(np.sum((R - implique(p))[hors_diag] ** 2))

    p0 = np.concatenate([np.full(J, 0.6), np.full(J, 0.3)])
    bornes = [(0.05, 0.98)] * J + [(0.0, 0.95)] * J
    res = minimize(objectif, p0, bounds=bornes, method="L-BFGS-B",
                   options={"maxiter": 5000})
    return res.x[:J], res.x[J:], float(res.fun)


def saturations_depuis_correlations(
    R: pd.DataFrame, domaines: dict[str, Domaine], *,
    n_reference: int, source: str, fichier: str, sha256: str,
    registry: ProvenanceRegistry | None = None,
    tolerance_divergence: float = 0.15,
) -> Saturations:
    """Fixe les lambda a partir d'une matrice de correlation de reference."""
    codes = [c for c in R.columns if c in domaines]
    exclus = {c: "domaine non declare dans la batterie" for c in R.columns
              if c not in domaines}
    if len(codes) < 3:
        raise NoReferenceError(
            "bifactor",
            f"seulement {len(codes)} sub-test(s) dotes d'une correlation de "
            "reference : le modele bifactoriel n'est pas identifie")
    M = R.loc[codes, codes].to_numpy(dtype=float)
    if not np.allclose(M, M.T, atol=1e-8):
        raise ValueError("matrice de correlation non symetrique")
    if not np.allclose(np.diag(M), 1.0, atol=1e-6):
        raise ValueError("diagonale de la matrice de correlation != 1")

    notes: list[str] = []
    lg_ls: np.ndarray | None = None
    ajustement: dict[str, Any] = {}

    try:
        import semopy
        modele = semopy.Model(_description_modele(codes, domaines))
        modele.fit(cov=pd.DataFrame(M, index=codes, columns=codes),
                   n_samples=n_reference)
        est = modele.inspect()
        charge = est[(est["op"] == "~") | (est["op"] == "=~")]
        lg = np.array([_extraire(charge, "G", c) for c in codes])
        ls = np.array([_extraire(charge, domaines[c].value, c) for c in codes])
        lg_ls = (lg, ls)
        ajustement["semopy"] = {"objectif": float(getattr(modele, "last_result", None).fun)
                                if getattr(modele, "last_result", None) is not None else None}
    except Exception as exc:  # noqa: BLE001
        notes.append(f"semopy indisponible ou en echec ({type(exc).__name__}: {exc}) ; "
                     "l'ajustement par moindres carres sur la matrice de correlation "
                     "est utilise a la place")

    lg_mc, ls_mc, residu = _ajuster_moindres_carres(M, codes, domaines)
    ajustement["moindres_carres"] = {"residu_hors_diagonale": residu}

    if lg_ls is not None:
        lg, ls = lg_ls
        ecart = float(np.max(np.abs(np.abs(lg) - np.abs(lg_mc))))
        ajustement["ecart_max_semopy_vs_moindres_carres"] = ecart
        if ecart > tolerance_divergence:
            notes.append(
                f"semopy et les moindres carres divergent de {ecart:.3f} sur "
                "lambda_g (seuil " f"{tolerance_divergence}). Les moindres carres, "
                "plus transparents, sont retenus et l'ecart est signale.")
            lg, ls = lg_mc, ls_mc
            ajustement["retenu"] = "moindres_carres"
        else:
            ajustement["retenu"] = "semopy"
    else:
        lg, ls = lg_mc, ls_mc
        ajustement["retenu"] = "moindres_carres"

    lg, ls = np.abs(lg), np.abs(ls)
    communalite = lg ** 2 + ls ** 2
    trop = [codes[j] for j in range(len(codes)) if communalite[j] >= 0.99]
    for c in trop:
        exclus[c] = "communalite >= 0,99 : variance d'erreur non positive, cas de Heywood"
    garde = [j for j, c in enumerate(codes) if c not in exclus]
    if len(garde) < 3:
        raise NoReferenceError(
            "bifactor", "trop de cas de Heywood : modele bifactoriel inutilisable")

    codes_g = [codes[j] for j in garde]
    pids: list[str] = []
    if registry is not None:
        for j in garde:
            pid = id_norme(source, fichier, f"lambda_g_{codes[j]}", j)
            registry.enregistrer(ProvenanceRecord(
                provenance_id=pid, source_id=source, fichier=fichier, sha256=sha256,
                colonne=f"correlations -> lambda_g[{codes[j]}]", index_ligne=j,
                valeur=float(lg[j]),
                description=("saturation generale fixee sur la matrice de "
                             f"correlation de reference (N = {n_reference})")))
            pids.append(pid)

    return Saturations(
        codes=codes_g,
        lambda_g={codes[j]: float(lg[j]) for j in garde},
        lambda_s={codes[j]: float(ls[j]) for j in garde},
        psi={codes[j]: float(max(1.0 - communalite[j], 1e-6)) for j in garde},
        domaines={codes[j]: domaines[codes[j]] for j in garde},
        source=source, fichier=fichier, sha256=sha256, n_reference=n_reference,
        provenance_ids=pids, exclus=exclus, ajustement=ajustement, notes=notes)


def _extraire(charge: pd.DataFrame, facteur: str, indicateur: str) -> float:
    ligne = charge[(charge["rval"] == facteur) & (charge["lval"] == indicateur)]
    if ligne.empty:
        ligne = charge[(charge["lval"] == facteur) & (charge["rval"] == indicateur)]
    if ligne.empty:
        return 0.0
    return float(ligne["Estimate"].iloc[0])


def charger_saturations(registry: ProvenanceRegistry) -> Saturations:
    """Point d'entree du pipeline. Leve tant qu'aucune reference n'est telechargee."""
    raise NoReferenceError(
        "bifactor",
        "aucune matrice de correlation inter-sub-tests n'a pu etre calculee : "
        "les fichiers ICAR/SAPA et NCPT sont absents. Les saturations lambda ne "
        "sont donc pas fixables et AUCUN sub-test n'entre dans le modele (§5.1, R1).")
