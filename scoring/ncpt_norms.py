"""§4.3 — Normes NCPT.

Pour chaque sub-test clone, on lit la ligne de `battery*_norms.csv`
correspondant a :
    age              = « 18-29 »
    gender           = collapse (moyenne ponderee par N des lignes homme et femme)
    education_level  = celui declare par le sujet

Si plusieurs batteries contiennent le meme sub-test, on choisit celle dont le N
de la cellule est le plus grand, et on le note.

Puis : z = (x - mean) / SD, et VERIFICATION de coherence avec les percentiles
10/25/50/75/90 de la meme ligne. Si l'ecart entre le z normal-theorique et le z
implicite aux percentiles depasse 0,15, on utilise une interpolation monotone
sur les cinq percentiles plutot que la normale, et on le signale (§4.3).

Aucune valeur n'est ecrite en dur : tout provient des fichiers telecharges, via
le registre de provenance (R1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.stats import norm

from scoring.provenance import (NoReferenceError, ProvenanceRecord,
                                ProvenanceRegistry, id_norme)

BANDE_AGE = "18-29"
SEUIL_COHERENCE_Z = 0.15
PERCENTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
COLONNES_PERCENTILES = ("10th", "25th", "50th", "75th", "90th")


@dataclass
class CelluleNormative:
    sub_test: str
    batterie: str
    fichier: str
    sha256: str
    education_level: str
    n_total: float
    moyenne: float
    ecart_type: float
    percentiles: dict[float, float]
    lignes_sources: list[int]
    provenance_ids: list[str] = field(default_factory=list)
    genres_fusionnes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub_test": self.sub_test, "batterie": self.batterie,
            "fichier": self.fichier, "sha256": self.sha256,
            "education_level": self.education_level,
            "N": self.n_total, "mean": self.moyenne, "SD": self.ecart_type,
            "percentiles": {str(k): v for k, v in self.percentiles.items()},
            "lignes_sources": self.lignes_sources,
            "provenance_ids": self.provenance_ids,
            "genres_fusionnes": self.genres_fusionnes,
            "notes": self.notes,
        }


def charger_normes(registry: ProvenanceRegistry) -> pd.DataFrame:
    """Concatene tous les battery*_norms.csv verifies. Leve si aucun n'existe."""
    fichiers = [m for m in registry.fichiers_de("NCPT")
                if m["nom"].lower().endswith(".csv") and "norms" in m["nom"].lower()]
    if not fichiers:
        raise NoReferenceError(
            "NCPT",
            "aucun fichier battery*_norms.csv telecharge : tous les sub-tests "
            "normes sur NCPT sortent du score (R1)")
    morceaux = []
    for meta in sorted(fichiers, key=lambda m: m["nom"]):
        chemin = registry.racine / meta["chemin"]
        d = pd.read_csv(chemin)
        d["_fichier"] = meta["chemin"]
        d["_sha256"] = meta["sha256"]
        d["_ligne_csv"] = np.arange(len(d))
        morceaux.append(d)
    return pd.concat(morceaux, ignore_index=True)


def _colonne(df: pd.DataFrame, *noms: str) -> str:
    for n in noms:
        if n in df.columns:
            return n
    raise NoReferenceError(
        "NCPT:colonne",
        f"aucune des colonnes {noms} n'est presente dans les fichiers telecharges ; "
        f"colonnes disponibles : {list(df.columns)}")


def _cdf_monotone(valeurs: Sequence[float], probas: Sequence[float]):
    v = np.asarray(valeurs, dtype=float)
    p = np.asarray(probas, dtype=float)
    if np.any(np.diff(v) <= 0):
        raise ValueError("percentiles non strictement croissants : ligne incoherente")
    return PchipInterpolator(v, p, extrapolate=False)


