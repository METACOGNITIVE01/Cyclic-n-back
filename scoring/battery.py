"""Registre structurel de la batterie CRIB-1.

Ce module ne contient AUCUNE valeur normative (R1). Il declare uniquement :
  - quels sub-tests existent,
  - dans quel canal ils tombent (seul NOYAU entre dans g_cr),
  - comment leurs items sont obtenus (R4 : ITEMS_EXACTS vs ITEMS_CLONES),
  - de quelle source normative ils dependent,
  - a quel domaine du modele bifactoriel ils appartiennent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Canal(str, Enum):
    NOYAU = "NOYAU"
    VITESSE = "VITESSE"
    CONTAMINATION = "CONTAMINATION"


class ModeItems(str, Enum):
    """R4 — honnetete de construction."""
    EXACTS = "ITEMS_EXACTS"
    CLONES = "ITEMS_CLONES"
    INDETERMINE = "INDETERMINE"  # avant resolution du chemin a l'execution


class Domaine(str, Enum):
    INDUCTION = "INDUCTION"
    SPATIAL = "SPATIAL"
    MEMOIRE_TRAVAIL = "MEMOIRE_TRAVAIL"
    AUCUN = "AUCUN"


@dataclass(frozen=True)
class SubTest:
    code: str
    nom_fr: str
    canal: Canal
    domaine: Domaine
    source_norme: str                 # id dans config/sources.json
    mode_items_possible: tuple[ModeItems, ...]
    chronometre: bool
    n_items_standard: int | None
    n_options: int | None = None
    regle_score: str = ""
    depend_convention_notationnelle: bool = False
    duplique_de: str | None = None    # C3bis -> C3
    optionnel: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def est_doublon(self) -> bool:
        return self.duplique_de is not None


# --------------------------------------------------------------------------
# NOYAU — seul canal qui entre dans g_cr
# --------------------------------------------------------------------------
_NOYAU = [
    SubTest(
        code="C1", nom_fr="Matrices figurales", canal=Canal.NOYAU,
        domaine=Domaine.INDUCTION, source_norme="ICAR_SAPA",
        mode_items_possible=(ModeItems.EXACTS, ModeItems.CLONES),
        chronometre=False, n_items_standard=11, n_options=8,
        regle_score="nombre d'items corrects sur 11",
        notes=("8e option = 'aucune de celles-ci'",
               "ITEMS_EXACTS si icar_items/ fournit les 11 items ; sinon generateur a regles"),
    ),
    SubTest(
        code="C2", nom_fr="Rotation 3D", canal=Canal.NOYAU,
        domaine=Domaine.SPATIAL, source_norme="ICAR_SAPA",
        mode_items_possible=(ModeItems.EXACTS, ModeItems.CLONES),
        chronometre=False, n_items_standard=24, n_options=8,
        regle_score="nombre d'items corrects sur 24",
        notes=("assemblages de cubes type Shepard-Metzler, projection isometrique",
               "distracteurs par reflexion et par rotation incorrecte"),
    ),
    SubTest(
        code="C3", nom_fr="Empan spatial direct", canal=Canal.NOYAU,
        domaine=Domaine.MEMOIRE_TRAVAIL, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=False, n_items_standard=None,
        regle_score="niveau maximal atteint (longueur de sequence)",
        notes=("clone NCPT Forward Memory Span",),
    ),
    SubTest(
        code="C4", nom_fr="Empan spatial inverse", canal=Canal.NOYAU,
        domaine=Domaine.MEMOIRE_TRAVAIL, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=False, n_items_standard=None,
        regle_score="niveau maximal atteint (longueur de sequence)",
        notes=("clone NCPT Reverse Memory Span",),
    ),
    SubTest(
        code="C5", nom_fr="Empan complexe", canal=Canal.NOYAU,
        domaine=Domaine.MEMOIRE_TRAVAIL, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=False, n_items_standard=None,
        regle_score="niveau maximal atteint (longueur de sequence)",
        notes=("clone NCPT Complex Span",),
    ),
    SubTest(
        code="C6", nom_fr="Matrices progressives", canal=Canal.NOYAU,
        domaine=Domaine.INDUCTION, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=False, n_items_standard=17,
        regle_score="nombre d'essais reussis (17 essais max)",
        notes=("clone NCPT Progressive Matrices",),
    ),
    SubTest(
        code="C7", nom_fr="Reconnaissance d'objets", canal=Canal.NOYAU,
        domaine=Domaine.SPATIAL, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=False, n_items_standard=40,
        regle_score="nombre d'essais reussis sur 40",
        notes=("clone NCPT Object Recognition",),
    ),
]

# --------------------------------------------------------------------------
# CANAL VITESSE — rapporte a part, JAMAIS dans g_cr
# --------------------------------------------------------------------------
_VITESSE = [
    SubTest(
        code="V1", nom_fr="Attention visuelle divisee", canal=Canal.VITESSE,
        domaine=Domaine.AUCUN, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=True, n_items_standard=12,
        regle_score="nombre d'essais reussis sur 12",
        notes=("clone NCPT Divided Visual Attention",),
    ),
    SubTest(
        code="V2", nom_fr="Trail Making A", canal=Canal.VITESSE,
        domaine=Domaine.AUCUN, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=True, n_items_standard=None,
        regle_score="temps de completion en secondes (score inverse : plus bas = mieux)",
        depend_convention_notationnelle=True,
        notes=("clone NCPT Trail Making A",
               "suppose la connaissance de l'ordre des chiffres arabes"),
    ),
    SubTest(
        code="V3", nom_fr="Code symboles-chiffres", canal=Canal.VITESSE,
        domaine=Domaine.AUCUN, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,),
        chronometre=True, n_items_standard=None,
        regle_score="nombre d'appariements corrects en 90 s",
        depend_convention_notationnelle=True,
        notes=("clone NCPT Digit Symbol Coding",
               "suppose la connaissance de l'ordre des chiffres arabes"),
    ),
]

# --------------------------------------------------------------------------
# CANAL CONTAMINATION — mesure l'ecart, JAMAIS dans g_cr
# --------------------------------------------------------------------------
_CONTAMINATION = [
    SubTest(
        code="K1", nom_fr="Series de lettres et de nombres", canal=Canal.CONTAMINATION,
        domaine=Domaine.AUCUN, source_norme="ICAR_SAPA",
        mode_items_possible=(ModeItems.EXACTS, ModeItems.CLONES),
        chronometre=False, n_items_standard=9, n_options=8,
        regle_score="nombre d'items corrects sur 9",
        depend_convention_notationnelle=True,
        notes=("depend de l'ordre alphabetique et de l'arithmetique",),
    ),
    SubTest(
        code="K2", nom_fr="Raisonnement verbal-numerique chronometre",
        canal=Canal.CONTAMINATION,
        domaine=Domaine.AUCUN, source_norme="UKB_20016",
        mode_items_possible=(ModeItems.EXACTS,),
        chronometre=True, n_items_standard=13,
        regle_score="nombre d'items corrects sur 13 ; non repondu = 0 ; limite stricte 120 s",
        depend_convention_notationnelle=True, optionnel=True,
        notes=("items en anglais, non traduits",
               "echantillon de reference 40-69 ans : AUCUNE correction d'age (§9)",
               "fidelite test-retest faible — avertissement affiche avant passation"),
    ),
]

# --------------------------------------------------------------------------
# Doublons intra-sujet (§3) : servent a estimer sigma_etat, ne doublent pas le poids
# --------------------------------------------------------------------------
_DOUBLONS = [
    SubTest(
        code="C3bis", nom_fr="Empan spatial direct (sequences nouvelles)",
        canal=Canal.NOYAU, domaine=Domaine.MEMOIRE_TRAVAIL, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,), chronometre=False,
        n_items_standard=None, regle_score="niveau maximal atteint",
        duplique_de="C3",
        notes=("doublon d'etat : n'entre pas dans le composite, sert a sigma_etat",),
    ),
    SubTest(
        code="C4bis", nom_fr="Empan spatial inverse (sequences nouvelles)",
        canal=Canal.NOYAU, domaine=Domaine.MEMOIRE_TRAVAIL, source_norme="NCPT",
        mode_items_possible=(ModeItems.CLONES,), chronometre=False,
        n_items_standard=None, regle_score="niveau maximal atteint",
        duplique_de="C4",
        notes=("doublon d'etat : n'entre pas dans le composite, sert a sigma_etat",),
    ),
]

BATTERIE: dict[str, SubTest] = {
    st.code: st for st in (_NOYAU + _VITESSE + _CONTAMINATION + _DOUBLONS)
}

#: ICAR Verbal Reasoning est explicitement EXCLU (§2). Traduire un item lexical
#: ne conserve pas sa difficulte : la norme deviendrait invalide.
EXCLUS: dict[str, str] = {
    "ICAR_verbal_reasoning": (
        "16 items lexicaux anglais. Traduire un item de vocabulaire ne conserve pas "
        "sa difficulte, la norme devient invalide. Non implemente."
    ),
}


def noyau() -> list[SubTest]:
    """Sub-tests du noyau, doublons exclus : les 7 qui entrent dans g_cr."""
    return [s for s in BATTERIE.values()
            if s.canal is Canal.NOYAU and not s.est_doublon]


def par_canal(canal: Canal) -> list[SubTest]:
    return [s for s in BATTERIE.values() if s.canal is canal and not s.est_doublon]


def domaines() -> dict[Domaine, list[str]]:
    d: dict[Domaine, list[str]] = {}
    for s in noyau():
        d.setdefault(s.domaine, []).append(s.code)
    return d
