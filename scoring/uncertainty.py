"""§5.6 — Budget d'incertitude a cinq composantes, en points d'echelle QI.

Aucune composante n'est mise a zero par defaut. Une composante non quantifiable
depuis une source telechargee est marquee indisponible, et sigma_total devient
explicitement une borne inferieure (R1, R3).
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from scoring.model import BudgetIncertitude, Composante, Observation


# ---------------------------------------------------------------------------
# sigma_mesure
# ---------------------------------------------------------------------------
def sigma_mesure(sd_posterior: float, echelle_sd: float, corrige: bool,
                 phi: float) -> Composante:
    return Composante(
        nom="mesure", valeur=sd_posterior * echelle_sd,
        origine=("ecart-type du posterieur de theta_g x " f"{echelle_sd:g}"
                 + (f", corrige de la surdispersion (phi = {phi:.3f})" if corrige
                    else ", posterieur nominal non corrige")),
        detail={"sd_posterior": sd_posterior, "phi": phi, "corrige": corrige},
    )


# ---------------------------------------------------------------------------
# sigma_etat — estime SUR CE SUJET a partir des doublons C3/C3bis, C4/C4bis
# ---------------------------------------------------------------------------
def sigma_etat(doublons: Sequence[tuple[str, float, float]],
               echelle_sd: float,
               fidelite_test_retest_publiee: float | None = None,
               origine_fidelite: str = "") -> Composante:
    """`doublons` : (code, z_premiere_passation, z_seconde_passation).

    Var(d) = 2 v  =>  v = d^2 / 2 pour chaque paire. On moyenne les v obtenus.
    Le composite est suppose charger sur un facteur d'etat COMMUN de poids total
    1 (les poids somment a 1) : sigma_etat_composite = sqrt(v_moyen). C'est le
    choix conservateur ; supposer l'independance entre sub-tests donnerait moins.
    """
    utilisables = [(c, a, b) for c, a, b in doublons
                   if a is not None and b is not None
                   and math.isfinite(a) and math.isfinite(b)]
    if utilisables:
        v = [((a - b) ** 2) / 2.0 for _, a, b in utilisables]
        v_moyen = float(np.mean(v))
        return Composante(
            nom="etat", valeur=math.sqrt(v_moyen) * echelle_sd,
            origine=("estime SUR CE SUJET a partir de "
                     + ", ".join(c for c, _, _ in utilisables)
                     + " (v = d^2/2, facteur d'etat commun)"),
            detail={"paires": [{"code": c, "z1": a, "z2": b, "v": vi}
                               for (c, a, b), vi in zip(utilisables, v)],
                    "v_moyen": v_moyen,
                    "n_paires": len(utilisables),
                    "avertissement": ("estimation fondee sur "
                                      f"{len(utilisables)} difference(s) : tres bruitee, "
                                      "a lire comme un ordre de grandeur")},
        )
    if fidelite_test_retest_publiee is not None:
        r = fidelite_test_retest_publiee
        return Composante(
            nom="etat", valeur=math.sqrt(max(1.0 - r, 0.0)) * echelle_sd,
            origine=("estimation intra-sujet impossible ; fidelite test-retest "
                     f"publiee utilisee a la place (r = {r:.3f}) — {origine_fidelite}"),
            detail={"r_test_retest": r, "source": origine_fidelite,
                    "substitution": True},
        )
    return Composante(
        nom="etat", valeur=None,
        origine=("ni doublon exploitable (C3/C3bis, C4/C4bis) ni fidelite "
                 "test-retest publiee telechargee : composante non quantifiable"),
        disponible=False,
    )


# ---------------------------------------------------------------------------
# sigma_norme — incertitude de delta (§4.2) + erreur d'echantillonnage des cellules
# ---------------------------------------------------------------------------
def sigma_norme(sd_delta_z: float | None, cellules: Sequence[dict] | None,
                poids: np.ndarray | None, echelle_sd: float,
                origine: str = "") -> Composante:
    """`cellules` : une par sub-test, avec 'sd' et 'N' issus d'un fichier telecharge.

    Erreur-type de la moyenne normative d'une cellule = SD / sqrt(N). Sur
    l'echelle z du sub-test, cela vaut (SD/sqrt(N))/SD = 1/sqrt(N).
    Propagation au composite : sqrt(somme_j w_j^2 / N_j).
    """
    if sd_delta_z is None and not cellules:
        return Composante(
            nom="norme", valeur=None,
            origine=("ni delta de post-stratification ni cellule normative "
                     "telechargee : composante non quantifiable"),
            disponible=False,
        )
    var = 0.0
    detail: dict = {}
    if sd_delta_z is not None:
        var += sd_delta_z ** 2
        detail["sd_delta_z"] = sd_delta_z
    if cellules and poids is not None:
        n = np.array([c["N"] for c in cellules], dtype=float)
        if np.any(n <= 0):
            raise ValueError("N de cellule normative <= 0")
        var_ech = float(np.sum((poids ** 2) / n))
        var += var_ech
        detail["variance_echantillonnage_cellules"] = var_ech
        detail["cellules"] = [{"N": c["N"], "sd": c.get("sd"),
                               "provenance_id": c.get("provenance_id")}
                              for c in cellules]
    return Composante(nom="norme", valeur=math.sqrt(var) * echelle_sd,
                      origine=origine or "delta de redressement + erreur d'echantillonnage",
                      detail=detail)


# ---------------------------------------------------------------------------
# sigma_age — ecart entre le centre de la bande normative et 21 ans
# ---------------------------------------------------------------------------
def sigma_age(centre_bande: float | None, age_sujet: float,
              pente_z_par_an: float | None, echelle_sd: float,
              origine: str = "") -> Composante:
    """Sans pente age->score estimee sur donnees telechargees, non quantifiable.

    On ne suppose JAMAIS une pente de memoire : §9 interdit d'extrapoler.
    """
    if centre_bande is None or pente_z_par_an is None:
        return Composante(
            nom="age", valeur=None,
            origine=("ecart d'age au centre de la bande non propageable : "
                     "aucune pente age-score estimee sur donnees telechargees"),
            disponible=False,
            detail={"centre_bande": centre_bande, "age_sujet": age_sujet},
        )
    ecart = abs(age_sujet - centre_bande)
    return Composante(
        nom="age", valeur=abs(pente_z_par_an) * ecart * echelle_sd,
        origine=origine or (f"|{age_sujet:g} - {centre_bande:g}| an(s) x pente estimee"),
        detail={"centre_bande": centre_bande, "age_sujet": age_sujet,
                "ecart_ans": ecart, "pente_z_par_an": pente_z_par_an},
    )


# ---------------------------------------------------------------------------
# sigma_clone — R4 : non-equivalence des items regeneres
# ---------------------------------------------------------------------------
def sigma_clone(observations: Sequence[Observation], poids: np.ndarray,
                r_clone: float, decalage_sd: float, echelle_sd: float) -> Composante:
    """Deux termes (§5.6) :

    systematique — decalage de difficulte du clone, +/- `decalage_sd` SD sur
        chaque sub-test clone. Traite comme PARFAITEMENT CORRELE entre sub-tests
        clones (hypothese conservatrice : un meme biais de construction) :
        sigma_sys = decalage_sd * somme des poids des sub-tests clones.
    aleatoire — (1 - r^2) de variance supplementaire sur chaque sub-test clone,
        r etant la correlation clone-original, INCONNUE et donc parametre
        explicite de configuration : variance = somme_j w_j^2 (1 - r^2).

    Vaut exactement 0 si aucun sub-test n'est ITEMS_CLONES.
    """
    obs = [o for o in observations if o.scorable]
    if len(obs) != poids.size:
        raise ValueError("poids et observations scorables de longueurs differentes")
    if not (0.0 < r_clone <= 1.0):
        raise ValueError(f"r_clone hors ]0,1] : {r_clone}")

    masque = np.array([o.est_clone for o in obs], dtype=float)
    poids_clones = float(np.sum(poids * masque))
    var_sys = (decalage_sd * poids_clones) ** 2
    var_ale = float(np.sum((poids ** 2) * masque) * (1.0 - r_clone ** 2))
    codes_clones = [o.code for o in obs if o.est_clone]

    return Composante(
        nom="clone",
        valeur=math.sqrt(var_sys + var_ale) * echelle_sd,
        origine=(f"{len(codes_clones)} sub-test(s) ITEMS_CLONES ; "
                 f"terme systematique +/-{decalage_sd:g} SD (suppose correle), "
                 f"terme aleatoire 1 - r^2 avec r = {r_clone:g} (parametre de configuration)")
        if codes_clones else "aucun sub-test ITEMS_CLONES : composante nulle par construction",
        detail={"codes_clones": codes_clones,
                "poids_cumule_clones": poids_clones,
                "r_clone": r_clone, "decalage_sd": decalage_sd,
                "sigma_systematique_z": math.sqrt(var_sys),
                "sigma_aleatoire_z": math.sqrt(var_ale),
                "r_clone_est_un_parametre_non_mesure": True},
    )


def budget(mesure: Composante, etat: Composante, norme: Composante,
           age: Composante, clone: Composante) -> BudgetIncertitude:
    return BudgetIncertitude(mesure=mesure, etat=etat, norme=norme,
                             age=age, clone=clone)
