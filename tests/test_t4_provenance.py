"""T4 — Provenance.

« Test qui echoue si une valeur normative apparait dans le code source ou dans
la sortie sans entree correspondante dans la table de provenance. »

Trois volets :
  * source  — aucun litteral numerique affecte a un identifiant normatif
  * sortie  — coherence normes_employees <-> annexe_provenance
  * garde-fou — le linter doit reellement detecter une violation plantee, sinon
    il ne prouve rien
"""
from __future__ import annotations

import json
import textwrap

import pytest

from scoring.lint_provenance import (charger_config, scanner_fichier,
                                     scanner_source, verifier_sortie)
from scoring.provenance import (NoReferenceError, ProvenanceRecord,
                                ProvenanceRegistry, id_norme)


def test_t4_aucune_norme_en_dur_dans_le_code():
    viols = scanner_source()
    if viols:
        detail = "\n".join(f"  {v}" for v in viols)
        pytest.fail(f"{len(viols)} valeur(s) normative(s) en dur :\n{detail}")
    print("\nT4 — aucune valeur normative en dur dans scoring/, report/, app/")


def test_t4_le_linter_detecte_une_violation_plantee(tmp_path):
    """Sans ce garde-fou, un linter qui ne trouve jamais rien passerait pour bon."""
    config = charger_config()
    mots = {m.lower() for m in config["mots_normatifs"]}
    faux = tmp_path / "faux_module.py"
    faux.write_text(textwrap.dedent("""
        moyenne_reference = 12.34
        ecart_type_reference = 3.21
        def f(percentile_50=7.5): ...
        TABLE = {"mean": 101.2, "sd": 14.8}
    """), encoding="utf-8")
    import scoring.lint_provenance as lp
    ancien = lp.RACINE
    lp.RACINE = tmp_path
    try:
        viols = scanner_fichier(faux, mots, set())
    finally:
        lp.RACINE = ancien
    noms = sorted(v.identifiant for v in viols)
    print(f"\nT4 (garde-fou) — violations detectees : {noms}")
    assert "moyenne_reference" in noms
    assert "ecart_type_reference" in noms
    assert "percentile_50" in noms
    assert "mean" in noms and "sd" in noms


def test_t4_sortie_norme_sans_provenance_echoue():
    rapport = {
        "normes_employees": [
            {"description": "moyenne NCPT empan direct", "valeur": 5.1,
             "provenance_id": "NCPT:battery17_norms.csv:mean:L42"},
            {"description": "ecart-type sans source", "valeur": 1.4},
        ],
        "annexe_provenance": [
            {"provenance_id": "NCPT:battery17_norms.csv:mean:L42",
             "fichier": "data/raw/ncpt/battery17_norms.csv", "sha256": "ab" * 32,
             "colonne": "mean", "index_ligne": 42},
        ],
    }
    erreurs = verifier_sortie(rapport)
    print(f"\nT4 — erreurs de sortie detectees : {erreurs}")
    assert any("sans provenance_id" in e for e in erreurs)


def test_t4_sortie_coherente_passe():
    rapport = {
        "normes_employees": [
            {"description": "moyenne", "valeur": 5.1, "provenance_id": "X:f.csv:mean:L1"},
        ],
        "annexe_provenance": [
            {"provenance_id": "X:f.csv:mean:L1", "fichier": "data/raw/f.csv",
             "sha256": "cd" * 32, "colonne": "mean", "index_ligne": 1},
        ],
    }
    assert verifier_sortie(rapport) == []


def test_t4_annexe_incomplete_echoue():
    rapport = {
        "normes_employees": [
            {"description": "m", "valeur": 1.0, "provenance_id": "X:f.csv:mean:L1"}],
        "annexe_provenance": [
            {"provenance_id": "X:f.csv:mean:L1", "fichier": "data/raw/f.csv",
             "sha256": "", "colonne": "mean", "index_ligne": 1}],
    }
    erreurs = verifier_sortie(rapport)
    assert any("sha256" in e for e in erreurs)


def test_t4_registre_refuse_une_norme_absente():
    reg = ProvenanceRegistry()
    with pytest.raises(NoReferenceError) as exc:
        reg.norme("NCPT:battery17_norms.csv:mean:L42")
    print(f"\nT4 — refus correct : {exc.value}")


def test_t4_norme_utilisable_seulement_apres_enregistrement():
    reg = ProvenanceRegistry()
    pid = id_norme("NCPT", "data/raw/ncpt/battery17_norms.csv", "mean", 42)
    nv = reg.enregistrer(ProvenanceRecord(
        provenance_id=pid, source_id="NCPT",
        fichier="data/raw/ncpt/battery17_norms.csv", sha256="ef" * 32,
        colonne="mean", index_ligne=42, valeur=5.1,
        description="moyenne de la cellule 18-29"))
    assert reg.table_annexe() == [], "aucun usage n'a encore ete inscrit"
    assert nv.get(reg) == 5.1
    annexe = reg.table_annexe()
    assert len(annexe) == 1 and annexe[0]["provenance_id"] == pid
    print(f"\nT4 — usage inscrit au registre : {annexe[0]['provenance_id']}")


def test_t4_normvalue_refuse_la_conversion_implicite():
    """Une NormValue ne doit pas pouvoir devenir un float sans passer au registre."""
    reg = ProvenanceRegistry()
    nv = reg.enregistrer(ProvenanceRecord(
        provenance_id="X:f.csv:mean:L0", source_id="X", fichier="data/raw/f.csv",
        sha256="00" * 32, colonne="mean", index_ligne=0, valeur=1.0,
        description="test"))
    with pytest.raises(TypeError):
        float(nv)
