"""§4.1 — Calibrage IRT sur les donnees ICAR telechargees.

Modele 2PL (option 3PL avec pseudo-hasard borne, les items ayant 8 options),
estime SEPAREMENT pour Matrix Reasoning, Three-dimensional Rotation et
Letter/Number Series, via `girth`.

« Ces parametres, et eux seuls, servent a placer le sujet sur l'echelle ICAR »
(§4.1). Aucun parametre n'est ecrit en dur : sans fichier ICAR telecharge, ce
module leve NoReferenceError et le sub-test sort du score (R1).

Les erreurs-types sont obtenues par bootstrap non parametrique sur les sujets,
avec graine enregistree (R2). C'est plus lent qu'une matrice d'information
analytique, mais cela n'exige aucune hypothese supplementaire.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Sequence

import numpy as np

from scoring.provenance import (NoReferenceError, ProvenanceRecord,
                                ProvenanceRegistry, id_norme)

ECHELLES_ICAR = {
    "matrix_reasoning": "C1",
    "three_dimensional_rotation": "C2",
    "letter_number_series": "K1",
}


@dataclass(frozen=True)
class ParametresItem:
    item: str
    a: float
    b: float
    c: float | None
    se_a: float
    se_b: float
    se_c: float | None
    provenance_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrageEchelle:
    echelle: str
    modele: str
    items: list[ParametresItem]
    n_sujets: int
    n_items: int
    graine_bootstrap: int
    n_bootstrap: int
    fichier: str
    sha256: str
    convergence: bool
    notes: list[str]

    def a(self) -> np.ndarray:
        return np.array([p.a for p in self.items])

    def b(self) -> np.ndarray:
        return np.array([p.b for p in self.items])

    def c(self) -> np.ndarray | None:
        if any(p.c is None for p in self.items):
            return None
        return np.array([p.c for p in self.items])

    def to_dict(self) -> dict[str, Any]:
        return {
            "echelle": self.echelle, "modele": self.modele,
            "n_sujets": self.n_sujets, "n_items": self.n_items,
            "graine_bootstrap": self.graine_bootstrap,
            "n_bootstrap": self.n_bootstrap,
            "fichier": self.fichier, "sha256": self.sha256,
            "convergence": self.convergence, "notes": self.notes,
            "items": [p.to_dict() for p in self.items],
        }


def _estimer(reponses: np.ndarray, modele: str, c_max: float) -> dict[str, np.ndarray]:
    """reponses : (n_items, n_sujets) binaire, sans manquant.

    girth indexe ses tables internes avec la matrice de reponses : elle doit
    donc etre d'un type entier, pas flottant.
    """
    from girth import twopl_mml, threepl_mml
    reponses = np.asarray(reponses)
    if not np.issubdtype(reponses.dtype, np.integer):
        if not np.all(np.isin(reponses, (0.0, 1.0))):
            raise ValueError("les reponses doivent etre binaires 0/1")
        reponses = reponses.astype(np.int64)
    if modele == "2PL":
        r = twopl_mml(reponses)
        return {"a": np.asarray(r["Discrimination"]),
                "b": np.asarray(r["Difficulty"]), "c": None}
    if modele == "3PL":
        r = threepl_mml(reponses)
        c = np.clip(np.asarray(r["Guessing"]), 0.0, c_max)
        return {"a": np.asarray(r["Discrimination"]),
                "b": np.asarray(r["Difficulty"]), "c": c}
    raise ValueError(f"modele IRT inconnu : {modele!r}")


def calibrer_echelle(reponses: np.ndarray, noms_items: Sequence[str], *,
                     echelle: str, fichier: str, sha256: str,
                     source_id: str = "ICAR_SAPA",
                     modele: str = "2PL", c_max: float = 0.125,
                     n_bootstrap: int = 200, graine: int = 20240117,
                     registry: ProvenanceRegistry | None = None) -> CalibrageEchelle:
    """Estime le modele et les erreurs-types par bootstrap sur les sujets.

    `reponses` : (n_sujets, n_items), 0/1, valeurs manquantes deja retirees.
    """
    reponses = np.asarray(reponses, dtype=float)
    if reponses.ndim != 2:
        raise ValueError("reponses doit etre une matrice (sujets x items)")
    n_sujets, n_items = reponses.shape
    if n_items != len(noms_items):
        raise ValueError("noms_items incoherent avec la largeur de la matrice")
    if n_sujets < 100:
        raise ValueError(
            f"{n_sujets} sujets : trop peu pour calibrer {echelle}. "
            "Refus plutot qu'une estimation instable (R1)."
        )
    notes: list[str] = []
    constants = [j for j in range(n_items)
                 if reponses[:, j].std() == 0.0]
    if constants:
        raise ValueError(
            f"items sans variance dans {echelle} : {[noms_items[j] for j in constants]}"
        )

    base = _estimer(reponses.T, modele, c_max)
    rng = np.random.default_rng(graine)
    boot_a = np.empty((n_bootstrap, n_items))
    boot_b = np.empty((n_bootstrap, n_items))
    boot_c = np.empty((n_bootstrap, n_items)) if base["c"] is not None else None
    echecs = 0
    for k in range(n_bootstrap):
        idx = rng.integers(0, n_sujets, size=n_sujets)
        ech = reponses[idx]
        if np.any(ech.std(axis=0) == 0.0):
            boot_a[k] = np.nan; boot_b[k] = np.nan
            if boot_c is not None:
                boot_c[k] = np.nan
            echecs += 1
            continue
        try:
            r = _estimer(ech.T, modele, c_max)
        except Exception:  # noqa: BLE001 - un replicat qui ne converge pas est ecarte
            boot_a[k] = np.nan; boot_b[k] = np.nan
            if boot_c is not None:
                boot_c[k] = np.nan
            echecs += 1
            continue
        boot_a[k], boot_b[k] = r["a"], r["b"]
        if boot_c is not None:
            boot_c[k] = r["c"]
    if echecs:
        notes.append(f"{echecs}/{n_bootstrap} replicats bootstrap ecartes (non convergence)")
    if echecs > n_bootstrap // 2:
        raise ValueError(
            f"{echelle} : plus de la moitie des replicats bootstrap ont echoue ; "
            "erreurs-types non fiables, calibrage refuse (R1)"
        )

    se_a = np.nanstd(boot_a, axis=0, ddof=1)
    se_b = np.nanstd(boot_b, axis=0, ddof=1)
    se_c = np.nanstd(boot_c, axis=0, ddof=1) if boot_c is not None else None

    items: list[ParametresItem] = []
    for j, nom in enumerate(noms_items):
        pid = id_norme(source_id, fichier, f"irt_{modele}_{echelle}_{nom}", j)
        if registry is not None:
            registry.enregistrer(ProvenanceRecord(
                provenance_id=pid, source_id=source_id, fichier=fichier,
                sha256=sha256, colonne=nom, index_ligne=j,
                valeur=float(base["a"][j]),
                description=(f"discrimination {modele} de l'item {nom} "
                             f"({echelle}), estimee sur {n_sujets} sujets")))
        items.append(ParametresItem(
            item=nom, a=float(base["a"][j]), b=float(base["b"][j]),
            c=(float(base["c"][j]) if base["c"] is not None else None),
            se_a=float(se_a[j]), se_b=float(se_b[j]),
            se_c=(float(se_c[j]) if se_c is not None else None),
            provenance_id=pid))

    return CalibrageEchelle(
        echelle=echelle, modele=modele, items=items, n_sujets=n_sujets,
        n_items=n_items, graine_bootstrap=graine, n_bootstrap=n_bootstrap,
        fichier=fichier, sha256=sha256, convergence=True, notes=notes)


def eap(reponses: np.ndarray, cal: CalibrageEchelle,
        grille: np.ndarray | None = None) -> tuple[float, float]:
    """EAP et erreur-type pour UN sujet, sous prior N(0,1)."""
    if grille is None:
        grille = np.arange(-4.0, 4.0 + 1e-9, 0.01)
    a, b, c = cal.a(), cal.b(), cal.c()
    if c is None:
        c = np.zeros_like(a)
    p = c[None, :] + (1.0 - c[None, :]) / (
        1.0 + np.exp(-a[None, :] * (grille[:, None] - b[None, :])))
    p = np.clip(p, 1e-12, 1 - 1e-12)
    x = np.asarray(reponses, dtype=float)
    ll = (x[None, :] * np.log(p) + (1 - x[None, :]) * np.log(1 - p)).sum(axis=1)
    ll -= ll.max()
    post = np.exp(ll) * np.exp(-0.5 * grille ** 2)
    post /= post.sum()
    m = float(post @ grille)
    v = float(post @ (grille ** 2) - m ** 2)
    return m, float(np.sqrt(max(v, 1e-12)))


def charger_calibrage(registry: ProvenanceRegistry, echelle: str) -> CalibrageEchelle:
    """Point d'entree du pipeline : leve NoReferenceError si ICAR est absent."""
    if not registry.source_disponible("ICAR_SAPA"):
        raise NoReferenceError(
            f"IRT:{echelle}",
            "aucun fichier ICAR/SAPA telecharge : le calibrage IRT est impossible "
            "et le sub-test correspondant sort du score (R1)")
    raise NoReferenceError(
        f"IRT:{echelle}",
        "fichiers ICAR presents mais aucun calibrage derive n'a ete produit ; "
        "lancer scoring/calibrate.py apres fetch_norms.py")
