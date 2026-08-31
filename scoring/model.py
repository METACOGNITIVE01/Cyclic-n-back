"""Types du modele de score CRIB-1 (§5) — contrat d'API.

Deux invariants portes par les types eux-memes :

  R3 — pas de pseudo-precision. `Intervalle` est le seul type d'affichage
       autorise pour un score. Un float nu ne peut pas etre rendu.
  R4 — honnetete de construction. Chaque observation porte son `mode_items`
       et, si ITEMS_CLONES, contribue une composante de non-equivalence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from scoring.battery import Domaine, ModeItems


class ScoreNuInterdit(TypeError):
    """R3 — tentative d'afficher un score ponctuel sans intervalle."""


@dataclass(frozen=True)
class Intervalle:
    """Un score, indissociable de son intervalle (R3).

    `masse` est la masse de probabilite couverte (0.90 par defaut dans CRIB-1).
    """
    point: float
    bas: float
    haut: float
    masse: float = 0.90
    unite: str = "z"

    def __post_init__(self) -> None:
        if self.bas > self.haut:
            raise ValueError(f"intervalle inverse : [{self.bas}, {self.haut}]")
        if not (0.0 < self.masse <= 1.0):
            raise ValueError(f"masse hors ]0,1] : {self.masse}")

    @property
    def largeur(self) -> float:
        return self.haut - self.bas

    def vers_qi(self, moyenne: float, sd: float) -> "Intervalle":
        return Intervalle(
            point=moyenne + sd * self.point,
            bas=moyenne + sd * self.bas,
            haut=moyenne + sd * self.haut,
            masse=self.masse, unite="QI",
        )

    def texte(self, decimales: int = 1) -> str:
        f = f"{{:.{decimales}f}}"
        return (f"{f.format(self.point)} "
                f"[{f.format(self.bas)} ; {f.format(self.haut)}] "
                f"({self.masse:.0%})")

    def to_dict(self) -> dict[str, Any]:
        return {"point": self.point, "bas": self.bas, "haut": self.haut,
                "masse": self.masse, "unite": self.unite, "largeur": self.largeur}


@dataclass(frozen=True)
class Observation:
    """Un sub-test observe, pret pour le modele bifactoriel.

    `psi` est la variance d'erreur TOTALE du sub-test sur l'echelle z :
    variance specifique residuelle + variance d'erreur de mesure. Elle est
    soustraite dans l'indice d'adequation (§5.4) : sans cela un sub-test peu
    fidele serait compte comme de l'heterogeneite reelle.
    """
    code: str
    z: float
    lambda_g: float
    lambda_s: float
    psi: float
    domaine: Domaine
    mode_items: ModeItems
    provenance_ids: tuple[str, ...] = ()
    drapeaux_effort: tuple[str, ...] = ()
    se_mesure: float = 0.0          # erreur-type de mesure incluse dans psi
    scorable: bool = True
    motif_non_scorable: str = ""

    def __post_init__(self) -> None:
        if self.psi <= 0:
            raise ValueError(f"{self.code} : psi doit etre > 0 (recu {self.psi})")
        if not math.isfinite(self.z):
            raise ValueError(f"{self.code} : z non fini")

    @property
    def est_clone(self) -> bool:
        return self.mode_items is ModeItems.CLONES


@dataclass(frozen=True)
class Posterior:
    """Postérieur de theta_g sur la grille -4..+4 (§5.2)."""
    grille: Any            # np.ndarray
    densite: Any           # np.ndarray, normalisee (integre a 1)
    moyenne: float
    ecart_type: float
    hdi_bas: float
    hdi_haut: float
    masse_hdi: float
    loi_erreur: str
    surdispersion: float = 1.0

    def intervalle(self) -> Intervalle:
        return Intervalle(point=self.moyenne, bas=self.hdi_bas,
                          haut=self.hdi_haut, masse=self.masse_hdi, unite="z")

    def to_dict(self, decimation: int = 5) -> dict[str, Any]:
        return {
            "moyenne": self.moyenne, "ecart_type": self.ecart_type,
            "hdi_bas": self.hdi_bas, "hdi_haut": self.hdi_haut,
            "masse_hdi": self.masse_hdi, "loi_erreur": self.loi_erreur,
            "surdispersion": self.surdispersion,
            "courbe_theta": [round(float(x), 4) for x in self.grille[::decimation]],
            "courbe_densite": [round(float(x), 8) for x in self.densite[::decimation]],
        }


@dataclass(frozen=True)
class Composante:
    """Une composante du budget d'incertitude (§5.6), en points d'echelle QI.

    `valeur` vaut None quand la composante n'est PAS quantifiable depuis une
    source telechargee. Elle n'est alors jamais remplacee par 0 : sigma_total
    devient une BORNE INFERIEURE, et le rapport le dit (R1, R3).
    """
    nom: str
    valeur: float | None
    origine: str
    disponible: bool = True
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.valeur is not None and self.valeur < 0:
            raise ValueError(f"{self.nom} : sigma negatif")
        if self.valeur is None and self.disponible:
            object.__setattr__(self, "disponible", False)

    def to_dict(self) -> dict[str, Any]:
        return {"nom": self.nom, "sigma_qi": self.valeur, "origine": self.origine,
                "disponible": self.disponible, "detail": self.detail}


@dataclass
class BudgetIncertitude:
    """§5.6 — cinq composantes, en points d'echelle QI (SD = 15)."""
    mesure: Composante
    etat: Composante
    norme: Composante
    age: Composante
    clone: Composante

    @property
    def toutes(self) -> tuple[Composante, ...]:
        return (self.mesure, self.etat, self.norme, self.age, self.clone)

    @property
    def composantes(self) -> dict[str, float | None]:
        return {c.nom: c.valeur for c in self.toutes}

    @property
    def manquantes(self) -> list[str]:
        return [c.nom for c in self.toutes if not c.disponible]

    @property
    def complet(self) -> bool:
        return not self.manquantes

    @property
    def sigma_total(self) -> float:
        """Racine de la somme des carres des composantes DISPONIBLES.

        Si une composante manque, c'est une borne inferieure (voir `complet`).
        """
        return math.sqrt(sum(c.valeur ** 2 for c in self.toutes if c.valeur is not None))

    @property
    def parts_variance(self) -> dict[str, float | None]:
        """Part de VARIANCE de chaque composante (§6.4)."""
        total = sum(c.valeur ** 2 for c in self.toutes if c.valeur is not None)
        if total <= 0:
            return {c.nom: None for c in self.toutes}
        return {c.nom: ((c.valeur ** 2) / total if c.valeur is not None else None)
                for c in self.toutes}

    def to_dict(self) -> dict[str, Any]:
        return {
            "composantes": [c.to_dict() for c in self.toutes],
            "sigma_total_qi": self.sigma_total,
            "sigma_total_est_borne_inferieure": not self.complet,
            "composantes_manquantes": self.manquantes,
            "parts_variance": self.parts_variance,
        }
