"""Orchestration du modele de score (§5.2 a §5.7).

Convention d'echelle, explicitee parce qu'elle est facile a rater :
S(w) = somme_j w_j z_j est une moyenne ponderee de z, donc une estimation de
theta_g RETRECIE du facteur lambda_barre(w) = somme_j w_j lambda_jg. Le score
composite ramene sur l'echelle theta_g est donc S(w) / lambda_barre(w). C'est
cette quantite qui est convertie en points d'echelle QI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from scoring.battery import Domaine
from scoring.model import (BudgetIncertitude, Composante, Intervalle,
                           Observation, Posterior)
from scoring import fit, ia as ia_mod, uncertainty as unc, weights as wts
from scoring.posterior import posterior_theta_g

Z_90 = 1.6448536269514722   # quantile normal a 95 % : +/- 1,645 couvre 90 %


@dataclass
class ResultatNoyau:
    observations: list[Observation]
    posterior_nominal: Posterior
    posterior_rapporte: Posterior
    posterior_student: Posterior
    D: float
    phi: float
    ppp: dict[str, Any]
    ia: dict[str, Any]
    palier: str
    budget: BudgetIncertitude
    composite_z: float
    lambda_barre: float
    intervalle_interne: Intervalle
    intervalle_externe: Intervalle
    ambiguite_ponderation: dict[str, Any]
    largeur_ambiguite_qi: float
    residus: list[dict[str, Any]]
    domaines: dict[str, dict[str, Any]]
    non_scorables: list[dict[str, str]] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


def _composite_sur_echelle_theta(obs: Sequence[Observation], w: np.ndarray
                                 ) -> tuple[float, float]:
    z = np.array([o.z for o in obs])
    lg = np.array([o.lambda_g for o in obs])
    lam = float(np.dot(w, lg))
    if lam <= 0:
        raise ValueError("lambda_barre <= 0 : composite non interpretable")
    return float(np.dot(w, z)) / lam, lam


def scorer_noyau(
    observations: Sequence[Observation],
    *,
    echelle_moyenne: float = 100.0,
    echelle_sd: float = 15.0,
    masse_hdi: float = 0.90,
    theta_min: float = -4.0, theta_max: float = 4.0, pas: float = 0.01,
    ddl_student: int = 4,
    ppp_tirages: int = 5000,
    graine: int = 0,
    r_clone: float = 0.80,
    decalage_clone_sd: float = 0.25,
    borne_basse_poids: float = 0.5,
    borne_haute_poids: float = 1.5,
    seuil_ia_haut: float = 0.70,
    seuil_ia_bas: float = 0.45,
    doublons: Sequence[tuple[str, float, float]] = (),
    fidelite_test_retest: float | None = None,
    origine_fidelite: str = "",
    sd_delta_z: float | None = None,
    cellules_normatives: Sequence[dict] | None = None,
    origine_norme: str = "",
    centre_bande_age: float | None = None,
    age_sujet: float = 21.0,
    pente_age_z_par_an: float | None = None,
    origine_age: str = "",
    poids_criteres: dict[str, np.ndarray] | None = None,
) -> ResultatNoyau:
    obs = [o for o in observations if o.scorable]
    non_scorables = [{"code": o.code, "motif": o.motif_non_scorable}
                     for o in observations if not o.scorable]
    if not obs:
        raise ValueError(
            "aucun sub-test scorable : le score general ne peut pas etre produit. "
            "Le rapport doit afficher « pas de reference » (R1)."
        )
    rng = np.random.default_rng(graine)
    avertissements: list[str] = []

    # --- §5.2 posterieur nominal -------------------------------------------
    post_nom = posterior_theta_g(obs, loi_erreur="normale", masse_hdi=masse_hdi,
                                 theta_min=theta_min, theta_max=theta_max, pas=pas)
    theta_hat = post_nom.moyenne

    # --- §5.3 ajustement ----------------------------------------------------
    D = fit.statistique_D(obs, theta_hat)
    phi = fit.surdispersion(obs, theta_hat)
    phi_eff = max(1.0, phi)
    post_rap = posterior_theta_g(obs, loi_erreur="normale", masse_hdi=masse_hdi,
                                 theta_min=theta_min, theta_max=theta_max, pas=pas,
                                 surdispersion=phi_eff)
    post_stu = posterior_theta_g(obs, loi_erreur="student_t", ddl=ddl_student,
                                 masse_hdi=masse_hdi, theta_min=theta_min,
                                 theta_max=theta_max, pas=pas)
    res_ppp = fit.ppp(obs, post_nom, ppp_tirages, rng)
    if res_ppp["drapeau_profil_mal_resume"]:
        avertissements.append(
            "PPP < 0,05 : profil mal resume par un facteur unique. Le total doit "
            "etre lu apres le vecteur des sous-scores."
        )

    # --- §5.4 indice d'adequation -------------------------------------------
    res_ia = ia_mod.indice_adequation(obs, theta_hat)
    pal = ia_mod.palier(res_ia["ia"], seuil_ia_haut, seuil_ia_bas)
    if res_ia.get("psi_mesure_tous_nuls"):
        avertissements.append(
            "Aucune variance d'erreur de mesure connue depuis une source telechargee : "
            "l'IA ne soustrait rien et sous-estime donc l'adequation (lecture conservatrice)."
        )

    # --- §5.5 ponderations ---------------------------------------------------
    w_g = wts.poids_g(obs)
    composite_z, lam_barre = _composite_sur_echelle_theta(obs, w_g)
    amb = wts.intervalle_ponderation(obs, borne_basse_poids, borne_haute_poids,
                                     poids_criteres)
    if not amb["w_crit_disponible"]:
        avertissements.append(
            "Famille w_crit absente : aucun coefficient de validite publie n'a pu "
            "etre telecharge et cite. W se reduit a w_g, w_egal et au polytope."
        )

    # --- §5.6 budget d'incertitude -------------------------------------------
    c_mesure = unc.sigma_mesure(post_rap.ecart_type, echelle_sd,
                                corrige=phi_eff > 1.0, phi=phi)
    c_etat = unc.sigma_etat(doublons, echelle_sd, fidelite_test_retest, origine_fidelite)
    c_norme = unc.sigma_norme(sd_delta_z, cellules_normatives, w_g, echelle_sd,
                              origine_norme)
    c_age = unc.sigma_age(centre_bande_age, age_sujet, pente_age_z_par_an,
                          echelle_sd, origine_age)
    c_clone = unc.sigma_clone(obs, w_g, r_clone, decalage_clone_sd, echelle_sd)
    bud = unc.budget(c_mesure, c_etat, c_norme, c_age, c_clone)
    if not bud.complet:
        avertissements.append(
            "Budget d'incertitude incomplet (" + ", ".join(bud.manquantes) + ") : "
            "sigma_total est une BORNE INFERIEURE, l'incertitude reelle est plus grande."
        )

    # --- §5.7 deux intervalles emboites --------------------------------------
    demi = Z_90 * bud.sigma_total
    centre_qi = echelle_moyenne + echelle_sd * composite_z
    interne = Intervalle(point=centre_qi, bas=centre_qi - demi, haut=centre_qi + demi,
                         masse=masse_hdi, unite="QI")

    # Union sur w de W : sigma_clone depend de w, on le recalcule pour chaque w.
    familles = wts.familles(obs, poids_criteres)
    sommets = wts.sommets_polytope(w_g, borne_basse_poids, borne_haute_poids)
    tous_w = list(familles.values()) + [s for s in sommets]
    bas_ext, haut_ext = math.inf, -math.inf
    for w in tous_w:
        s_z, _ = _composite_sur_echelle_theta(obs, w)
        c_cl = unc.sigma_clone(obs, w, r_clone, decalage_clone_sd, echelle_sd)
        b_w = unc.budget(c_mesure, c_etat, c_norme, c_age, c_cl)
        d_w = Z_90 * b_w.sigma_total
        centre_w = echelle_moyenne + echelle_sd * s_z
        bas_ext = min(bas_ext, centre_w - d_w)
        haut_ext = max(haut_ext, centre_w + d_w)
    externe = Intervalle(point=centre_qi, bas=bas_ext, haut=haut_ext,
                         masse=masse_hdi, unite="QI")

    largeur_amb_qi = float(amb["largeur"] / lam_barre * echelle_sd)

    # --- §6.5 residus : ecart au niveau general du sujet lui-meme -------------
    var_theta = post_rap.ecart_type ** 2
    residus: list[dict[str, Any]] = []
    for o in obs:
        r = o.z - o.lambda_g * theta_hat
        var_r = o.lambda_s ** 2 + o.psi + (o.lambda_g ** 2) * var_theta
        demi_r = Z_90 * math.sqrt(var_r)
        residus.append({
            "code": o.code,
            "residu": Intervalle(point=r, bas=r - demi_r, haut=r + demi_r,
                                 masse=masse_hdi, unite="z"),
            "z_observe": o.z,
            "z_attendu": o.lambda_g * theta_hat,
            "mode_items": o.mode_items.value,
            "drapeaux_effort": list(o.drapeaux_effort),
        })

    # --- §6.3 scores de domaine ----------------------------------------------
    domaines: dict[str, dict[str, Any]] = {}
    par_dom: dict[Domaine, list[Observation]] = {}
    for o in obs:
        par_dom.setdefault(o.domaine, []).append(o)
    for dom, groupe in sorted(par_dom.items(), key=lambda kv: kv[0].value):
        p_d = posterior_theta_g(groupe, loi_erreur="normale", masse_hdi=masse_hdi,
                                theta_min=theta_min, theta_max=theta_max, pas=pas)
        domaines[dom.value] = {
            "codes": [o.code for o in groupe],
            "n_sub_tests": len(groupe),
            "intervalle_z": p_d.intervalle(),
            "intervalle_qi": p_d.intervalle().vers_qi(echelle_moyenne, echelle_sd),
            "note": ("posterieur de theta_g calcule sur les seuls sub-tests de ce "
                     "domaine : c'est un niveau general estime a contenu restreint, "
                     "pas un facteur de domaine pur"),
        }

    return ResultatNoyau(
        observations=list(obs), posterior_nominal=post_nom,
        posterior_rapporte=post_rap, posterior_student=post_stu,
        D=D, phi=phi, ppp=res_ppp, ia=res_ia, palier=pal, budget=bud,
        composite_z=composite_z, lambda_barre=lam_barre,
        intervalle_interne=interne, intervalle_externe=externe,
        ambiguite_ponderation=amb, largeur_ambiguite_qi=largeur_amb_qi,
        residus=residus, domaines=domaines,
        non_scorables=non_scorables, avertissements=avertissements,
    )


def resultat_en_dict(r: ResultatNoyau, decimation_courbe: int = 5) -> dict[str, Any]:
    """Serialisation canonique et deterministe (R2, T6).

    Aucun horodatage, aucun chemin absolu, aucun identifiant d'execution : ces
    elements vivent dans l'annexe de reproductibilite, hors du bloc compare par
    le test de determinisme.
    """
    return {
        "composite": {
            "z": r.composite_z,
            "lambda_barre": r.lambda_barre,
            "intervalle_interne_qi": r.intervalle_interne.to_dict(),
            "intervalle_externe_qi": r.intervalle_externe.to_dict(),
        },
        "ajustement": {
            "D": r.D, "phi": r.phi, "ppp": r.ppp,
            "ia": r.ia, "palier": r.palier,
        },
        "posterieurs": {
            "nominal": r.posterior_nominal.to_dict(decimation_courbe),
            "rapporte": r.posterior_rapporte.to_dict(decimation_courbe),
            "student_t": r.posterior_student.to_dict(decimation_courbe),
        },
        "budget_incertitude": r.budget.to_dict(),
        "ponderation": {
            **{k: v for k, v in r.ambiguite_ponderation.items()},
            "largeur_qi": r.largeur_ambiguite_qi,
        },
        "residus": [
            {"code": d["code"], "z_observe": d["z_observe"],
             "z_attendu": d["z_attendu"], "mode_items": d["mode_items"],
             "drapeaux_effort": d["drapeaux_effort"],
             "intervalle": d["residu"].to_dict()}
            for d in r.residus
        ],
        "domaines": {
            k: {"codes": v["codes"], "n_sub_tests": v["n_sub_tests"],
                "intervalle_z": v["intervalle_z"].to_dict(),
                "intervalle_qi": v["intervalle_qi"].to_dict(),
                "note": v["note"]}
            for k, v in sorted(r.domaines.items())
        },
        "non_scorables": r.non_scorables,
        "avertissements": r.avertissements,
    }
