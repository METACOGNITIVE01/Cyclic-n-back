"""T3 — Profil plat : l'ambiguite de ponderation doit tomber sous 1 point de QI.

S(w) = somme_j w_j z_j. Si tous les z_j sont egaux a z, alors S(w) = z pour tout
w du simplexe : la largeur est exactement nulle. Le test verifie que c'est bien
ce que produit l'enumeration des sommets, y compris apres remise a l'echelle
theta_g (division par lambda_barre, qui varie, elle, avec w).
"""
from __future__ import annotations

import numpy as np
import pytest

from scoring.pipeline import scorer_noyau
from scoring.simulation import profil_constant, profil_disperse
from scoring.weights import intervalle_ponderation, poids_g, sommets_polytope


@pytest.mark.parametrize("valeur", [-1.0, 0.0, 0.5, 1.7])
def test_t3_ambiguite_nulle_sur_profil_plat(valeur):
    from scoring.simulation import plan_par_defaut
    obs = profil_constant(plan_par_defaut(), valeur)
    r = scorer_noyau(obs, graine=3)
    print(f"\nT3 — profil plat a z = {valeur:+.1f} : "
          f"ambiguite de ponderation = {r.largeur_ambiguite_qi:.6f} pt QI")
    assert r.largeur_ambiguite_qi < 1.0


def test_t3_ambiguite_non_nulle_sur_profil_disperse():
    """Garde-fou : le test T3 doit pouvoir echouer. Un profil disperse le montre."""
    from scoring.simulation import plan_par_defaut
    obs = profil_disperse(plan_par_defaut(), 0.5, 1.5)
    r = scorer_noyau(obs, graine=3)
    print(f"T3 (garde-fou) — profil disperse : "
          f"ambiguite = {r.largeur_ambiguite_qi:.2f} pts QI")
    assert r.largeur_ambiguite_qi > 1.0


def test_t3_polytope_bien_forme():
    """Les sommets doivent respecter les bornes et sommer a 1."""
    from scoring.simulation import plan_par_defaut
    obs = profil_constant(plan_par_defaut(), 0.0)
    w_g = poids_g(obs)
    s = sommets_polytope(w_g, 0.5, 1.5)
    assert np.allclose(s.sum(axis=1), 1.0), "tout sommet doit sommer a 1"
    assert np.all(s >= 0.5 * w_g - 1e-9), "borne basse violee"
    assert np.all(s <= 1.5 * w_g + 1e-9), "borne haute violee"
    print(f"\nT3 — {s.shape[0]} sommets, tous admissibles")


def test_t3_largeur_croit_avec_la_dispersion():
    """La largeur d'ambiguite est bien une mesure d'heterogeneite."""
    from scoring.simulation import plan_par_defaut
    plan = plan_par_defaut()
    largeurs = []
    for amp in (0.0, 0.25, 0.5, 1.0, 1.5):
        obs = (profil_constant(plan, 0.5) if amp == 0.0
               else profil_disperse(plan, 0.5, amp))
        largeurs.append(intervalle_ponderation(obs, 0.5, 1.5)["largeur"])
    print("\nT3 — largeur d'ambiguite par amplitude :",
          [f"{l:.4f}" for l in largeurs])
    assert all(b >= a - 1e-12 for a, b in zip(largeurs, largeurs[1:])), \
        "la largeur doit croitre avec la dispersion"
    assert largeurs[0] < 1e-12
