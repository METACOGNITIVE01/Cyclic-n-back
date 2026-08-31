"""§5.2 — Posterieur de theta_g par quadrature de Gauss-Hermite adaptative.

    p(theta_g | x) ~ prod_s [ integrale sur theta_s de prod_{j dans s}
                              f(z_j | theta_g, theta_s) phi(theta_s) ] . phi(theta_g)

Les theta_s (facteurs specifiques de domaine) sont integres analytiquement par
quadrature adaptative : pour chaque valeur de theta_g on centre les noeuds sur
le mode conditionnel et on les met a l'echelle de la courbure locale. La grille
de theta_g va de -4 a +4 par pas de 0,01 (§5.2).

Deux lois d'erreur (§5.3) :
  * "normale"   — eps_j ~ N(0, psi_j)
  * "student_t" — eps_j ~ t(nu) remis a l'echelle pour Var = psi_j

CORRECTION DE SURDISPERSION — note importante et volontairement visible.
Sous le modele lineaire-gaussien exact, Var(theta_g | z) NE DEPEND PAS de z :
c'est une propriete algebrique des modeles lineaires gaussiens, pas un choix.
Un profil heterogene et un profil plat de meme moyenne donneraient donc le meme
intervalle, ce que §5.2 exige explicitement de ne pas accepter. On applique donc
au posterieur RAPPORTE un facteur de surdispersion sqrt(max(1, phi)) avec
phi = D / ddl (§5.3) : l'information effective est reduite quand le profil est
plus disperse que le modele ne le predit. La correction n'aggrave jamais la
precision, elle ne fait qu'elargir. Le posterieur NOMINAL (non corrige) reste
calculable et rapporte a cote.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from scoring.battery import Domaine
from scoring.model import Observation, Posterior

N_NOEUDS_GH = 21


def grille_theta(theta_min: float = -4.0, theta_max: float = 4.0,
                 pas: float = 0.01) -> np.ndarray:
    n = int(round((theta_max - theta_min) / pas)) + 1
    return np.linspace(theta_min, theta_max, n)


def _log_densite_erreur(residu: np.ndarray, psi: np.ndarray,
                        loi: str, ddl: int) -> np.ndarray:
    """log f(residu) pour la loi d'erreur choisie, variance psi."""
    if loi == "normale":
        return -0.5 * (residu ** 2) / psi - 0.5 * np.log(2.0 * math.pi * psi)
    if loi == "student_t":
        if ddl <= 2:
            raise ValueError("ddl > 2 requis pour que la variance existe")
        echelle2 = psi * (ddl - 2.0) / ddl
        echelle = np.sqrt(echelle2)
        cst = (math.lgamma((ddl + 1) / 2.0) - math.lgamma(ddl / 2.0)
               - 0.5 * math.log(ddl * math.pi))
        return cst - np.log(echelle) - ((ddl + 1) / 2.0) * np.log1p(
            (residu ** 2) / (echelle2 * ddl))
    raise ValueError(f"loi d'erreur inconnue : {loi!r}")


def _log_integrale_domaine(theta: np.ndarray, z: np.ndarray, lg: np.ndarray,
                           ls: np.ndarray, psi: np.ndarray, loi: str, ddl: int,
                           n_noeuds: int = N_NOEUDS_GH) -> np.ndarray:
    """log de l'integrale sur theta_s, pour tout theta_g de la grille.

    Quadrature adaptative : mode et courbure conditionnels calcules
    analytiquement dans le cas gaussien, puis raffines par Newton dans le cas t.
    """
    G = theta.size
    # r_j(theta) = z_j - lambda_gj * theta        (G, J)
    r = z[None, :] - np.outer(theta, lg)

    # --- centre et echelle des noeuds (approximation gaussienne locale) -------
    B = 1.0 + np.sum(ls ** 2 / psi)               # precision conditionnelle
    u_hat = (r * (ls / psi)[None, :]).sum(axis=1) / B     # (G,)
    s_hat = 1.0 / math.sqrt(B)

    if loi == "student_t":
        # Deux pas de Newton sur le log-integrand pour recentrer sur le vrai mode.
        echelle2 = psi * (ddl - 2.0) / ddl
        for _ in range(2):
            d = r - np.outer(u_hat, ls)                       # (G, J)
            w = (ddl + 1.0) / (ddl * echelle2[None, :] + d ** 2)
            g1 = -u_hat + (w * d * ls[None, :]).sum(axis=1)
            g2 = -1.0 - (w * ls[None, :] ** 2).sum(axis=1)
            u_hat = u_hat - g1 / g2
        d = r - np.outer(u_hat, ls)
        w = (ddl + 1.0) / (ddl * echelle2[None, :] + d ** 2)
        courbure = 1.0 + (w * ls[None, :] ** 2).sum(axis=1)
        s_hat_v = 1.0 / np.sqrt(np.maximum(courbure, 1e-9))    # (G,)
    else:
        s_hat_v = np.full(G, s_hat)

    x, w_gh = np.polynomial.hermite.hermgauss(n_noeuds)        # (Q,)
    # u = u_hat + sqrt(2) * s_hat * x
    u = u_hat[:, None] + math.sqrt(2.0) * s_hat_v[:, None] * x[None, :]   # (G, Q)

    # log integrand = log phi(u) + somme_j log f(r_j - ls_j u)
    log_int = -0.5 * u ** 2 - 0.5 * math.log(2.0 * math.pi)                # (G, Q)
    for j in range(z.size):
        residu = r[:, j][:, None] - ls[j] * u                              # (G, Q)
        log_int = log_int + _log_densite_erreur(
            residu, np.full_like(residu, psi[j]), loi, ddl)

    # log( sqrt(2) s * somme_q w_q e^{x_q^2} integrand )
    termes = log_int + (x ** 2)[None, :] + np.log(w_gh)[None, :]
    m = termes.max(axis=1, keepdims=True)
    somme = np.exp(termes - m).sum(axis=1)
    return (m[:, 0] + np.log(somme) + 0.5 * math.log(2.0) + np.log(s_hat_v))


