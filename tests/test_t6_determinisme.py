"""T6 — Determinisme.

« Deux executions avec la meme graine et les memes reponses produisent des
sorties strictement identiques. » (§8)

Strictement = octet pour octet apres serialisation canonique. Les elements
intrinsequement variables (horodatages, versions, chemins) vivent dans l'annexe
de reproductibilite, hors du bloc compare ici.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from scoring.pipeline import resultat_en_dict, scorer_noyau
from scoring.simulation import (observations_depuis, plan_par_defaut,
                                profil_disperse, simuler_population)

GRAINE = 99


def _serialiser(d) -> str:
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _empreinte(d) -> str:
    return hashlib.sha256(_serialiser(d).encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def observations():
    return profil_disperse(plan_par_defaut(), 0.35, 1.1)


def test_t6_deux_executions_identiques(observations):
    kwargs = dict(graine=GRAINE, r_clone=0.80,
                  doublons=[("C3", 0.40, 0.25), ("C4", 0.10, 0.30)])
    a = resultat_en_dict(scorer_noyau(observations, **kwargs))
    b = resultat_en_dict(scorer_noyau(observations, **kwargs))
    ea, eb = _empreinte(a), _empreinte(b)
    print(f"\nT6 — empreinte execution 1 : {ea}")
    print(f"T6 — empreinte execution 2 : {eb}")
    assert ea == eb, "deux executions identiques doivent produire la meme sortie"


def test_t6_graine_differente_change_le_ppp(observations):
    """Garde-fou : si rien ne changeait jamais, T6 ne prouverait rien."""
    a = scorer_noyau(observations, graine=1)
    b = scorer_noyau(observations, graine=2)
    print(f"T6 (garde-fou) — PPP graine 1 = {a.ppp['ppp']:.4f}, "
          f"graine 2 = {b.ppp['ppp']:.4f}")
    assert a.ppp["ppp"] != b.ppp["ppp"], \
        "la graine doit reellement piloter le tirage predictif"
    # ... mais les quantites deterministes, elles, ne bougent pas.
    assert a.composite_z == b.composite_z
    assert a.posterior_nominal.ecart_type == b.posterior_nominal.ecart_type


def test_t6_simulation_reproductible():
    plan = plan_par_defaut()
    s1 = simuler_population(50, plan, np.random.default_rng(7))
    s2 = simuler_population(50, plan, np.random.default_rng(7))
    assert np.array_equal(s1["z"], s2["z"])
    assert np.array_equal(s1["theta_g"], s2["theta_g"])
    print("\nT6 — simulation reproductible a graine egale")


def test_t6_chaine_complete_reproductible():
    """De la simulation au resultat serialise, sans exception."""
    empreintes = []
    for _ in range(2):
        plan = plan_par_defaut()
        sim = simuler_population(200, plan, np.random.default_rng(2024))
        obs = observations_depuis(plan, sim["z"][0], sim["psi"], sim["se_mesure"])
        empreintes.append(_empreinte(resultat_en_dict(scorer_noyau(obs, graine=5))))
    print(f"T6 — empreinte de la chaine complete : {empreintes[0]}")
    assert empreintes[0] == empreintes[1]


def test_t6_serialisation_sans_horodatage(observations):
    """Le bloc deterministe ne doit contenir ni date ni chemin absolu."""
    texte = _serialiser(resultat_en_dict(scorer_noyau(observations, graine=GRAINE)))
    for interdit in ("/home/", "/tmp/", "T00:", "+00:00"):
        assert interdit not in texte, f"{interdit!r} ne doit pas apparaitre"
    for cle in ("horodatage", "timestamp", "date", "execute_le"):
        assert cle not in texte
    print("\nT6 — bloc deterministe exempt d'horodatage et de chemin")
