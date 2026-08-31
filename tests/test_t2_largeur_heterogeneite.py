"""T2 — Largeur et heterogeneite.

Deux profils de MEME moyenne, l'un plat, l'autre disperse de +/- 1,5 SD.
Le second doit produire :
  a) un intervalle interne plus large
  b) un intervalle externe NETTEMENT plus large
  c) un IA plus bas
« Si ce n'est pas le cas, le modele est faux » (§8).

Ce test est la raison d'etre de la correction de surdispersion documentee dans
scoring/posterior.py : sous le modele lineaire-gaussien nu, Var(theta_g | z) est
independante de z et (a) serait faux par construction.
"""
from __future__ import annotations

import numpy as np
import pytest

from scoring.pipeline import scorer_noyau
from scoring.posterior import posterior_theta_g
from scoring.simulation import profil_constant, profil_disperse

MOYENNE = 0.5
AMPLITUDE = 1.5


@pytest.fixture(scope="module")
def deux_profils():
    from scoring.simulation import plan_par_defaut
    plan = plan_par_defaut()
    plat = profil_constant(plan, MOYENNE)
    disperse = profil_disperse(plan, MOYENNE, AMPLITUDE)
    commun = dict(graine=771, doublons=[("C3", 0.40, 0.25), ("C4", 0.10, 0.30)])
    return {
        "plat": scorer_noyau(plat, **commun),
        "disperse": scorer_noyau(disperse, **commun),
        "obs_plat": plat, "obs_disperse": disperse,
    }


def test_t2_prealable_memes_moyennes(deux_profils):
    zp = np.mean([o.z for o in deux_profils["obs_plat"]])
    zd = np.mean([o.z for o in deux_profils["obs_disperse"]])
    assert abs(zp - zd) < 1e-12, "les deux profils doivent avoir la meme moyenne"


def test_t2a_intervalle_interne_plus_large(deux_profils):
    lp = deux_profils["plat"].intervalle_interne.largeur
    ld = deux_profils["disperse"].intervalle_interne.largeur
    print(f"\nT2a — largeur interne : plat {lp:.2f} QI, disperse {ld:.2f} QI")
    assert ld > lp, "l'intervalle interne du profil disperse doit etre plus large"


def test_t2b_intervalle_externe_nettement_plus_large(deux_profils):
    lp = deux_profils["plat"].intervalle_externe.largeur
    ld = deux_profils["disperse"].intervalle_externe.largeur
    print(f"T2b — largeur externe : plat {lp:.2f} QI, disperse {ld:.2f} QI "
          f"(rapport {ld/lp:.2f})")
    assert ld > 1.5 * lp, ("l'intervalle externe du profil disperse doit etre "
                           "NETTEMENT plus large (facteur > 1,5)")


def test_t2c_ia_plus_bas(deux_profils):
    ip = deux_profils["plat"].ia["ia"]
    idd = deux_profils["disperse"].ia["ia"]
    print(f"T2c — IA : plat {ip:.3f}, disperse {idd:.3f}")
    assert idd < ip, "l'IA du profil disperse doit etre plus bas"


def test_t2d_posterieur_nominal_insensible_documente(deux_profils):
    """Constat explicite : le posterieur NOMINAL, lui, ne bouge pas.

    Ce n'est pas un defaut cache, c'est une propriete algebrique du modele
    lineaire-gaussien. Le test la fige pour que personne ne la redecouvre par
    surprise, et justifie la correction de surdispersion appliquee au
    posterieur rapporte.
    """
    sp = deux_profils["plat"].posterior_nominal.ecart_type
    sd = deux_profils["disperse"].posterior_nominal.ecart_type
    print(f"T2d — sd du posterieur NOMINAL : plat {sp:.6f}, disperse {sd:.6f} "
          "(identiques : propriete du modele lineaire-gaussien)")
    assert abs(sp - sd) < 1e-9
    rp = deux_profils["plat"].posterior_rapporte.ecart_type
    rd = deux_profils["disperse"].posterior_rapporte.ecart_type
    print(f"      sd du posterieur RAPPORTE : plat {rp:.4f}, disperse {rd:.4f}")
    assert rd > rp


def test_t2e_student_t_aussi_plus_large(deux_profils):
    """La loi de Student, elle, elargit sans correction ad hoc (§5.3)."""
    sp = deux_profils["plat"].posterior_student.ecart_type
    sd = deux_profils["disperse"].posterior_student.ecart_type
    print(f"T2e — sd du posterieur Student-t(4) : plat {sp:.4f}, disperse {sd:.4f}")
    assert sd > sp
