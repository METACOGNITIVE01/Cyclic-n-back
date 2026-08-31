"""§3 — Protocole de passation : espacement, randomisation, pauses, controles d'effort.

Regles appliquees mecaniquement :
  * deux sessions separees d'au moins 48 h — REFUS logiciel si l'intervalle est
    plus court ;
  * ordre randomise a l'interieur de chaque session, avec graine enregistree (R2) ;
  * pause obligatoire de 60 s toutes les deux taches ;
  * echec de qualification => sub-test NON SCORE, jamais compte comme un echec (R5) ;
  * controles d'effort jamais annonces au sujet : ils elargissent l'intervalle du
    sub-test concerne, ils ne l'annulent pas (§3).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import numpy as np

from app.db import journaliser, maintenant

QUESTIONS_AVANT = [
    ("sommeil_heures", "Heures de sommeil la nuit derniere", 0.0, 14.0, "heures"),
    ("cafeine_mg", "Cafeine estimee consommee aujourd'hui", 0.0, 600.0, "mg"),
    ("heure_locale", "Heure locale (0-24)", 0.0, 24.0, "h"),
    ("effort_anticipe", "Effort que vous anticipez fournir", 1.0, 7.0, "echelle 1-7"),
    ("vigilance_actuelle", "Vigilance ressentie maintenant", 1.0, 7.0, "echelle 1-7"),
]

QUESTIONS_APRES = [
    ("effort_percu", "Effort que vous estimez avoir fourni", 1.0, 7.0, "echelle 1-7"),
    ("difficulte_percue", "Difficulte ressentie de l'ensemble", 1.0, 7.0, "echelle 1-7"),
]

#: Ces variables sont enregistrees et rapportees, mais ne corrigent AUCUN score (§3).
CORRIGE_LES_SCORES = False


class IntervalleTropCourt(RuntimeError):
    """Refus logiciel : moins de 48 h entre les deux sessions (§3)."""


@dataclass(frozen=True)
class PlanSession:
    numero: int
    graine: int
    ordre: list[str]
    pauses_apres_rangs: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {"numero": self.numero, "graine": self.graine, "ordre": self.ordre,
                "pauses_apres_rangs": self.pauses_apres_rangs}


def graine_session(graine_maitresse: int, sujet_id: str, numero: int) -> int:
    """Graine derivee, reproductible et distincte par session (R2)."""
    base = f"{graine_maitresse}|{sujet_id}|{numero}"
    return int(np.frombuffer(
        __import__("hashlib").sha256(base.encode()).digest()[:8], dtype=np.uint64)[0]
        % (2 ** 31 - 1))


def planifier_session(taches: Sequence[str], numero: int, graine_maitresse: int,
                      sujet_id: str, *, pause_toutes_les: int = 2,
                      taches_fixes_en_fin: Sequence[str] = ()) -> PlanSession:
    """Ordre randomise avec graine enregistree.

    `taches_fixes_en_fin` reste en fin de session quel que soit le tirage : K2 est
    propose « en fin de session 2 » (§2) et ne peut donc pas etre randomise ailleurs.
    """
    g = graine_session(graine_maitresse, sujet_id, numero)
    rng = np.random.default_rng(g)
    mobiles = [t for t in taches if t not in taches_fixes_en_fin]
    fixes = [t for t in taches if t in taches_fixes_en_fin]
    ordre = list(rng.permutation(mobiles)) + fixes
    pauses = [r for r in range(pause_toutes_les - 1, len(ordre) - 1, pause_toutes_les)]
    return PlanSession(numero=numero, graine=g, ordre=[str(t) for t in ordre],
                       pauses_apres_rangs=pauses)


def verifier_intervalle(cx: sqlite3.Connection, sujet_id: str, numero: int,
                        intervalle_min_h: float,
                        maintenant_utc: datetime | None = None) -> dict[str, Any]:
    """Refuse la session 2 si moins de `intervalle_min_h` depuis la fin de la session 1."""
    if numero <= 1:
        return {"autorisee": True, "motif": "premiere session"}
    maintenant_utc = maintenant_utc or datetime.now(timezone.utc)
    from app.db import lire
    lignes = lire(cx, "SELECT numero, debut_utc, fin_utc FROM session "
                      "WHERE sujet_id=? AND numero<? ORDER BY numero DESC LIMIT 1",
                  (sujet_id, numero))
    ligne = lignes[0] if lignes else None
    if ligne is None:
        raise IntervalleTropCourt(
            f"session {numero} demandee mais aucune session anterieure enregistree")
    reference = ligne["fin_utc"] or ligne["debut_utc"]
    t0 = datetime.fromisoformat(reference)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    ecoule = maintenant_utc - t0
    requis = timedelta(hours=intervalle_min_h)
    if ecoule < requis:
        manque = requis - ecoule
        raise IntervalleTropCourt(
            f"seulement {ecoule.total_seconds()/3600:.1f} h depuis la session "
            f"{ligne['numero']} ; {intervalle_min_h:g} h requises. "
            f"Reessayer dans {manque.total_seconds()/3600:.1f} h.")
    return {"autorisee": True, "heures_ecoulees": ecoule.total_seconds() / 3600.0,
            "session_precedente": int(ligne["numero"])}


# ---------------------------------------------------------------------------
# Qualification (R5)
# ---------------------------------------------------------------------------
def evaluer_qualification(reponses_correctes: Sequence[bool],
                          n_requises: int) -> dict[str, Any]:
    n_ok = sum(1 for r in reponses_correctes if r)
    qualifie = n_ok >= n_requises
    return {
        "qualifie": qualifie,
        "n_reussites": n_ok,
        "n_essais": len(reponses_correctes),
        "n_requises": n_requises,
        "consequence": ("sub-test administre et score normalement" if qualifie else
                        "sub-test NON SCORE. Ce n'est PAS un echec au test : la "
                        "consigne n'a pas ete acquise par la demonstration (R5)."),
    }


# ---------------------------------------------------------------------------
# Controles d'effort (§3) — jamais annonces au sujet
# ---------------------------------------------------------------------------
def detecter_controles_effort(essais: Sequence[dict[str, Any]], *,
                              latence_plancher_ms: float,
                              longueur_serie_identique: int) -> list[dict[str, Any]]:
    """Renvoie les declenchements. Un declenchement ELARGIT l'intervalle du
    sub-test concerne ; il ne l'annule jamais (§3)."""
    drapeaux: list[dict[str, Any]] = []

    rapides = [e for e in essais
               if e.get("latence_ms") is not None
               and e["latence_ms"] < latence_plancher_ms]
    if rapides:
        drapeaux.append({
            "type": "latence_sous_plancher",
            "n": len(rapides), "seuil_ms": latence_plancher_ms,
            "index": [e["index_essai"] for e in rapides],
            "consequence": "elargissement de l'intervalle du sub-test",
        })

    serie, plus_longue, valeur_serie = 1, 1, None
    debut, debut_max = 0, 0
    for i in range(1, len(essais)):
        if essais[i].get("reponse") == essais[i - 1].get("reponse") \
                and essais[i].get("reponse") is not None:
            serie += 1
            if serie > plus_longue:
                plus_longue, valeur_serie, debut_max = serie, essais[i]["reponse"], debut
        else:
            serie, debut = 1, i
    if plus_longue >= longueur_serie_identique:
        drapeaux.append({
            "type": "serie_de_reponses_identiques",
            "longueur": plus_longue, "valeur": valeur_serie,
            "index_debut": debut_max, "seuil": longueur_serie_identique,
            "consequence": "elargissement de l'intervalle du sub-test",
        })

    faciles = [e for e in essais if e.get("item_facile")]
    rates = [e for e in faciles if e.get("correct") is False]
    if faciles and rates:
        drapeaux.append({
            "type": "item_facile_rate",
            "n_rates": len(rates), "n_faciles": len(faciles),
            "index": [e["index_essai"] for e in rates],
            "consequence": "elargissement de l'intervalle du sub-test",
            "note": ("items dont la proportion de reussite attendue depasse .95 "
                     "dans la reference"),
        })
    return drapeaux