def _hdi(grille: np.ndarray, densite: np.ndarray, masse: float) -> tuple[float, float]:
    """Intervalle de plus haute densite, par seuillage sur la densite."""
    pas = float(grille[1] - grille[0])
    ordre = np.argsort(densite)[::-1]
    cum = np.cumsum(densite[ordre]) * pas
    k = int(np.searchsorted(cum, masse))
    k = min(k, ordre.size - 1)
    retenus = np.sort(grille[ordre[: k + 1]])
    return float(retenus[0]), float(retenus[-1])


def posterior_theta_g(observations: Sequence[Observation], *,
                      loi_erreur: str = "normale", ddl: int = 4,
                      masse_hdi: float = 0.90,
                      theta_min: float = -4.0, theta_max: float = 4.0,
                      pas: float = 0.01,
                      surdispersion: float = 1.0) -> Posterior:
    """Posterieur de theta_g. `surdispersion` = phi (1.0 = posterieur nominal).

    phi > 1 divise la log-vraisemblance par phi : l'information apportee par les
    donnees est reduite dans la proportion du desajustement observe.
    """
    obs = [o for o in observations if o.scorable]
    if not obs:
        raise ValueError("aucun sub-test scorable : pas de posterieur (R1)")
    if surdispersion < 1.0 - 1e-12:
        raise ValueError("la surdispersion ne peut pas retrecir le posterieur")

    theta = grille_theta(theta_min, theta_max, pas)
    log_vrais = np.zeros_like(theta)

    par_domaine: dict[Domaine, list[Observation]] = {}
    for o in obs:
        par_domaine.setdefault(o.domaine, []).append(o)

    for dom, groupe in sorted(par_domaine.items(), key=lambda kv: kv[0].value):
        z = np.array([o.z for o in groupe])
        lg = np.array([o.lambda_g for o in groupe])
        ls = np.array([o.lambda_s for o in groupe])
        psi = np.array([o.psi for o in groupe])
        log_vrais += _log_integrale_domaine(theta, z, lg, ls, psi, loi_erreur, ddl)

    log_post = log_vrais / surdispersion - 0.5 * theta ** 2
    log_post -= log_post.max()
    densite = np.exp(log_post)
    densite /= densite.sum() * (theta[1] - theta[0])

    pas_g = float(theta[1] - theta[0])
    moyenne = float(np.sum(theta * densite) * pas_g)
    var = float(np.sum((theta - moyenne) ** 2 * densite) * pas_g)
    bas, haut = _hdi(theta, densite, masse_hdi)

    return Posterior(grille=theta, densite=densite, moyenne=moyenne,
                     ecart_type=math.sqrt(max(var, 0.0)),
                     hdi_bas=bas, hdi_haut=haut, masse_hdi=masse_hdi,
                     loi_erreur=loi_erreur, surdispersion=surdispersion)


def posterior_gaussien_analytique(observations: Sequence[Observation]
                                  ) -> tuple[float, float]:
    """Solution exacte du cas lineaire-gaussien — sert a valider la quadrature.

    Sigma = Lg Lg' + somme_s (Ls_s Ls_s') + diag(psi) ; on conditionne theta_g.
    """
    obs = [o for o in observations if o.scorable]
    z = np.array([o.z for o in obs])
    lg = np.array([o.lambda_g for o in obs])
    ls = np.array([o.lambda_s for o in obs])
    psi = np.array([o.psi for o in obs])
    doms = sorted({o.domaine.value for o in obs})
    idx = {d: np.array([o.domaine.value == d for o in obs], dtype=float) for d in doms}

    Sigma = np.outer(lg, lg) + np.diag(psi)
    for d in doms:
        v = ls * idx[d]
        Sigma += np.outer(v, v)
    Sinv = np.linalg.inv(Sigma)
    # theta_g ~ N(0,1) a priori, Cov(theta_g, z) = lg  =>  regression gaussienne.
    var = float(1.0 - lg @ Sinv @ lg)
    moy = float(lg @ Sinv @ z)
    return moy, math.sqrt(max(var, 0.0))
