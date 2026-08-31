"""§5.5 — Ensemble de ponderations admissibles W.

Familles :
  w_g      ~ lambda_jg / psi_j       (optimale pour estimer g)
  w_egal   = 1/J
  w_crit,k = ponderations optimales pour le critere k, derivees de coefficients
             de validite PUBLIES et effectivement retrouves. Sans source
             telechargee, cette famille est absente et le rapport le dit (R1).

Polytope : { w : 0,5 w_g,j <= w_j <= 1,5 w_g,j , somme w = 1 }.
S(w) = somme_j w_j z_j est lineaire en w : le min et le max sur le polytope sont
atteints en un sommet, il suffit donc de les enumerer.

La LARGEUR de [min_w S, max_w S] est une mesure directe de l'heterogeneite du
profil : elle vaut exactement 0 pour un profil plat (tous les z_j egaux, S(w) = z
pour tout w du simplexe).
"""
from __future__ import annotations

import itertools
from typing import Sequence

import numpy as np

from scoring.model import Observation


def poids_g(observations: Sequence[Observation]) -> np.ndarray:
    obs = [o for o in observations if o.scorable]
    w = np.array([o.lambda_g / o.psi for o in obs], dtype=float)
    if np.any(w <= 0):
        raise ValueError("poids w_g non positifs : lambda_g doit etre > 0")
    return w / w.sum()


def poids_egal(observations: Sequence[Observation]) -> np.ndarray:
    n = sum(1 for o in observations if o.scorable)
    return np.full(n, 1.0 / n)


def sommets_polytope(w_ref: np.ndarray, borne_basse: float, borne_haute: float,
                     tol: float = 1e-12) -> np.ndarray:
    """Sommets de { w : l <= w <= u, somme w = 1 } avec l = a*w_ref, u = b*w_ref.

    Une seule contrainte d'egalite : a un sommet, au plus une coordonnee est
    strictement interieure a ses bornes ; toutes les autres sont sur une borne.
    On enumere donc les affectations borne-basse / borne-haute des J-1 autres.
    """
    l = borne_basse * w_ref
    u = borne_haute * w_ref
    J = w_ref.size
    if l.sum() > 1.0 + tol or u.sum() < 1.0 - tol:
        raise ValueError(
            f"polytope vide : somme des bornes = [{l.sum():.4f}, {u.sum():.4f}], "
            "ne contient pas 1"
        )
    sommets: list[np.ndarray] = []
    vus: set[bytes] = set()

    def ajouter(w: np.ndarray) -> None:
        if np.any(w < l - 1e-9) or np.any(w > u + 1e-9):
            return
        cle = np.round(w, 12).tobytes()
        if cle not in vus:
            vus.add(cle)
            sommets.append(w.copy())

    for libre in range(J):
        autres = [k for k in range(J) if k != libre]
        for masque in itertools.product((0, 1), repeat=J - 1):
            w = np.empty(J)
            for pos, k in enumerate(autres):
                w[k] = u[k] if masque[pos] else l[k]
            w[libre] = 1.0 - w[autres].sum()
            ajouter(w)

    if not sommets:  # pragma: no cover - le test de non-vacuite l'exclut
        raise ValueError("aucun sommet trouve")
    return np.array(sommets)


def familles(observations: Sequence[Observation],
             poids_criteres: dict[str, np.ndarray] | None = None
             ) -> dict[str, np.ndarray]:
    """Les familles disponibles. `poids_criteres` doit venir de coefficients
    publies traces en provenance ; s'il est vide, la famille w_crit est absente."""
    f = {"w_g": poids_g(observations), "w_egal": poids_egal(observations)}
    for nom, w in (poids_criteres or {}).items():
        f[f"w_crit:{nom}"] = np.asarray(w, dtype=float)
    return f


def score_pondere(observations: Sequence[Observation], w: np.ndarray) -> float:
    z = np.array([o.z for o in observations if o.scorable])
    return float(np.dot(w, z))


def intervalle_ponderation(observations: Sequence[Observation],
                           borne_basse: float, borne_haute: float,
                           poids_criteres: dict[str, np.ndarray] | None = None
                           ) -> dict[str, object]:
    """[min_w S(w), max_w S(w)] sur W = familles U polytope."""
    obs = [o for o in observations if o.scorable]
    z = np.array([o.z for o in obs])
    w_ref = poids_g(obs)

    candidats: list[tuple[str, np.ndarray]] = list(familles(obs, poids_criteres).items())
    somm = sommets_polytope(w_ref, borne_basse, borne_haute)
    for i, w in enumerate(somm):
        candidats.append((f"sommet_{i}", w))

    scores = np.array([float(np.dot(w, z)) for _, w in candidats])
    i_min, i_max = int(np.argmin(scores)), int(np.argmax(scores))
    return {
        "min": float(scores[i_min]),
        "max": float(scores[i_max]),
        "largeur": float(scores[i_max] - scores[i_min]),
        "argmin": candidats[i_min][0],
        "argmax": candidats[i_max][0],
        "n_sommets": int(somm.shape[0]),
        "n_candidats": len(candidats),
        "familles_disponibles": sorted(familles(obs, poids_criteres)),
        "w_crit_disponible": bool(poids_criteres),
        "score_w_g": float(np.dot(w_ref, z)),
    }