def facteur_elargissement(drapeaux: Sequence[dict[str, Any]],
                          facteur_par_drapeau: float) -> float:
    """Un seul facteur, applique une fois par TYPE de drapeau declenche."""
    types = {d["type"] for d in drapeaux}
    return float(facteur_par_drapeau ** len(types)) if types else 1.0


# ---------------------------------------------------------------------------
# Chronometrie (§7)
# ---------------------------------------------------------------------------
def evaluer_chronometrie(intervalles_ms: Sequence[float], tolerance: float,
                         chronometre: bool) -> dict[str, Any]:
    """Refuse la passation si le taux de rafraichissement varie de plus que
    `tolerance` pendant une tache CHRONOMETREE (§7)."""
    arr = np.asarray([x for x in intervalles_ms if x and x > 0], dtype=float)
    if arr.size < 10:
        return {"mesurable": False,
                "motif": f"{arr.size} intervalles de frame seulement : mesure impossible",
                "passation_refusee": bool(chronometre),
                "n_frames": int(arr.size)}
    hz = 1000.0 / arr
    med = float(np.median(hz))
    lo, hi = float(np.percentile(hz, 2.5)), float(np.percentile(hz, 97.5))
    variation = float((hi - lo) / med) if med > 0 else float("inf")
    refuse = bool(chronometre and variation > tolerance)
    return {
        "mesurable": True, "refresh_hz_median": med,
        "refresh_hz_min": lo, "refresh_hz_max": hi,
        "variation_relative": variation, "tolerance": tolerance,
        "n_frames": int(arr.size), "chronometre": chronometre,
        "passation_refusee": refuse,
        "motif": (f"variation du taux de rafraichissement {variation:.1%} > "
                  f"{tolerance:.0%} pendant une tache chronometree" if refuse else None),
        "latence_affichage_estimee_ms": float(1000.0 / med / 2.0) if med > 0 else None,
        "note_latence": ("latence d'affichage estimee a une demi-periode de "
                         "rafraichissement ; elle est soustraite des latences brutes"),
    }


def enregistrer_plan(cx: sqlite3.Connection, sujet_id: str, plan: PlanSession,
                     fuseau_local: str, refresh_hz: float | None) -> int:
    cur = cx.execute(
        "INSERT INTO session (sujet_id, numero, graine, ordre_taches, debut_utc, "
        "fuseau_local, refresh_hz_initial) VALUES (?,?,?,?,?,?,?)",
        (sujet_id, plan.numero, plan.graine,
         json.dumps(plan.ordre, ensure_ascii=False), maintenant(),
         fuseau_local, refresh_hz))
    sid = int(cur.lastrowid)
    journaliser(cx, "info", "session planifiee", sid, plan.to_dict())
    return sid
