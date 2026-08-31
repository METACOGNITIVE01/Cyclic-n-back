"""R3 (pas de pseudo-precision) et §9 (ce que le programme ne doit jamais faire).

Ces tests lisent la SORTIE reellement produite, pas le code : c'est la sortie
qui est soumise aux interdits.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest

from scoring.model import Intervalle, ScoreNuInterdit


@pytest.fixture(scope="module")
def rapports(racine, tmp_path_factory):
    d = tmp_path_factory.mktemp("rapports")
    sorties = {}
    for nom, args in (("reel", []), ("demo", ["--demo-simulation"])):
        h, j = d / f"{nom}.html", d / f"{nom}.json"
        r = subprocess.run(
            [sys.executable, "-m", "report.build_report", *args,
             "--sortie-html", str(h), "--sortie-json", str(j)],
            cwd=racine, capture_output=True, text=True)
        assert r.returncode == 0, f"generation {nom} echouee :\n{r.stdout}\n{r.stderr}"
        sorties[nom] = {"html": h.read_text(encoding="utf-8"),
                        "json": json.loads(j.read_text(encoding="utf-8"))}
    return sorties


# --------------------------------------------------------------------- R3
def test_r3_intervalle_refuse_bornes_inversees():
    with pytest.raises(ValueError):
        Intervalle(point=0.0, bas=1.0, haut=-1.0)


def test_r3_tout_score_affiche_porte_un_intervalle(rapports):
    """Chaque valeur de score du bloc total est accompagnee de ses bornes."""
    for nom, r in rapports.items():
        if r["json"].get("resultat") is None:
            continue
        comp = r["json"]["resultat"]["composite"]
        for cle in ("intervalle_interne_qi", "intervalle_externe_qi"):
            iv = comp[cle]
            assert {"point", "bas", "haut", "masse"} <= set(iv), f"{nom}/{cle}"
            assert iv["bas"] <= iv["point"] <= iv["haut"], f"{nom}/{cle} incoherent"
            assert iv["haut"] > iv["bas"], f"{nom}/{cle} de largeur nulle"


def test_r3_pas_de_valeur_qi_nue_dans_le_html(rapports):
    """Aucune ligne du bloc total n'affiche un nombre sans crochets d'intervalle."""
    for nom, r in rapports.items():
        for valeur in re.findall(r'<span class="valeur">([^<]+)</span>', r["html"]):
            assert "[" in valeur and ";" in valeur, \
                f"{nom} : score affiche sans intervalle -> {valeur!r}"


def test_r3_composantes_manquantes_jamais_mises_a_zero(rapports):
    j = rapports["demo"]["json"]["resultat"]["budget_incertitude"]
    manquantes = [c for c in j["composantes"] if not c["disponible"]]
    for c in manquantes:
        assert c["sigma_qi"] is None, \
            f"{c['nom']} indisponible mais chiffree a {c['sigma_qi']}"
    if manquantes:
        assert j["sigma_total_est_borne_inferieure"] is True


# --------------------------------------------------------------------- §9
#: Une batterie clinique ne peut etre nommee que pour DIRE qu'on ne s'y compare
#: pas : liste des tournures de negation admises autour de la mention.
NEGATIONS = ("pas une equivalence", "aucune equivalence", "n'en propose aucune",
             "ne fait jamais", "annoncer une equivalence", "interdits")


def test_s9_aucune_equivalence_wais(rapports):
    for nom, r in rapports.items():
        texte = r["html"].lower()
        for interdit in ("wais", "wechsler", "wisc"):
            for m in re.finditer(interdit, texte):
                contexte = texte[max(0, m.start() - 320):m.start() + 90]
                assert any(n in contexte for n in NEGATIONS), \
                    f"{nom} : mention de {interdit!r} hors contexte de negation"


def test_s9_la_regle_wais_est_reellement_testee(rapports):
    """Garde-fou : le test precedent doit pouvoir echouer."""
    faux = "<p>Ce score correspond a un QI WAIS de 118.</p>".lower()
    m = re.search("wais", faux)
    contexte = faux[max(0, m.start() - 320):m.start() + 90]
    assert not any(n in contexte for n in NEGATIONS)


def test_s9_aucune_correction_age_ukb():
    from scoring.ukb_norms import GROUPE_AGE_REFERENCE, DistributionUKB, rang
    d = DistributionUKB(n=100000.0, table_frequence={k: 1000.0 for k in range(14)},
                        moyenne=6.0, ecart_type=2.0, mediane=6.0,
                        fichier="data/raw/ukb_20016/x.json", sha256="ab" * 32,
                        provenance_ids=[])
    r = rang(9, d)
    assert r["correction_age_appliquee"] is False
    assert r["qi_derive"] is None
    assert r["groupe_age_reference"] == GROUPE_AGE_REFERENCE
    assert any("21 ans" in m for m in r["mentions_obligatoires"])


def test_s9_percentile_jamais_a_la_decimale():
    from scoring.ukb_norms import DistributionUKB, rang
    d = DistributionUKB(n=1000.0, table_frequence={k: 100.0 for k in range(10)},
                        moyenne=None, ecart_type=None, mediane=None,
                        fichier="f.json", sha256="cd" * 32, provenance_ids=[])
    for brut in range(10):
        p = rang(brut, d, arrondi_percentile=5)["rang_percentile_arrondi"]
        assert isinstance(p, int) and p % 5 == 0, f"percentile non arrondi : {p}"


def test_s9_vitesse_et_contamination_hors_du_noyau():
    from scoring.battery import Canal, noyau, par_canal
    codes_noyau = {s.code for s in noyau()}
    for canal in (Canal.VITESSE, Canal.CONTAMINATION):
        for s in par_canal(canal):
            assert s.code not in codes_noyau, \
                f"{s.code} ({canal.value}) ne doit jamais entrer dans le noyau"
    assert codes_noyau == {"C1", "C2", "C3", "C4", "C5", "C6", "C7"}


def test_s9_echec_qualification_nest_pas_une_erreur():
    from app.session_logic import evaluer_qualification
    r = evaluer_qualification([True, False, False], 3)
    assert r["qualifie"] is False
    assert "PAS un echec" in r["consequence"]


def test_s9_verbal_reasoning_non_implemente():
    from scoring.battery import BATTERIE, EXCLUS
    assert "ICAR_verbal_reasoning" in EXCLUS
    assert not any("verbal_reasoning" in c.lower() for c in BATTERIE)
    assert "difficulte" in EXCLUS["ICAR_verbal_reasoning"]


def test_s9_sapa_jamais_brut():
    """Le redressement est obligatoire : la fonction exige des marges cibles."""
    import inspect
    from scoring.raking import redresser
    sig = inspect.signature(redresser)
    for p in ("marges", "origine_marges", "est_scenario"):
        assert p in sig.parameters, f"{p} doit etre exige par redresser()"
    assert sig.parameters["marges"].default is inspect.Parameter.empty


def test_rapport_reel_ne_produit_aucun_score(rapports):
    """Sans norme, le rapport reel n'affiche aucun total (R1)."""
    j = rapports["reel"]["json"]
    assert j["total"] is None
    assert j["normes_employees"] == []
    assert j["annexe_provenance"] == []
    assert "pas de reference" in rapports["reel"]["html"].lower()


def test_rapport_demo_est_estampille(rapports):
    h = rapports["demo"]["html"]
    assert "DONNEES SIMULEES" in h
    assert rapports["demo"]["json"]["meta"]["mode"] == "DEMONSTRATION SIMULEE"
    assert rapports["demo"]["json"]["annexe_provenance"] == []
