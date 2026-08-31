"""Generateurs d'items, deterministes et graines (R2).

Les items sont produits COTE SERVEUR et envoyes au client sous forme de
specifications JSON que le canvas se contente de dessiner. C'est ce qui rend la
passation reproductible : meme graine -> memes items, quel que soit le
navigateur.

R4 — tous les generateurs de ce module produisent des ITEMS_CLONES : ils
regenerent une tache d'apres sa description publiee. Les items ICAR exacts, s'ils
sont fournis dans icar_items/, sont charges par app/items_exacts.py et etiquetes
ITEMS_EXACTS.

Aucune valeur normative ici : la difficulte des items est une echelle INTERNE,
sans unite, qui ne devient un score que confrontee a une norme telechargee.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

FORMES = ("cercle", "carre", "triangle", "losange", "hexagone", "croix")
REMPLISSAGES = ("plein", "vide", "hachure")
COULEURS = ("#2f3640", "#0a6cff", "#c0392b")
N_OPTIONS = 8
INDEX_AUCUNE = N_OPTIONS - 1      # « aucune de celles-ci »

REGLES_MATRICE = ("identite", "progression", "addition_soustraction", "distribution_trois")


# ---------------------------------------------------------------------------
# C1 / C6 — matrices figurales 3x3 a regles explicites
# ---------------------------------------------------------------------------
def _cellule(forme: int, n: int, taille: int, remplissage: int,
             rotation: int, couleur: int) -> dict[str, Any]:
    return {"forme": FORMES[forme % len(FORMES)], "n": int(n),
            "taille": int(taille), "remplissage": REMPLISSAGES[remplissage % 3],
            "rotation": int(rotation) % 360, "couleur": COULEURS[couleur % 3]}


def generer_matrice(rng: np.random.Generator, difficulte: float) -> dict[str, Any]:
    """Matrice 3x3. `difficulte` dans [0,1] pilote le nombre de regles simultanees.

    Regles implementees : identite, progression, addition/soustraction
    d'elements, distribution de trois.
    """
    n_regles = int(np.clip(1 + round(difficulte * 2.5), 1, 3))
    attributs = ["forme", "n", "taille", "remplissage", "rotation", "couleur"]
    choisis = [str(a) for a in rng.choice(attributs, size=n_regles, replace=False)]
    regles = {str(a): str(rng.choice(REGLES_MATRICE)) for a in choisis}

    base = {"forme": int(rng.integers(0, len(FORMES))), "n": int(rng.integers(1, 4)),
            "taille": int(rng.integers(1, 4)), "remplissage": int(rng.integers(0, 3)),
            "rotation": int(rng.integers(0, 4)) * 45, "couleur": int(rng.integers(0, 3))}
    fixe = dict(base)

    grille: list[list[dict[str, Any]]] = []
    for i in range(3):
        ligne = []
        for j in range(3):
            v = dict(fixe)
            for a, regle in regles.items():
                if regle == "identite":
                    v[a] = base[a]
                elif regle == "progression":
                    pas = 45 if a == "rotation" else 1
                    v[a] = base[a] + pas * j
                elif regle == "addition_soustraction":
                    v[a] = base[a] + i + j
                elif regle == "distribution_trois":
                    v[a] = base[a] + (i + j) % 3
            if "n" in v:
                v["n"] = int(np.clip(v["n"], 1, 4))
            if "taille" in v:
                v["taille"] = int(np.clip(v["taille"], 1, 3))
            ligne.append(_cellule(v["forme"], v["n"], v["taille"], v["remplissage"],
                                  v["rotation"], v["couleur"]))
        grille.append(ligne)

    bonne = grille[2][2]
    grille[2][2] = None  # type: ignore[assignment]

    options: list[dict[str, Any]] = []
    vus = {tuple(sorted(bonne.items()))}
    while len(options) < N_OPTIONS - 2:
        alt = dict(bonne)
        a = str(rng.choice(attributs))
        if a == "forme":
            alt["forme"] = FORMES[(FORMES.index(bonne["forme"]) + int(rng.integers(1, 6)))
                                  % len(FORMES)]
        elif a == "n":
            alt["n"] = int(np.clip(bonne["n"] + rng.choice([-2, -1, 1, 2]), 1, 4))
        elif a == "taille":
            alt["taille"] = int(np.clip(bonne["taille"] + rng.choice([-1, 1]), 1, 3))
        elif a == "remplissage":
            alt["remplissage"] = REMPLISSAGES[
                (REMPLISSAGES.index(bonne["remplissage"]) + int(rng.integers(1, 3))) % 3]
        elif a == "rotation":
            alt["rotation"] = (bonne["rotation"] + int(rng.choice([45, 90, 135, 180]))) % 360
        else:
            alt["couleur"] = COULEURS[(COULEURS.index(bonne["couleur"])
                                       + int(rng.integers(1, 3))) % 3]
        cle = tuple(sorted(alt.items()))
        if cle not in vus:
            vus.add(cle)
            options.append(alt)

    # Dans une fraction des items, la bonne reponse EST « aucune de celles-ci ».
    aucune_est_correcte = bool(rng.random() < 0.15)
    if aucune_est_correcte:
        reponse = INDEX_AUCUNE
        options = options[:N_OPTIONS - 1]
    else:
        pos = int(rng.integers(0, N_OPTIONS - 1))
        options.insert(pos, bonne)
        reponse = pos

    return {
        "type": "matrice",
        "grille": grille,
        "options": options + [{"aucune": True}],
        "reponse": reponse,
        "n_options": N_OPTIONS,
        "regles": regles,
        "difficulte_interne": float(difficulte),
        "aucune_est_correcte": aucune_est_correcte,
    }


# ---------------------------------------------------------------------------
# C2 — rotation 3D, assemblages type Shepard-Metzler
# ---------------------------------------------------------------------------
def _assemblage(rng: np.random.Generator, n_cubes: int) -> list[list[int]]:
    """Chemin de cubes unitaires a angles droits, sans auto-intersection."""
    cubes = [[0, 0, 0]]
    direction = np.array([1, 0, 0])
    occupe = {(0, 0, 0)}
    axes = [np.array(v) for v in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
    for _ in range(n_cubes - 1):
        for _essai in range(30):
            if rng.random() < 0.30:       # coude
                cand = [a * s for a in axes for s in (1, -1)
                        if not np.array_equal(a * s, direction)
                        and not np.array_equal(a * s, -direction)]
                d = cand[int(rng.integers(0, len(cand)))]
            else:
                d = direction
            p = (np.array(cubes[-1]) + d).tolist()
            if tuple(p) not in occupe:
                cubes.append([int(v) for v in p])
                occupe.add(tuple(p))
                direction = d
                break
        else:
            break
    return cubes


def _rotation(cubes: Sequence[Sequence[int]], axe: int, quarts: int) -> list[list[int]]:
    out = []
    for (x, y, z) in cubes:
        for _ in range(quarts % 4):
            if axe == 0:
                x, y, z = x, -z, y
            elif axe == 1:
                x, y, z = z, y, -x
            else:
                x, y, z = -y, x, z
        out.append([int(x), int(y), int(z)])
    return out


def _miroir(cubes: Sequence[Sequence[int]], axe: int) -> list[list[int]]:
    return [[(-v if k == axe else v) for k, v in enumerate(c)] for c in cubes]


def _normaliser(cubes: Sequence[Sequence[int]]) -> tuple[tuple[int, int, int], ...]:
    a = np.array(cubes)
    a = a - a.min(axis=0)
    return tuple(sorted(tuple(int(v) for v in c) for c in a.tolist()))


def generer_rotation3d(rng: np.random.Generator, difficulte: float) -> dict[str, Any]:
    """Cible + 7 propositions dont « aucune », distracteurs par reflexion et
    par rotation incorrecte."""
    n_cubes = int(np.clip(7 + round(difficulte * 4), 7, 11))
    cible = _assemblage(rng, n_cubes)
    axe, quarts = int(rng.integers(0, 3)), int(rng.integers(1, 4))
    bonne = _rotation(cible, axe, quarts)
    ref_bonne = _normaliser(bonne)

    options: list[dict[str, Any]] = []
    vus = {ref_bonne}
    tentatives = 0
    while len(options) < N_OPTIONS - 2 and tentatives < 300:
        tentatives += 1
        if rng.random() < 0.5:
            c = _rotation(_miroir(cible, int(rng.integers(0, 3))),
                          int(rng.integers(0, 3)), int(rng.integers(0, 4)))
            genre = "reflexion"
        else:
            c = _rotation(cible, int(rng.integers(0, 3)), int(rng.integers(1, 4)))
            # une rotation d'un assemblage reste le meme objet : on le deforme
            k = int(rng.integers(0, len(c)))
            c = [list(v) for v in c]
            c[k] = [c[k][0] + int(rng.choice([-1, 1])), c[k][1], c[k][2]]
            genre = "rotation_incorrecte"
        ref = _normaliser(c)
        if ref in vus:
            continue
        vus.add(ref)
        options.append({"cubes": c, "genre_distracteur": genre})

    aucune_est_correcte = bool(rng.random() < 0.15)
    if aucune_est_correcte:
        reponse = INDEX_AUCUNE
        options = options[:N_OPTIONS - 1]
    else:
        pos = int(rng.integers(0, min(N_OPTIONS - 1, len(options) + 1)))
        options.insert(pos, {"cubes": bonne, "genre_distracteur": None})
        reponse = pos

    return {
        "type": "rotation3d",
        "cible": cible,
        "options": options + [{"aucune": True}],
        "reponse": reponse, "n_options": N_OPTIONS,
        "rotation_appliquee": {"axe": axe, "quarts": quarts},
        "n_cubes": n_cubes,
        "difficulte_interne": float(difficulte),
        "aucune_est_correcte": aucune_est_correcte,
    }


# ---------------------------------------------------------------------------
# C3 / C4 / C5 — empans spatiaux
# ---------------------------------------------------------------------------
def generer_empan(rng: np.random.Generator, longueur: int, *, sens: str = "direct",
                  complexe: bool = False, n_cases: int = 9) -> dict[str, Any]:
    sequence = [int(v) for v in rng.choice(n_cases, size=longueur, replace=False)] \
        if longueur <= n_cases else \
        [int(rng.integers(0, n_cases)) for _ in range(longueur)]
    attendu = list(sequence) if sens == "direct" else list(reversed(sequence))
    item: dict[str, Any] = {
        "type": "empan", "sens": sens, "complexe": complexe,
        "n_cases": n_cases, "sequence": sequence,
        "reponse_attendue": attendu, "longueur": longueur,
    }
    if complexe:
        # Tache intercalaire entre deux presentations : jugement de symetrie.
        item["intercalaires"] = [
            {"motif": [int(v) for v in rng.integers(0, 2, size=n_cases)],
             "symetrique": bool(rng.random() < 0.5)}
            for _ in range(longueur)
        ]
    return item


# ---------------------------------------------------------------------------
# C7 — reconnaissance d'objets
# ---------------------------------------------------------------------------
def generer_reconnaissance(rng: np.random.Generator, n_essais: int,
                           n_familiarisation: int = 8) -> dict[str, Any]:
    banque = [
        {"forme": FORMES[int(rng.integers(0, len(FORMES)))],
         "couleur": COULEURS[int(rng.integers(0, 3))],
         "rotation": int(rng.integers(0, 8)) * 45,
         "remplissage": REMPLISSAGES[int(rng.integers(0, 3))],
         "graine_texture": int(rng.integers(0, 10 ** 6))}
        for _ in range(n_familiarisation + n_essais)
    ]
    cibles = banque[:n_familiarisation]
    essais = []
    for k in range(n_essais):
        ancien = bool(rng.random() < 0.5)
        obj = cibles[int(rng.integers(0, n_familiarisation))] if ancien \
            else banque[n_familiarisation + k]
        essais.append({"objet": obj, "deja_vu": ancien})
    return {"type": "reconnaissance", "familiarisation": cibles,
            "essais": essais, "n_essais": n_essais}


# ---------------------------------------------------------------------------
# V1 — attention visuelle divisee
# ---------------------------------------------------------------------------
def generer_attention_divisee(rng: np.random.Generator, n_essais: int) -> dict[str, Any]:
    essais = []
    for _ in range(n_essais):
        n_peripheriques = int(rng.integers(4, 13))
        cible_presente = bool(rng.random() < 0.5)
        essais.append({
            "central": {"forme": FORMES[int(rng.integers(0, 2))],
                        "couleur": COULEURS[int(rng.integers(0, 2))]},
            "peripheriques": [
                {"angle": float(rng.uniform(0, 360)), "rayon": float(rng.uniform(0.45, 0.92)),
                 "forme": FORMES[int(rng.integers(0, len(FORMES)))]}
                for _ in range(n_peripheriques)],
            "cible_presente": cible_presente,
            "duree_ms": int(rng.integers(140, 260)),
        })
    return {"type": "attention_divisee", "essais": essais, "n_essais": n_essais}


# ---------------------------------------------------------------------------
# V2 — Trail Making A
# ---------------------------------------------------------------------------
def generer_trail_making(rng: np.random.Generator, n_cibles: int = 25,
                         marge: float = 0.07) -> dict[str, Any]:
    points: list[dict[str, float]] = []
    for _ in range(n_cibles):
        for _essai in range(500):
            x, y = float(rng.uniform(marge, 1 - marge)), float(rng.uniform(marge, 1 - marge))
            if all((x - p["x"]) ** 2 + (y - p["y"]) ** 2 > 0.012 for p in points):
                points.append({"x": x, "y": y})
                break
        else:
            points.append({"x": float(rng.uniform(marge, 1 - marge)),
                           "y": float(rng.uniform(marge, 1 - marge))})
    return {"type": "trail_making", "variante": "A",
            "cibles": [{"etiquette": str(i + 1), **p} for i, p in enumerate(points)],
            "n_cibles": n_cibles,
            "convention_notationnelle": "ordre des chiffres arabes"}


# ---------------------------------------------------------------------------
# V3 — code symboles-chiffres
# ---------------------------------------------------------------------------
def generer_code_symboles(rng: np.random.Generator, duree_s: int = 90,
                          n_symboles: int = 9, n_items: int = 400) -> dict[str, Any]:
    cle = [{"chiffre": i + 1, "symbole": int(rng.integers(0, 24))}
           for i in range(n_symboles)]
    perm = list(rng.permutation(n_symboles))
    for k, c in enumerate(cle):
        c["symbole"] = int(perm[k])
    items = [int(rng.integers(1, n_symboles + 1)) for _ in range(n_items)]
    return {"type": "code_symboles", "cle": cle, "items": items,
            "duree_s": duree_s, "n_symboles": n_symboles,
            "convention_notationnelle": "ordre des chiffres arabes"}


# ---------------------------------------------------------------------------
# K1 — series de lettres et de nombres (clone)
# ---------------------------------------------------------------------------
def generer_serie_lettres_nombres(rng: np.random.Generator,
                                  difficulte: float) -> dict[str, Any]:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    genre = str(rng.choice(["arithmetique", "alphabetique", "alterne"]))
    longueur = int(np.clip(4 + round(difficulte * 3), 4, 7))
    if genre == "arithmetique":
        a0, pas = int(rng.integers(1, 12)), int(rng.integers(2, 8))
        if rng.random() < 0.35:
            serie = [a0 * (pas ** k) for k in range(longueur + 1)]
        else:
            serie = [a0 + pas * k for k in range(longueur + 1)]
        elements = [str(v) for v in serie]
    elif genre == "alphabetique":
        i0, pas = int(rng.integers(0, 12)), int(rng.integers(1, 5))
        elements = [alphabet[(i0 + pas * k) % 26] for k in range(longueur + 1)]
    else:
        i0, a0 = int(rng.integers(0, 12)), int(rng.integers(1, 9))
        pas_l, pas_n = int(rng.integers(1, 4)), int(rng.integers(1, 5))
        elements = []
        for k in range(longueur + 1):
            elements.append(alphabet[(i0 + pas_l * k) % 26])
            elements.append(str(a0 + pas_n * k))
        elements = elements[:longueur + 1]

    bonne = elements[-1]
    visibles = elements[:-1]
    options, vus = [], {bonne}
    while len(options) < N_OPTIONS - 2:
        if bonne.isdigit():
            alt = str(max(1, int(bonne) + int(rng.integers(-9, 10))))
        else:
            alt = alphabet[(alphabet.index(bonne) + int(rng.integers(1, 13))) % 26]
        if alt not in vus:
            vus.add(alt)
            options.append(alt)
    aucune_est_correcte = bool(rng.random() < 0.15)
    if aucune_est_correcte:
        reponse = INDEX_AUCUNE
        options = options[:N_OPTIONS - 1]
    else:
        pos = int(rng.integers(0, N_OPTIONS - 1))
        options.insert(pos, bonne)
        reponse = pos
    return {"type": "serie", "genre": genre, "elements": visibles,
            "options": options + ["aucune"], "reponse": reponse,
            "n_options": N_OPTIONS, "difficulte_interne": float(difficulte),
            "aucune_est_correcte": aucune_est_correcte,
            "convention_notationnelle": "ordre alphabetique et arithmetique"}


# ---------------------------------------------------------------------------
# Items tres faciles inseres (controle d'effort, §3)
# ---------------------------------------------------------------------------
def item_facile(rng: np.random.Generator, type_item: str) -> dict[str, Any]:
    """Item dont la reussite attendue depasse .95 dans la reference.

    Sert UNIQUEMENT de controle d'effort : jamais compte dans le score brut.
    """
    if type_item == "matrice":
        it = generer_matrice(rng, 0.0)
        it["regles"] = {"forme": "identite"}
        it["difficulte_interne"] = 0.0
    elif type_item == "rotation3d":
        it = generer_rotation3d(rng, 0.0)
    elif type_item == "serie":
        it = generer_serie_lettres_nombres(rng, 0.0)
    else:
        raise ValueError(f"pas d'item facile defini pour {type_item!r}")
    it["item_facile"] = True
    it["aucune_est_correcte"] = False
    return it
