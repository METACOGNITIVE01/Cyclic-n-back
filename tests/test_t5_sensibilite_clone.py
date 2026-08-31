"""T5 — Sensibilite : le rapport change-t-il de conclusion quand r_clone passe
de 0,70 a 0,90 ? « Affiche la reponse. » (§8)

Le test affiche la reponse et verifie les proprietes de correction qui, elles,
ne sont pas negociables : sigma_clone doit decroitre quand r_clone croit, et
l'analyse doit couvrir toute la plage demandee.
"""
from __future__ import annotations

import numpy as np
import pytest

from scoring.sensitivity import analyse_r_clone, conclusion_qualitative
from scoring.simulation import profil_constant, profil_disperse


@pytest.fixture(scope="module")
def analyses():
    from scoring.simulation import plan_par_defaut
    plan = plan_par_defaut()
    commun = dict(graine=4242, doublons=[("C3", 0.40, 0.25), ("C4", 0.10, 0.30)])
    return {
        "plat": analyse_r_clone(profil_constant(plan, 0.5), **commun),
        "disperse": analyse_r_clone(profil_disperse(plan, 0.5, 1.5), **commun),
    }


def test_t5_reponse_affichee(analyses):
    print("\n" + "=" * 70)
    print("T5 — SENSIBILITE A r_clone (0,70 -> 0,90)")
    print("=" * 70)
    for nom, a in analyses.items():
        print(f"\nProfil {nom} :")
        print(f"  {a['reponse']}")
        for p in a["points"]:
            ii = p["intervalle_interne"]
            print(f"    r={p['r_clone']:.2f}  sigma_clone={p['sigma_clone_qi']:5.2f}  "
                  f"sigma_total={p['sigma_total_qi']:5.2f}  "
                  f"interne=[{ii['bas']:6.1f} ; {ii['haut']:6.1f}]  "
                  f"arrondi={p['conclusion']['intervalle_interne_arrondi']}")
    assert all("reponse" in a for a in analyses.values())


def test_t5_sigma_clone_decroit_avec_r(analyses):
    for nom, a in analyses.items():
        s = [p["sigma_clone_qi"] for p in a["points"]]
        assert all(b <= x + 1e-12 for x, b in zip(s, s[1:])), \
            f"{nom} : sigma_clone doit decroitre quand r_clone croit ({s})"


def test_t5_plage_complete(analyses):
    for a in analyses.values():
        rs = [p["r_clone"] for p in a["points"]]
        assert rs[0] == pytest.approx(0.70)
        assert rs[-1] == pytest.approx(0.90)
        assert len(rs) == 5


def test_t5_sigma_total_borne_par_les_extremes(analyses):
    for a in analyses.values():
        largeurs = [p["intervalle_interne"]["largeur"] for p in a["points"]]
        assert largeurs[0] == pytest.approx(a["largeur_interne_max_qi"])
        assert largeurs[-1] == pytest.approx(a["largeur_interne_min_qi"])


def test_t5_conclusion_est_grossiere_pas_decimale():
    """Un changement de 3e decimale ne doit pas compter comme changement."""
    from scoring.pipeline import scorer_noyau
    from scoring.simulation import plan_par_defaut
    plan = plan_par_defaut()
    obs = profil_constant(plan, 0.5)
    a = scorer_noyau(obs, graine=1, r_clone=0.800)
    b = scorer_noyau(obs, graine=1, r_clone=0.801)
    assert conclusion_qualitative(a) == conclusion_qualitative(b)