def fusionner_genres(lignes: pd.DataFrame, col_n: str, col_mean: str,
                     col_sd: str) -> tuple[float, float, dict[float, float], list[str]]:
    """Collapse des lignes homme/femme, pondere par N.

    Moyenne  : moyenne ponderee.
    Variance : variance intra + variance inter (formule de decomposition), pas
               une simple moyenne des SD — qui sous-estimerait.
    Percentiles : inversion de la CDF MELANGEE, pas une moyenne de percentiles.
    """
    n = lignes[col_n].to_numpy(dtype=float)
    m = lignes[col_mean].to_numpy(dtype=float)
    s = lignes[col_sd].to_numpy(dtype=float)
    if np.any(n <= 0) or np.any(s < 0):
        raise ValueError("N <= 0 ou SD < 0 dans une cellule normative")
    ntot = float(n.sum())
    m_pool = float(np.sum(n * m) / ntot)
    var_pool = float(np.sum(n * (s ** 2 + m ** 2)) / ntot - m_pool ** 2)
    notes: list[str] = []

    perc_pool: dict[float, float] = {}
    dispo = [c for c in COLONNES_PERCENTILES if c in lignes.columns]
    if len(dispo) == len(COLONNES_PERCENTILES):
        try:
            grilles, cdfs = [], []
            for _, ligne in lignes.iterrows():
                v = [float(ligne[c]) for c in COLONNES_PERCENTILES]
                cdfs.append(_cdf_monotone(v, PERCENTILES))
                grilles.append(v)
            lo = min(min(g) for g in grilles)
            hi = max(max(g) for g in grilles)
            x = np.linspace(lo, hi, 2001)
            melange = np.zeros_like(x)
            for poids, f in zip(n / ntot, cdfs):
                val = f(x)
                val = np.where(np.isnan(val), np.where(x < f.x[0], 0.0, 1.0), val)
                melange += poids * val
            melange = np.maximum.accumulate(melange)
            for p in PERCENTILES:
                perc_pool[p] = float(np.interp(p, melange, x))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"percentiles fusionnes indisponibles : {type(exc).__name__}: {exc}")
    else:
        notes.append(
            f"colonnes de percentiles incompletes ({dispo}) : "
            "la verification de coherence normale/percentiles ne pourra pas etre faite")
    return m_pool, float(np.sqrt(max(var_pool, 0.0))), perc_pool, notes


def selectionner_cellule(df: pd.DataFrame, sub_test: str, education_level: str,
                         registry: ProvenanceRegistry,
                         bande_age: str = BANDE_AGE) -> CelluleNormative:
    col_sub = _colonne(df, "subtest_name")
    col_age = _colonne(df, "age", "age_band", "age_group")
    col_edu = _colonne(df, "education_level", "education")
    col_gen = _colonne(df, "gender", "sex")
    col_n = _colonne(df, "N", "n")
    col_mean = _colonne(df, "mean", "Mean")
    col_sd = _colonne(df, "SD", "sd", "std")

    sel = df[(df[col_sub].astype(str) == sub_test)
             & (df[col_age].astype(str) == bande_age)
             & (df[col_edu].astype(str) == str(education_level))]
    if sel.empty:
        raise NoReferenceError(
            f"NCPT:{sub_test}",
            f"aucune ligne pour subtest={sub_test!r}, age={bande_age!r}, "
            f"education_level={education_level!r} dans les fichiers telecharges")

    col_bat = "specific_subtest_id" if "specific_subtest_id" in df.columns else "_fichier"
    meilleures, meilleur_n = None, -1.0
    for batterie, groupe in sel.groupby(col_bat, sort=True):
        n = float(groupe[col_n].astype(float).sum())
        if n > meilleur_n:
            meilleur_n, meilleures = n, (str(batterie), groupe)
    batterie, groupe = meilleures  # type: ignore[misc]

    n_batteries = sel[col_bat].nunique()
    m, s, perc, notes = fusionner_genres(groupe, col_n, col_mean, col_sd)
    if n_batteries > 1:
        notes.append(
            f"{n_batteries} batteries contiennent {sub_test} ; celle retenue "
            f"({batterie}) a le plus grand N de cellule : {meilleur_n:g}")

    fichier = str(groupe["_fichier"].iloc[0])
    sha = str(groupe["_sha256"].iloc[0])
    lignes = [int(v) for v in groupe["_ligne_csv"].tolist()]
    genres = sorted(str(g) for g in groupe[col_gen].tolist())

    pids: list[str] = []
    for colonne, valeur, desc in (
        (col_mean, m, f"moyenne NCPT collapsee ({sub_test}, {bande_age}, educ {education_level})"),
        (col_sd, s, f"ecart-type NCPT collapse ({sub_test}, {bande_age}, educ {education_level})"),
        (col_n, meilleur_n, f"N de la cellule NCPT ({sub_test}, {bande_age})"),
    ):
        pid = id_norme("NCPT", fichier, colonne, lignes[0])
        registry.enregistrer(ProvenanceRecord(
            provenance_id=pid, source_id="NCPT", fichier=fichier, sha256=sha,
            colonne=colonne, index_ligne=lignes[0], valeur=float(valeur),
            description=desc + f" ; lignes fusionnees {lignes}"))
        pids.append(pid)
    for p, col in zip(PERCENTILES, COLONNES_PERCENTILES):
        if p in perc:
            pid = id_norme("NCPT", fichier, col, lignes[0])
            registry.enregistrer(ProvenanceRecord(
                provenance_id=pid, source_id="NCPT", fichier=fichier, sha256=sha,
                colonne=col, index_ligne=lignes[0], valeur=float(perc[p]),
                description=f"percentile {int(p*100)} collapse ({sub_test}, {bande_age})"))
            pids.append(pid)

    return CelluleNormative(
        sub_test=sub_test, batterie=batterie, fichier=fichier, sha256=sha,
        education_level=str(education_level), n_total=meilleur_n,
        moyenne=m, ecart_type=s, percentiles=perc, lignes_sources=lignes,
        provenance_ids=pids, genres_fusionnes=genres, notes=notes)


