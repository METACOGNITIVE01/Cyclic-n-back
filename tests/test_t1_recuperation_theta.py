"""T1 — Recuperation de theta.

On simule 2 000 sujets a theta_g connu, on leur administre virtuellement la
batterie (items binaires generes par les parametres IRT pour les sub-tests a
items, trait latent direct pour les autres), puis on estime theta_g avec le
meme estimateur que celui du pipeline reel.

Deux exigences (§8) :
  a) correlation theta_estime / theta_vrai > 0,90
  b) couverture empirique de l'intervalle a 90 % comprise entre 0,87 et 0,93

(b) est le test de CALIBRATION : il echoue si la quadrature, le HDI ou la
propagation d'erreur sont faux. Il n'est pas ajustable par le choix des
saturations. (a) depend en plus du niveau d'information de la batterie
virtuelle, fixe par le plan de simulation.

Note de portee : les parametres du plan de simulation ne sont PAS des normes
(R1). Ce test valide la machinerie d'estimation, pas le calibrage sur donnees
reelles — celui-ci exige les fichiers ICAR/SAPA, absents tant que
fetch_norms.py n'a pas abouti.
"""
from __future__ import annotations

import numpy as np
import pytest

from scoring.posterior import posterior_theta_g, posterior_gaussien_analytique
from scoring.simulation import observations_depuis, simuler_population

N_SUJETS = 2000


@pytest.fixture(scope="module")
def simulation():
    from scoring.simulation import plan_par_defaut
    plan = plan_par_defaut()
    rng = np.random.default_rng(20240117)
    sim = simuler_population(N_SUJETS, plan, rng)
    est = np.empty(N_SUJETS)
    bas = np.empty(N_SUJETS)
    haut = np.empty(N_SUJETS)
    for i in range(N_SUJETS):
        obs = observations_depuis(plan, sim["z"][i], sim["psi"], sim["se_mesure"])
        p = posterior_theta_g(obs, loi_erreur="normale", masse_hdi=0.90)
        est[i], bas[i], haut[i] = p.moyenne, p.hdi_bas, p.hdi_haut
    return {"plan": plan, "sim": sim, "est": est, "bas": bas, "haut": haut}


@pytest.mark.lent
def test_t1a_correlation_theta_estime_vrai(simulation):
    r = float(np.corrcoef(simulation["est"], simulation["sim"]["theta_g"])[0, 1])
    print(f"\nT1a — r(theta_estime, theta_vrai) = {r:.4f} sur {N_SUJETS} sujets")
    assert r > 0.90, f"correlation insuffisante : {r:.4f} <= 0,90"


@pytest.mark.lent
def test_t1b_couverture_intervalle_90(simulation):
    vrai = simulation["sim"]["theta_g"]
    couvert = (vrai >= simulation["bas"]) & (vrai <= simulation["haut"])
    c = float(np.mean(couvert))
    erreur_type = float(np.sqrt(0.90 * 0.10 / N_SUJETS))
    print(f"T1b — couverture empirique de l'HDI 90 % = {c:.4f} "
          f"(erreur-type de Monte-Carlo {erreur_type:.4f})")
    assert 0.87 <= c <= 0.93, f"couverture hors bornes : {c:.4f}"


@pytest.mark.lent
def test_t1c_quadrature_egale_solution_analytique(simulation):
    """La quadrature adaptative doit reproduire le cas lineaire-gaussien exact.

    La comparaison se fait sur LA MEME grille tronquee (-4..+4, imposee par
    §5.2) : la solution analytique fermee, elle, integre sur toute la droite.
    Pour un sujet dont le posterieur est centre pres d'un bord, la masse
    tronquee suffit a creer un ecart de l'ordre de 1e-5 qui ne dit rien sur la
    quadrature. On compare donc quadrature vs gaussienne EVALUEE ET NORMALISEE
    sur la meme grille — c'est l'egalite que la quadrature doit satisfaire.
    """
    plan, sim = simulation["plan"], simulation["sim"]
    ecarts_moy, ecarts_sd, ecarts_bruts = [], [], []
    for i in range(200):
        obs = observations_depuis(plan, sim["z"][i], sim["psi"], sim["se_mesure"])
        p = posterior_theta_g(obs)
        m, s = posterior_gaussien_analytique(obs)
        ecarts_bruts.append(abs(p.moyenne - m))

        g = p.grille
        d = np.exp(-0.5 * ((g - m) / s) ** 2)
        d /= d.sum() * (g[1] - g[0])
        pas = g[1] - g[0]
        m_tr = float(np.sum(g * d) * pas)
        sd_tr = float(np.sqrt(np.sum((g - m_tr) ** 2 * d) * pas))
        ecarts_moy.append(abs(p.moyenne - m_tr))
        ecarts_sd.append(abs(p.ecart_type - sd_tr))

    print(f"T1c — ecart max sur grille identique : moyenne {max(ecarts_moy):.2e}, "
          f"ecart-type {max(ecarts_sd):.2e}")
    print(f"      (ecart max contre la forme fermee non tronquee : "
          f"{max(ecarts_bruts):.2e}, du a la troncature a +/-4)")
    assert max(ecarts_moy) < 1e-9
    assert max(ecarts_sd) < 1e-9


@pytest.mark.lent
def test_t1d_biais_negligeable(simulation):
    """L'estimateur EAP retrecit vers 0 ; on verifie que la pente reste proche de 1."""
    vrai = simulation["sim"]["theta_g"]
    est = simulation["est"]
    pente = float(np.polyfit(vrai, est, 1)[0])
    print(f"T1d — pente de regression theta_estime sur theta_vrai = {pente:.4f} "
          "(retrecissement bayesien attendu, < 1)")
    assert 0.75 < pente < 1.05
