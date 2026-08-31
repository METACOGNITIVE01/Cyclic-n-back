"""Couche de calibrage (§4) — IRT, redressement, normes NCPT, UK Biobank, bifactoriel.

Chaque module doit (a) faire correctement son calcul quand on lui donne des
donnees, (b) REFUSER quand la source n'est pas telechargee, sans jamais
substituer de valeur (R1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from scoring.battery import Domaine
from scoring.bifactor import saturations_depuis_correlations
from scoring.irt import calibrer_echelle, eap
from scoring.ncpt_norms import (CelluleNormative, charger_normes,
                                coherence_normale_percentiles, fusionner_genres,
                                score_z)
from scoring.provenance import NoReferenceError, ProvenanceRegistry
from scoring.raking import (effectif_kish, marges_scenario_moins_etudiant,
                            redresser, restreindre_tranche_age)
from scoring.ukb_norms import DistributionUKB, charger_distribution, rang


# ------------------------------------------------------------------ IRT
@pytest.fixture(scope="module")
def donnees_2pl():
    rng = np.random.default_rng(0)
    n, m = 900, 11
    theta = rng.standard_normal(n)
    a = rng.uniform(1.0, 2.0, m)
    b = np.linspace(-1.5, 1.5, m)
    p = 1 / (1 + np.exp(-a[None, :] * (theta[:, None] - b[None, :])))
    x = (rng.random((n, m)) < p).astype(float)
    return {"x": x, "a": a, "b": b, "theta": theta}


def test_irt_retrouve_les_parametres(donnees_2pl):
    cal = calibrer_echelle(
        donnees_2pl["x"], [f"MR{i+1}" for i in range(11)],
        echelle="matrix_reasoning", fichier="data/raw/icar_sapa/x.csv",
        sha256="00" * 32, n_bootstrap=20)
    rb = float(np.corrcoef(cal.b(), donnees_2pl["b"])[0, 1])
    ra = float(np.corrcoef(cal.a(), donnees_2pl["a"])[0, 1])
    print(f"\nIRT — r(b estime, b vrai) = {rb:.3f} ; r(a estime, a vrai) = {ra:.3f}")
    assert rb > 0.95 and ra > 0.70
    assert all(p.se_a > 0 and p.se_b > 0 for p in cal.items)


def test_irt_eap_correle_au_theta_vrai(donnees_2pl):
    cal = calibrer_echelle(
        donnees_2pl["x"], [f"MR{i+1}" for i in range(11)],
        echelle="matrix_reasoning", fichier="f.csv", sha256="00" * 32,
        n_bootstrap=5)
    est = np.array([eap(donnees_2pl["x"][i], cal)[0] for i in range(300)])
    r = float(np.corrcoef(est, donnees_2pl["theta"][:300])[0, 1])
    print(f"IRT — r(EAP, theta vrai) = {r:.3f}")
    assert r > 0.80


def test_irt_refuse_un_echantillon_trop_petit(donnees_2pl):
    with pytest.raises(ValueError, match="trop peu"):
        calibrer_echelle(donnees_2pl["x"][:40], [f"MR{i+1}" for i in range(11)],
                         echelle="m", fichier="f", sha256="0" * 64, n_bootstrap=2)


def test_irt_refuse_un_item_sans_variance(donnees_2pl):
    x = donnees_2pl["x"].copy()
    x[:, 3] = 1.0
    with pytest.raises(ValueError, match="sans variance"):
        calibrer_echelle(x, [f"MR{i+1}" for i in range(11)], echelle="m",
                         fichier="f", sha256="0" * 64, n_bootstrap=2)


# ------------------------------------------------------- redressement (§4.2)
@pytest.fixture(scope="module")
def echantillon_biaise():
    rng = np.random.default_rng(3)
    n = 4000
    df = pd.DataFrame({
        "age": rng.integers(18, 30, n),
        "sexe": rng.choice(["H", "F"], n, p=[0.4, 0.6]),
        "educ": rng.choice(["bas", "moyen", "haut"], n, p=[0.10, 0.25, 0.65]),
    })
    effet = {"bas": -0.40, "moyen": 0.0, "haut": 0.35}
    df["score"] = [effet[e] + rng.normal() for e in df["educ"]]
    return df


def test_raking_corrige_le_biais_de_composition(echantillon_biaise):
    marges = {"sexe": {"H": .5, "F": .5},
              "educ": {"bas": .35, "moyen": .35, "haut": .30}}
    r = redresser(echantillon_biaise, "score", "age", marges,
                  origine_marges="scenario de test", est_scenario=True)
    print(f"\nRedressement — brute {r.moyenne_brute:+.3f}, redressee "
          f"{r.moyenne_redressee:+.3f}, delta {r.delta:+.3f} (± {r.sd_delta:.3f})")
    assert r.convergence
    assert abs(r.moyenne_redressee) < abs(r.moyenne_brute), \
        "le redressement doit rapprocher de 0 un echantillon sur-eduque"
    assert r.delta > 0.10
    assert r.sd_delta > 0
    assert any("scenario" in n.lower() for n in r.notes)


def test_raking_restreint_bien_19_23_avant_redressement(echantillon_biaise):
    sous = restreindre_tranche_age(echantillon_biaise, "age")
    assert sous["age"].min() >= 19 and sous["age"].max() <= 23
    marges = {"sexe": {"H": .5, "F": .5},
              "educ": {"bas": .35, "moyen": .35, "haut": .30}}
    r = redresser(echantillon_biaise, "score", "age", marges,
                  origine_marges="t", est_scenario=True)
    assert r.n_apres_restriction == len(sous)
    assert r.n_apres_restriction < r.n_avant_restriction


def test_raking_refuse_une_marge_absente(echantillon_biaise):
    with pytest.raises(NoReferenceError):
        redresser(echantillon_biaise, "score", "age",
                  {"revenu": {"bas": .5, "haut": .5}},
                  origine_marges="t", est_scenario=True)


def test_effectif_kish_inferieur_a_n():
    w = np.array([0.5, 1.0, 1.5, 2.0])
    assert effectif_kish(w) < w.size


def test_scenario_moins_etudiant_deplace_vers_le_bas():
    d = marges_scenario_moins_etudiant({"bas": .1, "moyen": .25, "haut": .65}, 0.5)
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert d["bas"] > 0.1 and d["haut"] < 0.65


# ------------------------------------------------------------ NCPT (§4.3)
def _cellule(percentiles: dict[float, float], m=50.0, s=10.0) -> CelluleNormative:
    return CelluleNormative("X", "b1", "data/raw/ncpt/b.csv", "0" * 64, "3",
                            5000.0, m, s, percentiles, [0])


def test_ncpt_fusion_genres_pondere_par_n():
    lignes = pd.DataFrame({"gender": ["male", "female"], "N": [3000., 1000.],
                           "mean": [52., 44.], "SD": [10., 10.],
                           "10th": [39., 31.], "25th": [45., 37.],
                           "50th": [52., 44.], "75th": [59., 51.],
                           "90th": [65., 57.]})
    m, s, perc, _ = fusionner_genres(lignes, "N", "mean", "SD")
    assert m == pytest.approx(50.0)          # (3000*52 + 1000*44)/4000
    assert s > 10.0, "la variance inter-groupes doit gonfler l'ecart-type"
    print(f"\nNCPT — fusion : mean={m:.2f}, SD={s:.3f} (intra 10,0)")


def test_ncpt_cellule_normale_passe_la_verification():
    perc = {p: 50.0 + 10.0 * norm.ppf(p) for p in (.10, .25, .50, .75, .90)}
    coh = coherence_normale_percentiles(_cellule(perc))
    assert coh["verifiable"] and not coh["depasse_seuil"]
    r = score_z(65.0, _cellule(perc))
    assert r["methode"] == "normale" and r["z"] == pytest.approx(1.5)


def test_ncpt_cellule_asymetrique_bascule_en_interpolation():
    """Queue haute etiree : la ligne reste strictement croissante mais n'est
    plus normale, donc l'interpolation monotone doit prendre le relais."""
    perc = {p: 50.0 + 10.0 * norm.ppf(p) for p in (.10, .25, .50, .75, .90)}
    perc[.75] = 50.0 + (perc[.75] - 50.0) * 1.4
    perc[.90] = 50.0 + (perc[.90] - 50.0) * 2.0
    assert list(perc.values()) == sorted(perc.values()), "fixture non monotone"
    c = _cellule(perc)
    coh = coherence_normale_percentiles(c)
    assert coh["depasse_seuil"], f"ecart max {coh['ecart_max']}"
    r = score_z(58.0, c)
    print(f"NCPT — ecart max {coh['ecart_max']:.3f} -> methode {r['methode']}")
    assert r["methode"] == "interpolation_monotone_percentiles"
    assert r["signale"] is True