def coherence_normale_percentiles(cellule: CelluleNormative) -> dict[str, Any]:
    """Compare, sur la ligne elle-meme, z normal-theorique et z des percentiles."""
    if len(cellule.percentiles) < len(PERCENTILES):
        return {"verifiable": False,
                "motif": "percentiles incomplets dans le fichier telecharge",
                "ecart_max": None, "depasse_seuil": None}
    if cellule.ecart_type <= 0:
        return {"verifiable": False, "motif": "SD nul ou negatif",
                "ecart_max": None, "depasse_seuil": None}
    ecarts = {}
    for p in PERCENTILES:
        z_normal = (cellule.percentiles[p] - cellule.moyenne) / cellule.ecart_type
        ecarts[f"p{int(p*100)}"] = float(z_normal - norm.ppf(p))
    emax = float(max(abs(v) for v in ecarts.values()))
    return {
        "verifiable": True, "ecarts_z": ecarts, "ecart_max": emax,
        "seuil": SEUIL_COHERENCE_Z,
        "depasse_seuil": bool(emax > SEUIL_COHERENCE_Z),
    }


def score_z(brut: float, cellule: CelluleNormative,
            plus_haut_est_mieux: bool = True) -> dict[str, Any]:
    """z du sujet, par la normale ou par interpolation monotone des percentiles."""
    coh = coherence_normale_percentiles(cellule)
    if cellule.ecart_type <= 0:
        raise NoReferenceError(f"NCPT:{cellule.sub_test}",
                               "ecart-type normatif nul : z non calculable")
    z_normal = (brut - cellule.moyenne) / cellule.ecart_type

    resultat: dict[str, Any] = {
        "brut": brut, "z_normal": float(z_normal),
        "coherence": coh, "methode": "normale",
        "z": float(z_normal), "signale": False,
        "provenance_ids": list(cellule.provenance_ids),
    }

    if coh.get("depasse_seuil"):
        v = [cellule.percentiles[p] for p in PERCENTILES]
        cause = ""
        try:
            cdf = _cdf_monotone(v, PERCENTILES)
            rang = float(cdf(brut))
            if not np.isfinite(rang):
                cause = (f"le score brut ({brut}) tombe hors de l'intervalle "
                         f"p10-p90 [{v[0]}, {v[-1]}]")
        except ValueError as exc:
            rang = float("nan")
            cause = (f"les percentiles publies de cette ligne ne sont pas "
                     f"strictement croissants ({v}) : {exc}")
        if np.isfinite(rang):
            rang = float(np.clip(rang, 1e-6, 1 - 1e-6))
            resultat.update(
                methode="interpolation_monotone_percentiles",
                z=float(norm.ppf(rang)), rang_percentile=rang, signale=True,
                motif=(f"ecart normale/percentiles = {coh['ecart_max']:.3f} > "
                       f"{SEUIL_COHERENCE_Z} : la normale est rejetee pour cette ligne"))
        else:
            resultat.update(
                signale=True,
                interpolation_impossible=True,
                motif=(f"ecart normale/percentiles = {coh['ecart_max']:.3f} > "
                       f"{SEUIL_COHERENCE_Z}, mais l'interpolation monotone est "
                       f"impossible : {cause}. Le z normal est conserve et signale "
                       "comme peu fiable."))

    if not plus_haut_est_mieux:
        resultat["z"] = -resultat["z"]
        resultat["z_normal"] = -resultat["z_normal"]
        resultat["score_inverse"] = True
    return resultat
