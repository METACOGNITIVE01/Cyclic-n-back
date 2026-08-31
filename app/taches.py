"""Assemblage d'une tache complete : demonstrations, qualification, test.

R5 — aucune consigne verbale a l'interieur des sub-tests du noyau. Chaque tache
s'apprend par 4 a 6 DEMONSTRATIONS ANIMEES avec retour immediat, suivies de 3
essais de qualification. Les demonstrations sont des items de difficulte
minimale dont la solution est montree pas a pas par le client ; aucun texte
explicatif n'accompagne le stimulus.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from app import generators as gen
from app.items_exacts import disponibilite
from scoring.battery import BATTERIE

#: Longueur standard de chaque sub-test, d'apres la description publiee de la
#: tache (structure de l'instrument, pas norme). Les essais au-dela de cette
#: longueur affinent l'estimation latente mais N'ENTRENT JAMAIS dans la
#: comparaison normative (§2).
LONGUEUR_STANDARD: dict[str, int] = {
    "C1": 11, "C2": 24, "C6": 17, "C7": 40,
    "V1": 12, "K1": 9, "K2": 13,
}

N_DEMOS = 5          # dans la plage 4-6 exigee par R5
N_QUALIF = 3


def _ladder(n: int) -> list[float]:
    """Echelle de difficulte interne, croissante, sans unite."""
    return [float(x) for x in np.linspace(0.05, 0.95, n)]


def _items_choix_multiple(code: str, rng: np.random.Generator, n: int,
                          generateur: Callable[..., dict[str, Any]],
                          n_supplementaires: int = 0) -> dict[str, Any]:
    standard = [generateur(rng, d) for d in _ladder(n)]
    for i, it in enumerate(standard):
        it["standard"] = True
        it["index_standard"] = i
    # Items tres faciles inserés comme controle d'effort (§3), hors score brut.
    faciles = []
    for pos in (n // 3, 2 * n // 3):
        f = gen.item_facile(rng, standard[0]["type"])
        f["standard"] = False
        f["insere_apres"] = int(pos)
        faciles.append(f)
    supplementaires = [generateur(rng, float(rng.uniform(0.5, 1.0)))
                       for _ in range(n_supplementaires)]
    for it in supplementaires:
        it["standard"] = False
        it["hors_norme"] = True
    return {"standard": standard, "faciles": faciles,
            "supplementaires": supplementaires}


def construire_tache(code: str, graine: int, *,
                     essais_supplementaires: int = 0) -> dict[str, Any]:
    """Payload complet d'une tache, deterministe pour une graine donnee."""
    base = BATTERIE[code]
    reference = base.duplique_de or code
    rng = np.random.default_rng(graine)
    dispo = disponibilite(reference)

    payload: dict[str, Any] = {
        "code": code, "code_reference": reference,
        "nom": base.nom_fr, "canal": base.canal.value,
        "chronometre": base.chronometre,
        "mode_items": dispo["mode"],
        "mode_items_motif": dispo.get("motif", ""),
        "regle_score": base.regle_score,
        "longueur_standard": LONGUEUR_STANDARD.get(reference),
        "n_demonstrations": N_DEMOS, "n_qualification": N_QUALIF,
        "depend_convention_notationnelle": base.depend_convention_notationnelle,
        "graine": int(graine),
        "sans_consigne_verbale": True,
    }

    if reference in ("C1", "C6"):
        n = LONGUEUR_STANDARD[reference]
        payload["demonstrations"] = [gen.generer_matrice(rng, 0.02) for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_matrice(rng, 0.10) for _ in range(N_QUALIF)]
        payload.update(_items_choix_multiple(reference, rng, n, gen.generer_matrice,
                                             essais_supplementaires))
    elif reference == "C2":
        n = LONGUEUR_STANDARD[reference]
        payload["demonstrations"] = [gen.generer_rotation3d(rng, 0.02) for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_rotation3d(rng, 0.10) for _ in range(N_QUALIF)]
        payload.update(_items_choix_multiple(reference, rng, n, gen.generer_rotation3d,
                                             essais_supplementaires))
    elif reference == "K1":
        n = LONGUEUR_STANDARD[reference]
        payload["demonstrations"] = [gen.generer_serie_lettres_nombres(rng, 0.02)
                                     for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_serie_lettres_nombres(rng, 0.10)
                                    for _ in range(N_QUALIF)]
        payload.update(_items_choix_multiple(reference, rng, n,
                                             gen.generer_serie_lettres_nombres,
                                             essais_supplementaires))
    elif reference in ("C3", "C4", "C5"):
        sens = "direct" if reference == "C3" else "inverse"
        complexe = reference == "C5"
        if complexe:
            sens = "direct"
        payload["demonstrations"] = [gen.generer_empan(rng, 2, sens=sens, complexe=complexe)
                                     for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_empan(rng, 3, sens=sens, complexe=complexe)
                                    for _ in range(N_QUALIF)]
        # Empan adaptatif : deux essais par longueur, arret apres deux echecs.
        payload["escalier"] = {
            "longueur_min": 2, "longueur_max": 9, "essais_par_longueur": 2,
            "echecs_pour_arret": 2, "sens": sens, "complexe": complexe,
        }
        payload["standard"] = []
        payload["regle_arret"] = ("deux echecs a la meme longueur ; le score est le "
                                  "niveau maximal atteint")
    elif reference == "C7":
        payload["demonstrations"] = [gen.generer_reconnaissance(rng, 2, 2)
                                     for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_reconnaissance(rng, 3, 3)
                                    for _ in range(N_QUALIF)]
        payload["bloc"] = gen.generer_reconnaissance(rng, LONGUEUR_STANDARD["C7"])
        payload["standard"] = payload["bloc"]["essais"]
    elif reference == "V1":
        payload["demonstrations"] = [gen.generer_attention_divisee(rng, 2)
                                     for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_attention_divisee(rng, 1)
                                    for _ in range(N_QUALIF)]
        payload["bloc"] = gen.generer_attention_divisee(rng, LONGUEUR_STANDARD["V1"])
        payload["standard"] = payload["bloc"]["essais"]
    elif reference == "V2":
        payload["demonstrations"] = [gen.generer_trail_making(rng, 5) for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_trail_making(rng, 8) for _ in range(N_QUALIF)]
        payload["bloc"] = gen.generer_trail_making(rng, 25)
        payload["standard"] = payload["bloc"]["cibles"]
    elif reference == "V3":
        payload["demonstrations"] = [gen.generer_code_symboles(rng, 10, 9, 12)
                                     for _ in range(N_DEMOS)]
        payload["qualification"] = [gen.generer_code_symboles(rng, 10, 9, 6)
                                    for _ in range(N_QUALIF)]
        payload["bloc"] = gen.generer_code_symboles(rng, 90)
        payload["standard"] = payload["bloc"]["items"]
    elif reference == "K2":
        payload["demonstrations"] = []
        payload["qualification"] = []
        payload["standard"] = []
        payload["indisponible"] = True
        payload["motif_indisponible"] = (
            "Les 13 items du champ 20016 sont documentes publiquement mais ne sont "
            "pas reproduits ici : leur texte doit venir du PDF telecharge "
            "(Fluidintelligence.pdf). Sans telechargement, K2 n'est pas administrable "
            "et n'est pas remplace par des items inventes (R1).")
        payload["avertissement_prealable"] = [
            "Echantillon de reference : 40-69 ans. Vous avez 21 ans.",
            "Items en anglais, non traduits.",
            "Fidelite test-retest faible.",
            "Limite stricte de 2 minutes ; item non repondu = 0.",
            "Aucun QI ne sera derive de ce score.",
        ]
        payload["optionnel"] = True
    else:
        raise ValueError(f"tache inconnue : {code}")

    return payload