def test_ncpt_score_inverse_pour_un_temps():
    perc = {p: 50.0 + 10.0 * norm.ppf(p) for p in (.10, .25, .50, .75, .90)}
    r = score_z(65.0, _cellule(perc), plus_haut_est_mieux=False)
    assert r["z"] == pytest.approx(-1.5) and r["score_inverse"] is True


def test_ncpt_refuse_sans_fichier():
    with pytest.raises(NoReferenceError, match="battery"):
        charger_normes(ProvenanceRegistry())


# ------------------------------------------------------- UK Biobank (§4.4)
def test_ukb_rang_monotone_et_arrondi():
    d = DistributionUKB(n=13000.0, table_frequence={k: 1000.0 for k in range(14)},
                        moyenne=6.5, ecart_type=2.0, mediane=6.0,
                        fichier="f.json", sha256="ab" * 32, provenance_ids=[])
    rangs = [rang(b, d)["rang_percentile_arrondi"] for b in range(14)]
    assert rangs == sorted(rangs)
    assert all(p % 5 == 0 for p in rangs)


def test_ukb_refuse_sans_table_de_frequence():
    d = DistributionUKB(n=100.0, table_frequence=None, moyenne=None,
                        ecart_type=None, mediane=None, fichier="f.json",
                        sha256="ab" * 32, provenance_ids=[])
    with pytest.raises(NoReferenceError, match="table de frequence"):
        rang(7, d)


