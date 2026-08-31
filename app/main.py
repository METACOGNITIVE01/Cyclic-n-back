#!/usr/bin/env python3
"""Serveur de passation CRIB-1 — local, 127.0.0.1 uniquement (§7).

Lancement :
    python3 -m app.main            # verifie les normes puis sert l'interface
    python3 -m app.main --sans-norme   # passation brute autorisee, AUCUN score

Le serveur refuse de demarrer si `verify_norms.py` rejette la passation, sauf
avec --sans-norme, qui enregistre alors dans la base que la session a ete
conduite sans reference (le rapport le dira).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tomllib
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import db, session_logic as sl  # noqa: E402
from app.taches import construire_tache  # noqa: E402
from scoring.battery import BATTERIE  # noqa: E402

CONFIG = tomllib.load(open(RACINE / "config" / "crib1.toml", "rb"))
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="CRIB-1", docs_url=None, redoc_url=None)
ETAT: dict[str, Any] = {"sans_norme": False, "verification": None}


def cx() -> sqlite3.Connection:
    if "cx" not in ETAT:
        ETAT["cx"] = db.connecter()
    return ETAT["cx"]


# ---------------------------------------------------------------------------
# Modeles de requete
# ---------------------------------------------------------------------------
class Sujet(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    age_annees: int = Field(ge=5, le=120)
    sexe: str
    langue: str = "fr"
    main_dominante: str = ""
    niveau_education: str


class DemarrerSession(BaseModel):
    sujet_id: str
    numero: int = Field(ge=1, le=2)
    fuseau_local: str = ""
    refresh_hz: float | None = None


class ReponsesQuestionnaire(BaseModel):
    session_id: int
    moment: str
    reponses: dict[str, float]


class DemarrerTache(BaseModel):
    session_id: int
    code: str
    essais_supplementaires: int = 0


class Essai(BaseModel):
    tache_id: int
    phase: str
    index_essai: int
    item: dict[str, Any]
    reponse: Any = None
    correct: bool | None = None
    latence_ms: float | None = None
    t_monotone_ms: float
    item_facile: bool = False
    latence_affichage_ms: float = 0.0


class Chronometrie(BaseModel):
    tache_id: int
    intervalles_ms: list[float]


class TerminerTache(BaseModel):
    tache_id: int


class Pause(BaseModel):
    session_id: int
    apres_rang: int
    duree_s: float


class TerminerSession(BaseModel):
    session_id: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/etat")
def etat() -> dict[str, Any]:
    return {
        "sujet_configure": CONFIG["sujet"],
        "protocole": CONFIG["protocole"],
        "qualification": CONFIG["qualification"],
        "chronometrie": CONFIG["chronometrie"],
        "sans_norme": ETAT["sans_norme"],
        "verification": ETAT["verification"],
        "avertissement_sans_norme": (
            "Aucune source normative n'est disponible sur ce disque. La passation "
            "est enregistree integralement, mais AUCUN score normatif ne sera "
            "produit : le rapport affichera « pas de reference » pour chaque "
            "sub-test concerne (R1)." if ETAT["sans_norme"] else None),
    }


@app.post("/api/sujet")
def creer_sujet(s: Sujet) -> dict[str, Any]:
    with db.transaction(cx()) as c:
        c.execute(
            "INSERT INTO sujet (id, age_annees, sexe, langue, main_dominante, "
            "niveau_education, cree_le) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET age_annees=excluded.age_annees, "
            "sexe=excluded.sexe, niveau_education=excluded.niveau_education",
            (s.id, s.age_annees, s.sexe, s.langue, s.main_dominante,
             s.niveau_education, db.maintenant()))
    return {"ok": True, "sujet_id": s.id}


@app.post("/api/session/demarrer")
def demarrer_session(r: DemarrerSession) -> dict[str, Any]:
    p = CONFIG["protocole"]
    try:
        controle = sl.verifier_intervalle(cx(), r.sujet_id, r.numero,
                                          float(p["intervalle_min_sessions_h"]))
    except sl.IntervalleTropCourt as exc:
        raise HTTPException(status_code=409, detail={
            "erreur": "intervalle_trop_court", "message": str(exc),
            "regle": f"{p['intervalle_min_sessions_h']:g} h minimum entre sessions (§3)",
        }) from exc

    lignes = db.lire(cx(), "SELECT id FROM session WHERE sujet_id=? AND numero=?",
                     (r.sujet_id, r.numero))
    existante = lignes[0] if lignes else None
    if existante:
        raise HTTPException(status_code=409, detail={
            "erreur": "session_deja_ouverte", "session_id": int(existante["id"])})

    taches = p[f"session{r.numero}"]
    plan = sl.planifier_session(
        taches, r.numero, int(p["graine_maitresse"]), r.sujet_id,
        pause_toutes_les=int(p["pause_toutes_les_n_taches"]),
        taches_fixes_en_fin=("K2",) if p.get("k2_optionnel") else ())
    with db.transaction(cx()) as c:
        sid = sl.enregistrer_plan(c, r.sujet_id, plan, r.fuseau_local, r.refresh_hz)
    return {"session_id": sid, "plan": plan.to_dict(), "controle_intervalle": controle,
            "questions_avant": [
                {"cle": k, "libelle": lib, "min": mn, "max": mx, "unite": u}
                for k, lib, mn, mx, u in sl.QUESTIONS_AVANT],
            "pause_s": p["pause_obligatoire_s"]}


@app.post("/api/questionnaire")
def questionnaire(r: ReponsesQuestionnaire) -> dict[str, Any]:
    if r.moment not in ("avant", "apres"):
        raise HTTPException(400, "moment doit etre 'avant' ou 'apres'")
    with db.transaction(cx()) as c:
        for cle, val in sorted(r.reponses.items()):
            c.execute(
                "INSERT INTO questionnaire (session_id, moment, cle, valeur, "
                "horodatage_utc) VALUES (?,?,?,?,?) "
                "ON CONFLICT(session_id, moment, cle) DO UPDATE SET valeur=excluded.valeur",
                (r.session_id, r.moment, cle, float(val), db.maintenant()))
    return {"ok": True, "n": len(r.reponses),
            "note": "variables enregistrees et rapportees ; elles ne corrigent aucun score (§3)"}


@app.post("/api/tache/demarrer")
def demarrer_tache(r: DemarrerTache) -> dict[str, Any]:
    if r.code not in BATTERIE:
        raise HTTPException(404, f"tache inconnue : {r.code}")
    s_l = db.lire(cx(), "SELECT * FROM session WHERE id=?", (r.session_id,))
    s = s_l[0] if s_l else None
    if s is None:
        raise HTTPException(404, "session inconnue")
    ordre = json.loads(s["ordre_taches"])
    if r.code not in ordre:
        raise HTTPException(400, f"{r.code} n'est pas au programme de cette session")
    rang = ordre.index(r.code)
    graine_tache = (int(s["graine"]) * 1000003 + rang * 7919) % (2 ** 31 - 1)
    payload = construire_tache(r.code, graine_tache,
                               essais_supplementaires=r.essais_supplementaires)
    with db.transaction(cx()) as c:
        cur = c.execute(
            "INSERT INTO tache (session_id, code, rang, mode_items, graine_tache, "
            "statut, debut_utc) VALUES (?,?,?,?,?,'en_cours',?) "
            "ON CONFLICT(session_id, code) DO UPDATE SET statut='en_cours', "
            "debut_utc=excluded.debut_utc",
            (r.session_id, r.code, rang, payload["mode_items"], graine_tache,
             db.maintenant()))
        tid = int(cur.lastrowid) or int(c.execute(
            "SELECT id FROM tache WHERE session_id=? AND code=?",
            (r.session_id, r.code)).fetchone()["id"])
    payload["tache_id"] = tid
    payload["rang"] = rang
    payload["pause_apres"] = rang in sl.planifier_session(
        ordre, int(s["numero"]), int(CONFIG["protocole"]["graine_maitresse"]),
        s["sujet_id"]).pauses_apres_rangs
    return payload


class SequenceEmpan(BaseModel):
    tache_id: int
    longueur: int = Field(ge=1, le=12)
    index: int = 0


@app.post("/api/empan/sequence")
def sequence_empan(r: SequenceEmpan) -> dict[str, Any]:
    """Sequence d'empan a la demande, deterministe : graine = graine de la tache,
    longueur et index d'essai. Rejouable a l'identique (R2)."""
    from app.generators import generer_empan
    t_l = db.lire(cx(), "SELECT * FROM tache WHERE id=?", (r.tache_id,))
    t = t_l[0] if t_l else None
    if t is None:
        raise HTTPException(404, "tache inconnue")
    ref = BATTERIE[t["code"]].duplique_de or t["code"]
    graine = (int(t["graine_tache"]) + r.longueur * 104729 + r.index * 1299709) % (2 ** 31 - 1)
    import numpy as np
    return generer_empan(np.random.default_rng(graine), r.longueur,
                         sens="direct" if ref in ("C3", "C5") else "inverse",
                         complexe=(ref == "C5"))


@app.post("/api/essai")
def essai(e: Essai) -> dict[str, Any]:
    latence_corrigee = None
    if e.latence_ms is not None:
        latence_corrigee = max(0.0, e.latence_ms - float(e.latence_affichage_ms))
    with db.transaction(cx()) as c:
        eid = db.enregistrer_essai(
            c, e.tache_id, e.phase, e.index_essai, e.item, e.reponse, e.correct,
            e.latence_ms, latence_corrigee, e.t_monotone_ms, e.item_facile)
    return {"ok": True, "essai_id": eid, "latence_corrigee_ms": latence_corrigee}


@app.post("/api/chronometrie")
def chronometrie(r: Chronometrie) -> dict[str, Any]:
    t_l = db.lire(cx(), "SELECT * FROM tache WHERE id=?", (r.tache_id,))
    t = t_l[0] if t_l else None
    if t is None:
        raise HTTPException(404, "tache inconnue")
    chrono = BATTERIE[t["code"]].chronometre
    res = sl.evaluer_chronometrie(r.intervalles_ms,
                                  float(CONFIG["chronometrie"]["tolerance_variation_refresh"]),
                                  chrono)
    with db.transaction(cx()) as c:
        c.execute(
            "INSERT INTO chronometrie (tache_id, refresh_hz_median, refresh_hz_min, "
            "refresh_hz_max, variation_relative, latence_affichage_ms, n_frames, "
            "passation_refusee, motif, horodatage_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r.tache_id, res.get("refresh_hz_median"), res.get("refresh_hz_min"),
             res.get("refresh_hz_max"), res.get("variation_relative"),
             res.get("latence_affichage_estimee_ms"), res.get("n_frames"),
             int(res["passation_refusee"]), res.get("motif"), db.maintenant()))
        if res["passation_refusee"]:
            c.execute("UPDATE tache SET statut='refusee_chronometrie', "
                      "motif_non_score=? WHERE id=?", (res.get("motif"), r.tache_id))
    return res


@app.post("/api/tache/terminer")
def terminer_tache(r: TerminerTache) -> dict[str, Any]:
    q = CONFIG["qualification"]
    ce = CONFIG["controles_effort"]
    qualif = [bool(x["correct"]) for x in db.essais_de(cx(), r.tache_id, "qualification")]
    res_q = sl.evaluer_qualification(qualif, int(q["n_reussites_requises"]))

    essais = [dict(x) for x in db.essais_de(cx(), r.tache_id, "test")]
    for x in essais:
        x["reponse"] = x["reponse"]
        x["correct"] = None if x["correct"] is None else bool(x["correct"])
        x["item_facile"] = bool(x["item_facile"])
    drapeaux = sl.detecter_controles_effort(
        essais, latence_plancher_ms=float(ce["latence_plancher_ms"]),
        longueur_serie_identique=int(ce["longueur_serie_identique"]))
    facteur = sl.facteur_elargissement(drapeaux, float(ce["facteur_elargissement_sigma"]))

    with db.transaction(cx()) as c:
        for d in drapeaux:
            c.execute("INSERT INTO controle_effort (tache_id, type, detail, "
                      "horodatage_utc) VALUES (?,?,?,?)",
                      (r.tache_id, d["type"], json.dumps(d, ensure_ascii=False),
                       db.maintenant()))
        c.execute("UPDATE tache SET qualifie=?, statut=?, motif_non_score=?, fin_utc=? "
                  "WHERE id=?",
                  (int(res_q["qualifie"]),
                   "terminee" if res_q["qualifie"] else "non_qualifiee",
                   None if res_q["qualifie"] else res_q["consequence"],
                   db.maintenant(), r.tache_id))
    return {"qualification": res_q, "controles_effort": drapeaux,
            "facteur_elargissement": facteur, "n_essais_test": len(essais)}


@app.post("/api/pause")
def pause(r: Pause) -> dict[str, Any]:
    requis = float(CONFIG["protocole"]["pause_obligatoire_s"])
    respectee = r.duree_s >= requis - 0.5
    with db.transaction(cx()) as c:
        c.execute("INSERT INTO pause (session_id, apres_rang, duree_s, respectee, "
                  "horodatage_utc) VALUES (?,?,?,?,?)",
                  (r.session_id, r.apres_rang, r.duree_s, int(respectee),
                   db.maintenant()))
    return {"ok": True, "respectee": respectee, "requis_s": requis}


@app.post("/api/session/terminer")
def terminer_session(r: TerminerSession) -> dict[str, Any]:
    with db.transaction(cx()) as c:
        c.execute("UPDATE session SET fin_utc=?, statut='terminee' WHERE id=?",
                  (db.maintenant(), r.session_id))
    return {"ok": True, "questions_apres": [
        {"cle": k, "libelle": lib, "min": mn, "max": mx, "unite": u}
        for k, lib, mn, mx, u in sl.QUESTIONS_APRES]}


@app.exception_handler(HTTPException)
def erreur(_req, exc: HTTPException) -> JSONResponse:  # type: ignore[override]
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> int:
    import uvicorn
    from verify_norms import verifier

    ap = argparse.ArgumentParser(description="CRIB-1 — serveur de passation local")
    ap.add_argument("--sans-norme", action="store_true",
                    help="autoriser la passation brute sans source normative "
                         "(aucun score ne sera produit)")
    ap.add_argument("--port", type=int, default=int(CONFIG["serveur"]["port"]))
    args = ap.parse_args()

    rapport = verifier()
    ETAT["verification"] = {
        "passation_autorisee": rapport["passation_autorisee"],
        "motif_refus": rapport.get("motif_refus") or rapport.get("erreur_fatale"),
        "sous_tests_non_scorables": sorted(rapport["sous_tests_non_scorables"]),
        "verifie_le": rapport["verifie_le"],
    }
    if not rapport["passation_autorisee"]:
        if not args.sans_norme:
            print("=" * 72)
            print("SERVEUR NON DEMARRE — verification des normes en echec.")
            print(f"  {rapport.get('motif_refus') or rapport.get('erreur_fatale')}")
            print("\n  Lancer d'abord :  python3 fetch_norms.py")
            print("  Ou forcer une passation SANS SCORE :  python3 -m app.main --sans-norme")
            print("=" * 72)
            return 1
        ETAT["sans_norme"] = True
        print("=" * 72)
        print("PASSATION SANS NORME — la session sera enregistree integralement,")
        print("mais AUCUN score normatif ne sera produit (R1).")
        print(f"  sub-tests sans reference : "
              f"{', '.join(sorted(rapport['sous_tests_non_scorables']))}")
        print("=" * 72)

    hote = CONFIG["serveur"]["hote"]
    if hote not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit(f"refus de servir sur {hote} : 127.0.0.1 uniquement (§7)")
    print(f"CRIB-1 sur http://{hote}:{args.port}")
    uvicorn.run(app, host=hote, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
