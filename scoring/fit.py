"""§5.3 — Ajustement individuel : statistique D, surdispersion, PPP.

Definitions retenues, explicitees parce qu'elles ne sont pas neutres :

  residu_j        = z_j - lambda_jg * E[theta_g | x]        (§5.5)
  var_residu_j    = lambda_js^2 + psi_j
                    (variance de ce residu sous le modele, theta_s marginalise)
  D               = somme_j residu_j^2 / var_residu_j
  ddl             = J - 1   (un parametre, theta_g, est estime)
  phi             = D / ddl  -> facteur de surdispersion

Le residu inclut deliberement la part de facteur specifique : c'est ce que §5.5
demande d'afficher (« ce qui s'ecarte de son propre niveau general »), et c'est
la meme quantite qui alimente D et l'indice d'adequation.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from scoring.model import Observation, Posterior


def residus(observations: Sequence[Observation], theta_g: float) -> np.ndarray:
    return np.array([o.z - o.lambda_g * theta_g for o in observations if o.scorable])


def variances_residus(observations: Sequence[Observation]) -> np.ndarray:
    return np.array([o.lambda_s ** 2 + o.psi for o in observations if o.scorable])


def statistique_D(observations: Sequence[Observation], theta_g: float) -> float:
    r = residus(observations, theta_g)
    v = variances_residus(observations)
    return float(np.sum(r ** 2 / v))


def degres_liberte(observations: Sequence[Observation]) -> int:
    return max(1, sum(1 for o in observations if o.scorable) - 1)


def surdispersion(observations: Sequence[Observation], theta_g: float) -> float:
    """phi = D / ddl. Ramene a >= 1 : la correction n'aiguise jamais."""
    return statistique_D(observations, theta_g) / degres_liberte(observations)


def ppp(observations: Sequence[Observation], posterior: Posterior,
        n_tirages: int, rng: np.random.Generator) -> dict[str, float]:
    """p-valeur predictive a posteriori sur D (§5.3).

    Pour chaque tirage theta^(m) du posterieur : on replique un profil sous le
    modele, on compare D(replique) a D(observe), tous deux evalues au meme
    theta^(m). PPP = Pr(D_rep >= D_obs). Une valeur basse signale un profil que
    le facteur unique resume mal.
    """
    obs = [o for o in observations if o.scorable]
    lg = np.array([o.lambda_g for o in obs])
    ls = np.array([o.lambda_s for o in obs])
    psi = np.array([o.psi for o in obs])
    z = np.array([o.z for o in obs])
    v = ls ** 2 + psi
    doms = [o.domaine.value for o in obs]
    dom_uniques = sorted(set(doms))
    idx_dom = {d: np.array([k for k, dd in enumerate(doms) if dd == d]) for d in dom_uniques}

    pas = float(posterior.grille[1] - posterior.grille[0])
    p = posterior.densite * pas
    p = np.clip(p, 0.0, None)
    p /= p.sum()
    tirages = rng.choice(posterior.grille, size=n_tirages, p=p)

    # profils repliques : z_rep = lg*theta + ls*theta_s(dom) + eps
    z_rep = lg[None, :] * tirages[:, None]
    for d, cols in idx_dom.items():
        ts = rng.standard_normal(n_tirages)
        z_rep[:, cols] += ls[None, cols] * ts[:, None]
    z_rep += rng.standard_normal((n_tirages, len(obs))) * np.sqrt(psi)[None, :]

    r_obs = z[None, :] - lg[None, :] * tirages[:, None]
    r_rep = z_rep - lg[None, :] * tirages[:, None]
    d_obs = (r_obs ** 2 / v[None, :]).sum(axis=1)
    d_rep = (r_rep ** 2 / v[None, :]).sum(axis=1)

    valeur = float(np.mean(d_rep >= d_obs))
    return {
        "ppp": valeur,
        "D_observe_moyen": float(np.mean(d_obs)),
        "D_replique_moyen": float(np.mean(d_rep)),
        "n_tirages": int(n_tirages),
        "drapeau_profil_mal_resume": bool(valeur < 0.05),
    }