def test_ukb_refuse_sans_fichier():
    with pytest.raises(NoReferenceError):
        charger_distribution(ProvenanceRegistry())


# --------------------------------------------------- bifactoriel (§5.1)
@pytest.fixture(scope="module")
def correlations_connues():
    codes = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    dom = {"C1": Domaine.INDUCTION, "C6": Domaine.INDUCTION,
           "C2": Domaine.SPATIAL, "C7": Domaine.SPATIAL,
           "C3": Domaine.MEMOIRE_TRAVAIL, "C4": Domaine.MEMOIRE_TRAVAIL,
           "C5": Domaine.MEMOIRE_TRAVAIL}
    lg = np.array([.80, .72, .68, .70, .74, .80, .68])
    ls = np.array([.30, .40, .44, .42, .38, .30, .42])
    M = np.outer(lg, lg)
    for d in set(dom.values()):
        v = ls * np.array([dom[c] == d for c in codes], float)
        M = M + np.outer(v, v)
    np.fill_diagonal(M, 1.0)
    return {"R": pd.DataFrame(M, index=codes, columns=codes), "dom": dom,
            "lg": lg, "ls": ls, "codes": codes}


def test_bifactor_retrouve_les_saturations(correlations_connues):
    reg = ProvenanceRegistry()
    s = saturations_depuis_correlations(
        correlations_connues["R"], correlations_connues["dom"],
        n_reference=5000, source="TEST", fichier="data/raw/t.csv",
        sha256="0" * 64, registry=reg)
    est = np.array([s.lambda_g[c] for c in correlations_connues["codes"]])
    ecart = float(np.max(np.abs(est - correlations_connues["lg"])))
    print(f"\nBifactoriel — ecart max sur lambda_g : {ecart:.4f} "
          f"(ajustement retenu : {s.ajustement['retenu']})")
    assert ecart < 0.02
    assert len(reg) == len(correlations_connues["codes"])
    assert all(0.0 < s.psi[c] < 1.0 for c in s.codes)


def test_bifactor_orthogonalite_et_provenance(correlations_connues):
    reg = ProvenanceRegistry()
    s = saturations_depuis_correlations(
        correlations_connues["R"], correlations_connues["dom"], n_reference=5000,
        source="TEST", fichier="data/raw/t.csv", sha256="0" * 64, registry=reg)
    for pid in s.provenance_ids:
        assert reg.norme(pid).valeur > 0
    assert s.n_reference == 5000


def test_bifactor_refuse_trop_peu_de_sub_tests(correlations_connues):
    R = correlations_connues["R"].iloc[:2, :2]
    with pytest.raises(NoReferenceError, match="identifie"):
        saturations_depuis_correlations(
            R, correlations_connues["dom"], n_reference=100, source="T",
            fichier="f", sha256="0" * 64)


def test_bifactor_charger_refuse_sans_reference():
    from scoring.bifactor import charger_saturations
    with pytest.raises(NoReferenceError, match="lambda"):
        charger_saturations(ProvenanceRegistry())


def test_ncpt_ligne_non_monotone_refuse_l_interpolation():
    """Une ligne dont les percentiles publies se croisent ne peut pas etre
    interpolee : on conserve le z normal et on le signale, on n'invente rien."""
    perc = {p: 50.0 + 10.0 * norm.ppf(p) for p in (.10, .25, .50, .75, .90)}
    perc[.10] = perc[.25] + 1.0          # croisement volontaire
    c = _cellule(perc)
    r = score_z(58.0, c)
    assert r["methode"] == "normale"
    assert r["signale"] is True
    assert r.get("interpolation_impossible") is True
    assert "strictement croissants" in r["motif"]
    print(f"\nNCPT — ligne incoherente : {r['motif'][:110]}")
