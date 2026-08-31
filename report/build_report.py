#!/usr/bin/env python3
"""§6 — Rapport CRIB-1 : HTML autonome + JSON complet + base SQLite.

Deux modes :

  python3 -m report.build_report
      Rapport reel. Lit data/derived/crib1.sqlite et le registre de provenance.
      Si aucune norme n'est disponible, le rapport le DIT et n'affiche aucun
      score : « pas de reference » pour chaque sub-test concerne (R1).

  python3 -m report.build_report --demo-simulation
      Rapport de DEMONSTRATION, estampille comme tel sur chaque page. Il montre
      la forme complete de la sortie a partir de donnees SIMULEES. Il ne contient
      aucune norme et son annexe de provenance est vide — c'est precisement ce qui
      le distingue d'un rapport reel.
"""
from __future__ import annotations

import argparse
import html
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from report import graphiques as gr, textes as tx  # noqa: E402
from scoring.battery import BATTERIE, Canal, ModeItems, par_canal  # noqa: E402
from scoring.lint_provenance import verifier_sortie  # noqa: E402
from scoring.model import Intervalle  # noqa: E402
from scoring.provenance import ProvenanceRegistry  # noqa: E402
from scoring import ia as ia_mod  # noqa: E402

SORTIE_HTML = RACINE / "report" / "crib1_rapport.html"
SORTIE_JSON = RACINE / "report" / "crib1_rapport.json"


def _esc(t: Any) -> str:
    return html.escape(str(t), quote=True)


def fmt(i: Intervalle, dec: int = 2) -> str:
    """R3 — un score ne s'affiche jamais nu."""
    return _esc(i.texte(dec))


# ---------------------------------------------------------------------------
# Collecte
# ---------------------------------------------------------------------------
def charger_verification() -> dict[str, Any]:
    p = RACINE / "data" / "derived" / "verification.json"
    if not p.exists():
        return {"passation_autorisee": False,
                "erreur_fatale": "verify_norms.py n'a jamais ete execute",
                "sources": {}, "sous_tests_non_scorables": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def resultat_simulation(graine: int, r_clone: float) -> dict[str, Any]:
    from scoring.pipeline import scorer_noyau
    from scoring.sensitivity import analyse_r_clone
    from scoring.simulation import (observations_depuis, plan_par_defaut,
                                    simuler_population)
    plan = plan_par_defaut()
    # La fidelite de l'EAP se mesure sur une population ; on simule donc une
    # population et on en extrait UN sujet, celui du rapport.
    sim = simuler_population(500, plan, np.random.default_rng(graine))
    obs = observations_depuis(plan, sim["z"][0], sim["psi"], sim["se_mesure"])
    doublons = [("C3", float(obs[2].z), float(obs[2].z) - 0.31),
                ("C4", float(obs[3].z), float(obs[3].z) + 0.18)]
    res = scorer_noyau(obs, graine=graine, r_clone=r_clone, doublons=doublons)
    sens = analyse_r_clone(obs, graine=graine, doublons=doublons)
    return {"resultat": res, "observations": obs, "sensibilite": sens,
            "theta_vrai": float(sim["theta_g"][0]), "n_population_simulee": 500}


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def section_cadrage() -> str:
    blocs = "".join(
        f'<div class="cadrage"><h3>{_esc(t)}</h3><p>{_esc(c)}</p></div>'
        for t, c in tx.CE_QUE_LE_TEST_PEUT_DIRE)
    interdits = "".join(f"<li>{_esc(x)}</li>" for x in tx.INTERDITS)
    return f"""
<section id="cadrage">
  <h2>1. Ce que ce test peut et ne peut pas dire</h2>
  {blocs}
  <div class="encadre">
    <h4>Ce que ce programme ne fait jamais</h4>
    <ul class="interdits">{interdits}</ul>
  </div>
</section>"""


def section_profil(res, moyenne: float, sd: float) -> str:
    lignes = []
    for d in res.residus:
        o = next(x for x in res.observations if x.code == d["code"])
        z = o.z
        demi = 1.6448536269514722 * np.sqrt(o.psi + o.lambda_s ** 2)
        iv = Intervalle(z, z - demi, z + demi, 0.90, "z")
        lignes.append({
            "code": o.code, "nom": BATTERIE[o.code].nom_fr,
            "iv_z": iv, "iv_qi": iv.vers_qi(moyenne, sd),
            "mode": o.mode_items.value,
            "drapeaux": list(o.drapeaux_effort),
        })
    lignes.sort(key=lambda l: l["iv_z"].point, reverse=True)

    svg = gr.barres_intervalles(
        [{"etiquette": f'{l["code"]} — {l["nom"]}', "point": l["iv_z"].point,
          "bas": l["iv_z"].bas, "haut": l["iv_z"].haut,
          "note": "clone" if l["mode"] == ModeItems.CLONES.value else "exact"}
         for l in lignes], unite="z")

    tr = "".join(
        f'<tr><td class="code">{_esc(l["code"])}</td><td>{_esc(l["nom"])}</td>'
        f'<td class="num">{fmt(l["iv_z"])}</td>'
        f'<td class="num">{fmt(l["iv_qi"], 0)}</td>'
        f'<td><span class="etiquette {"clone" if l["mode"]==ModeItems.CLONES.value else "exact"}">'
        f'{_esc(l["mode"])}</span></td>'
        f'<td>{_esc(", ".join(l["drapeaux"]) or "—")}</td></tr>'
        for l in lignes)

    return f"""
<section id="profil">
  <h2>2. Profil des sept sub-tests du noyau</h2>
  <p class="chapo">Tries par valeur. Chaque point porte son intervalle a 90 %.</p>
  {svg}
  <table>
    <thead><tr><th>code</th><th>sub-test</th><th>z [IC 90 %]</th>
      <th>equivalent QI [IC 90 %]</th><th>items</th><th>controles d'effort</th></tr></thead>
    <tbody>{tr}</tbody>
  </table>
  <p class="aide">L'equivalent QI est une convention de lecture (moyenne 100,
  ecart-type 15). Ce n'est pas une equivalence avec une batterie clinique.</p>
</section>"""


def section_domaines(res, moyenne: float, sd: float) -> str:
    lignes = [{"etiquette": k, "point": v["intervalle_z"].point,
               "bas": v["intervalle_z"].bas, "haut": v["intervalle_z"].haut}
              for k, v in res.domaines.items()]
    tr = "".join(
        f'<tr><td>{_esc(k)}</td><td>{_esc(", ".join(v["codes"]))}</td>'
        f'<td class="num">{fmt(v["intervalle_z"])}</td>'
        f'<td class="num">{fmt(v["intervalle_qi"], 0)}</td></tr>'
        for k, v in res.domaines.items())
    note = next(iter(res.domaines.values()))["note"] if res.domaines else ""
    return f"""
<section id="domaines">
  <h2>3. Scores de domaine</h2>
  {gr.barres_intervalles(lignes, unite="z")}
  <table><thead><tr><th>domaine</th><th>sub-tests</th><th>z [IC 90 %]</th>
    <th>equivalent QI [IC 90 %]</th></tr></thead><tbody>{tr}</tbody></table>
  <p class="aide">{_esc(note)}</p>
</section>"""


def section_total(res, moyenne: float, sd: float, sensibilite: dict | None) -> str:
    p = res.posterior_rapporte
    courbe = gr.courbe_posterieur(
        [float(x) for x in p.grille[::5]], [float(x) for x in p.densite[::5]],
        (p.hdi_bas, p.hdi_haut), p.moyenne)
    parts = gr.barres_variance(res.budget.parts_variance)

    post_qi = p.intervalle().vers_qi(moyenne, sd)
    ecart_qi = abs(res.composite_z - p.moyenne) * sd
    note_ecart = (
        f"Ecart entre le composite a ponderation w_g et la moyenne du posterieur : "
        f"{ecart_qi:.1f} point(s) d'echelle. Cet ecart n'est pas une erreur de calcul : "
        "le composite additionne les z sans distinguer ce qui vient du facteur general "
        "de ce qui vient des facteurs specifiques de domaine, alors que le posterieur "
        "marginalise ces derniers. Un ecart marque signale un profil dont une partie "
        "de l'elevation tient a un domaine particulier plutot qu'au niveau general.")

    palier_classe = {"total_presente_normalement": "normal",
                     "total_second_plan": "second",
                     "total_retrograde": "retrograde"}[res.palier]
    mention = ia_mod.mention_palier(res.palier)
    ia_txt = ("non defini" if res.ia["ia"] is None else f'{res.ia["ia"]:.2f}')

    tr_budget = "".join(
        f'<tr><td>{_esc(c.nom)}</td>'
        f'<td class="num">{"—" if c.valeur is None else f"{c.valeur:.2f}"}</td>'
        f'<td class="num">{"—" if res.budget.parts_variance[c.nom] is None else f"{res.budget.parts_variance[c.nom]*100:.0f} %"}</td>'
        f'<td class="petit">{_esc(c.origine)}</td></tr>'
        for c in res.budget.toutes)

    borne = ("<p class=\"alerte\">sigma_total est une <strong>borne inferieure</strong> : "
             f"les composantes {_esc(', '.join(res.budget.manquantes))} n'ont pas pu etre "
             "quantifiees depuis une source telechargee. L'incertitude reelle est plus "
             "grande que celle affichee.</p>" if not res.budget.complet else "")

    sens_html = ""
    if sensibilite:
        pts = "".join(
            f'<tr><td class="num">{p_["r_clone"]:.2f}</td>'
            f'<td class="num">{p_["sigma_clone_qi"]:.2f}</td>'
            f'<td class="num">{p_["sigma_total_qi"]:.2f}</td>'
            f'<td class="num">{p_["intervalle_interne"]["bas"]:.1f} – '
            f'{p_["intervalle_interne"]["haut"]:.1f}</td></tr>'
            for p_ in sensibilite["points"])
        sens_html = f"""
  <h3>Sensibilite a r_clone (0,70 – 0,90)</h3>
  <p class="reponse">{_esc(sensibilite["reponse"])}</p>
  <table><thead><tr><th>r_clone</th><th>sigma_clone (QI)</th>
    <th>sigma_total (QI)</th><th>intervalle interne</th></tr></thead>
    <tbody>{pts}</tbody></table>
  <p class="aide">{_esc(sensibilite["note"])}</p>"""

    return f"""
<section id="total">
  <h2>4. Score total</h2>
  <div class="total {palier_classe}">
    <div class="ligne-total">
      <span class="libelle">intervalle interne</span>
      <span class="valeur">{fmt(res.intervalle_interne, 1)}</span>
    </div>
    <div class="ligne-total">
      <span class="libelle">intervalle externe</span>
      <span class="valeur">{fmt(res.intervalle_externe, 1)}</span>
    </div>
    <div class="ligne-total">
      <span class="libelle">moyenne du posterieur de theta_g</span>
      <span class="valeur">{fmt(post_qi, 1)}</span>
    </div>
    {'<p class="mention">' + _esc(mention) + '</p>' if mention else ''}
    <p class="aide ecart">{_esc(note_ecart)}</p>
  </div>
  <div class="indicateurs">
    <div><span class="k">IA</span><span class="v">{_esc(ia_txt)}</span>
      <span class="d">indice d'adequation descriptive</span></div>
    <div><span class="k">PPP</span><span class="v">{res.ppp["ppp"]:.3f}</span>
      <span class="d">{'profil mal resume par un facteur unique' if res.ppp["drapeau_profil_mal_resume"] else 'ajustement acceptable'}</span></div>
    <div><span class="k">phi</span><span class="v">{res.phi:.2f}</span>
      <span class="d">surdispersion (D / ddl)</span></div>
    <div><span class="k">ambiguite w</span><span class="v">{res.largeur_ambiguite_qi:.1f}</span>
      <span class="d">largeur due au choix des poids, en points QI</span></div>
  </div>

  <h3>Courbe du posterieur de theta_g</h3>
  {courbe}
  <p class="aide">Posterieur rapporte : loi normale, corrige de la surdispersion
  (phi = {res.phi:.2f}). Posterieur Student-t(4) a titre de robustesse :
  ecart-type {res.posterior_student.ecart_type:.3f} contre
  {res.posterior_nominal.ecart_type:.3f} pour le posterieur nominal non corrige.</p>

  <h3>Decomposition de l'incertitude</h3>
  {parts}
  <table><thead><tr><th>composante</th><th>sigma (QI)</th><th>part de variance</th>
    <th>origine</th></tr></thead><tbody>{tr_budget}</tbody></table>
  <p><strong>sigma_total = {res.budget.sigma_total:.2f}</strong> points d'echelle QI.</p>
  {borne}
  {sens_html}
</section>"""


def section_residus(res) -> str:
    lignes = sorted(
        [{"etiquette": d["code"], "point": d["residu"].point,
          "bas": d["residu"].bas, "haut": d["residu"].haut} for d in res.residus],
        key=lambda l: l["point"], reverse=True)
    tr = "".join(
        f'<tr><td class="code">{_esc(d["code"])}</td>'
        f'<td class="num">{d["z_observe"]:+.2f}</td>'
        f'<td class="num">{d["z_attendu"]:+.2f}</td>'
        f'<td class="num">{fmt(d["residu"])}</td></tr>'
        for d in sorted(res.residus, key=lambda x: x["residu"].point, reverse=True))
    return f"""
<section id="residus">
  <h2>5. Relations entre dimensions</h2>
  <p class="chapo">{_esc(tx.NOTE_RESIDUS)}</p>
  {gr.barres_intervalles(lignes, xmin=-2.0, xmax=2.0, unite="residu (z)")}
  <table><thead><tr><th>code</th><th>z observe</th><th>z attendu vu theta_g</th>
    <th>residu [IC 90 %]</th></tr></thead><tbody>{tr}</tbody></table>
</section>"""


def section_canaux(verification: dict[str, Any]) -> str:
    def bloc(canal: Canal, titre: str) -> str:
        rows = []
        for st in par_canal(canal):
            nsc = verification.get("sous_tests_non_scorables", {}).get(st.code)
            etat = ("<span class=\"absent\">pas de reference</span>"
                    if nsc else "<span class=\"ok\">score disponible</span>")
            conv = "oui" if st.depend_convention_notationnelle else "non"
            rows.append(
                f'<tr><td class="code">{_esc(st.code)}</td><td>{_esc(st.nom_fr)}</td>'
                f'<td>{"chronometre" if st.chronometre else "sans limite"}</td>'
                f'<td>{conv}</td><td>{etat}</td></tr>')
        return (f'<h3>{titre}</h3><table><thead><tr><th>code</th><th>sub-test</th>'
                f'<th>temps</th><th>depend d\'une convention notationnelle</th>'
                f'<th>etat</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')

    return f"""
<section id="canaux">
  <h2>6. Canal vitesse et canal contamination</h2>
  <p class="chapo">{_esc(tx.NOTE_CANAUX)}</p>
  {bloc(Canal.VITESSE, "Canal vitesse")}
  {bloc(Canal.CONTAMINATION, "Canal contamination")}
  <div class="encadre">
    <h4>Contraste chronometre / non chronometre</h4>
    <p>Le noyau est administre sans limite de temps pour les epreuves de
    raisonnement (C1, C2, C6). Le canal vitesse est integralement chronometre.
    L'ecart entre les deux est la quantite interessante ; il n'est calculable que
    si les deux canaux disposent d'une reference. Ce n'est pas le cas ici tant que
    les fichiers normatifs ne sont pas telecharges.</p>
  </div>
</section>"""


def section_predictions(coefficients: list[dict] | None) -> str:
    if not coefficients:
        return f"""
<section id="predictions">
  <h2>7. Ce que ces scores predisent</h2>
  <div class="encadre alerte-bloc">
    <p>{_esc(tx.NOTE_PREDICTIONS_ABSENTES)}</p>
  </div>
  <p class="aide">{_esc(tx.NOTE_ECART_TYPE_RESIDUEL)}</p>
</section>"""
    tr = "".join(
        f'<tr><td>{_esc(c["critere"])}</td><td class="num">{c["r"]:.2f}</td>'
        f'<td class="num">{c["r"]**2:.2f}</td>'
        f'<td class="num">{np.sqrt(1-c["r"]**2):.2f}</td>'
        f'<td class="num">{_esc(c["intervalle_predit"])}</td>'
        f'<td class="petit">{_esc(c["provenance_id"])}</td></tr>'
        for c in coefficients)
    return f"""
<section id="predictions">
  <h2>7. Ce que ces scores predisent</h2>
  <table><thead><tr><th>critere</th><th>r</th><th>R²</th>
    <th>ecart-type residuel</th><th>valeur predite [IC 90 %]</th>
    <th>provenance</th></tr></thead><tbody>{tr}</tbody></table>
  <p class="aide">{_esc(tx.NOTE_ECART_TYPE_RESIDUEL)}</p>
</section>"""


def section_provenance(annexe: list[dict]) -> str:
    if not annexe:
        return """
<section id="provenance">
  <h2>8. Annexe provenance</h2>
  <div class="encadre alerte-bloc">
    <p>Aucune valeur normative n'a ete employee dans ce rapport. L'annexe est
    donc vide, et c'est coherent : aucun score normatif n'y figure. Une annexe
    vide accompagnee de scores serait le signe d'une violation de la regle de
    provenance (R1).</p>
  </div>
</section>"""
    tr = "".join(
        f'<tr><td class="petit mono">{_esc(e["provenance_id"])}</td>'
        f'<td class="petit">{_esc(e["fichier"])}</td>'
        f'<td class="petit">{_esc(e["colonne"])}</td>'
        f'<td class="num">{_esc(e["index_ligne"])}</td>'
        f'<td class="num">{_esc(e["valeur"])}</td>'
        f'<td class="petit mono sha">{_esc(e["sha256"])}</td></tr>'
        for e in annexe)
    return f"""
<section id="provenance">
  <h2>8. Annexe provenance</h2>
  <p class="chapo">Chaque norme employee, son fichier, sa colonne, son index de
  ligne et le SHA-256 du fichier dont elle est extraite.</p>
  <table class="large"><thead><tr><th>identifiant</th><th>fichier</th>
    <th>colonne</th><th>ligne</th><th>valeur</th><th>SHA-256</th></tr></thead>
    <tbody>{tr}</tbody></table>
</section>"""


def section_reproductibilite(meta: dict[str, Any]) -> str:
    tr = "".join(f'<tr><td>{_esc(k)}</td><td class="petit mono">{_esc(v)}</td></tr>'
                 for k, v in meta.items())
    return f"""
<section id="reproductibilite">
  <h2>9. Annexe reproductibilite</h2>
  <table><tbody>{tr}</tbody></table>
</section>"""


# ---------------------------------------------------------------------------
# Assemblage
# ---------------------------------------------------------------------------
CSS = """
:root{--fond:#fbfbf9;--encre:#191920;--doux:#63636e;--trait:#dedede;
 --accent:#0a4fa8;--alerte:#a8320a;--ok:#1d6b34;--carte:#fff;--ombre:rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root{--fond:#111116;--encre:#e9e9ec;--doux:#9a9aa6;
 --trait:#31313b;--accent:#7ab0ff;--alerte:#ff9070;--ok:#6fd68f;--carte:#1a1a21;
 --ombre:rgba(0,0,0,.4)}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--encre);
 font:15px/1.62 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:34px 22px 90px}
h1{font-size:30px;margin:0 0 4px} h2{font-size:21px;margin:44px 0 12px;
 padding-bottom:7px;border-bottom:1px solid var(--trait)}
h3{font-size:16px;margin:26px 0 8px} h4{font-size:14px;margin:0 0 6px;
 text-transform:uppercase;letter-spacing:.06em;color:var(--doux)}
p{margin:.5em 0} .chapo{color:var(--doux)} .aide{color:var(--doux);font-size:13.5px}
.petit{font-size:12.5px} .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.sha{word-break:break-all;max-width:230px;display:inline-block}
.bandeau{border-radius:9px;padding:14px 18px;margin:0 0 26px;font-size:14px;
 border:1px solid var(--alerte);border-left-width:5px;background:var(--carte)}
.bandeau.demo{border-color:var(--accent)}
.cadrage{margin:16px 0;padding-left:14px;border-left:3px solid var(--trait)}
.cadrage h3{margin:0 0 3px;font-size:15px} .cadrage p{margin:0;color:var(--doux)}
.encadre{background:var(--carte);border:1px solid var(--trait);border-radius:9px;
 padding:14px 18px;margin:20px 0;box-shadow:0 1px 2px var(--ombre)}
.encadre.alerte-bloc{border-color:var(--alerte)}
.interdits{margin:.4em 0;padding-left:20px} .interdits li{margin:.2em 0}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13.5px}
.large{font-size:12.5px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--trait);
 vertical-align:top}
th{color:var(--doux);font-weight:600;font-size:12.5px;text-transform:uppercase;
 letter-spacing:.04em}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.code{font-weight:700}
.etiquette{font-size:11.5px;padding:2px 7px;border-radius:20px;border:1px solid var(--trait)}
.etiquette.clone{border-color:var(--alerte);color:var(--alerte)}
.etiquette.exact{border-color:var(--ok);color:var(--ok)}
.absent{color:var(--alerte)} .ok{color:var(--ok)}
.alerte{color:var(--alerte)}
.total{background:var(--carte);border:1px solid var(--trait);border-radius:11px;
 padding:18px 22px;margin:14px 0}
.total.second{opacity:.9;border-style:dashed}
.total.retrograde{opacity:.62;filter:grayscale(.65)}
.ligne-total{display:flex;justify-content:space-between;align-items:baseline;
 gap:16px;padding:5px 0}
.ligne-total .libelle{color:var(--doux);font-size:13.5px}
.ligne-total .valeur{font-size:19px;font-variant-numeric:tabular-nums;font-weight:600}
.mention{margin:10px 0 0;color:var(--alerte);font-size:13.5px}
.ecart{margin-top:10px;padding-top:9px;border-top:1px solid var(--trait)}
.indicateurs{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
 gap:10px;margin:16px 0}
.indicateurs>div{background:var(--carte);border:1px solid var(--trait);
 border-radius:9px;padding:10px 13px}
.indicateurs .k{display:block;font-size:11.5px;text-transform:uppercase;
 letter-spacing:.05em;color:var(--doux)}
.indicateurs .v{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.indicateurs .d{display:block;font-size:12px;color:var(--doux)}
.reponse{font-weight:600}
.graphe{width:100%;height:auto;margin:10px 0;overflow:visible}
.graphe .grille{stroke:var(--trait);stroke-width:1}
.graphe .zero{stroke:var(--doux);stroke-width:1;stroke-dasharray:4 4}
.graphe .axe{fill:var(--doux);font-size:11px}
.graphe .etiq{fill:var(--encre);font-size:12px}
.graphe .note{fill:var(--doux);font-size:10.5px}
.graphe .ic{stroke:var(--accent);stroke-width:2}
.graphe .pt{fill:var(--accent)}
.graphe .courbe{fill:none;stroke:var(--accent);stroke-width:2}
.graphe .hdi{fill:var(--accent);opacity:.17}
.graphe .moy{stroke:var(--accent);stroke-width:1.5;stroke-dasharray:3 3}
.graphe .barre{fill:var(--accent);opacity:.72}
.graphe .val{fill:var(--doux);font-size:11.5px}
.graphe .absent{fill:var(--alerte);font-size:11.5px}
.vide{color:var(--doux);font-style:italic}
footer{margin-top:50px;padding-top:16px;border-top:1px solid var(--trait);
 color:var(--doux);font-size:12.5px}
@media print{body{background:#fff}.total.retrograde{filter:none;opacity:1}}
"""


def rendre_html(corps: str, bandeau: str, titre: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(titre)}</title><style>{CSS}</style></head>
<body><main>
<h1>{_esc(titre)}</h1>
{bandeau}
{corps}
<footer>CRIB-1 — Culture-Reduced Inference Battery, version 1.
Rapport genere localement. Aucun modele de langage n'intervient dans la
passation ni dans le scoring (R2).</footer>
</main></body></html>"""


def construire(demo: bool, graine: int, r_clone: float) -> tuple[str, dict[str, Any]]:
    verification = charger_verification()
    horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
    registry = ProvenanceRegistry()

    meta = {
        "genere_le": horodatage,
        "mode": "DEMONSTRATION SIMULEE" if demo else "reel",
        "graine_maitresse": graine,
        "r_clone": r_clone,
        "python": sys.version.split()[0],
        "plateforme": platform.platform(),
        "numpy": np.__version__,
        "scipy": __import__("scipy").__version__,
        "pandas": __import__("pandas").__version__,
        "girth": "installe" if _module_present("girth") else "absent",
        "semopy": _version("semopy"),
        "verification_normes": verification.get("verifie_le", "jamais executee"),
        "passation_autorisee": verification.get("passation_autorisee"),
        "base_sqlite": str((RACINE / "data" / "derived" / "crib1.sqlite")
                           .relative_to(RACINE)),
    }

    sortie: dict[str, Any] = {
        "meta": meta,
        "cadrage": [{"titre": t, "texte": c} for t, c in tx.CE_QUE_LE_TEST_PEUT_DIRE],
        "interdits": tx.INTERDITS,
        "verification_normes": verification,
        "normes_employees": [],
        "annexe_provenance": registry.table_annexe(),
    }

    if not demo:
        non_scorables = verification.get("sous_tests_non_scorables", {})
        bandeau = f"""<div class="bandeau">
<strong>Aucun score n'est produit.</strong> {_esc(verification.get('motif_refus') or verification.get('erreur_fatale') or '')}
Les {len(non_scorables)} sub-tests de la batterie sont sans reference : conformement a
la regle de provenance (R1), le programme affiche « pas de reference » et les exclut
du score plutot que d'interpoler une norme.</div>"""
        corps = (section_cadrage()
                 + section_sans_reference(non_scorables, verification)
                 + section_canaux(verification)
                 + section_predictions(None)
                 + section_provenance(registry.table_annexe())
                 + section_reproductibilite(meta))
        sortie["profil"] = []
        sortie["total"] = None
        sortie["sous_tests_non_scorables"] = non_scorables
        return rendre_html(corps, bandeau, "CRIB-1 — rapport"), sortie

    d = resultat_simulation(graine, r_clone)
    res = d["resultat"]
    bandeau = f"""<div class="bandeau demo">
<strong>RAPPORT DE DEMONSTRATION — DONNEES SIMULEES.</strong>
Aucune passation reelle, aucune norme. Les nombres de ce rapport proviennent d'un
sujet virtuel tire au sort (theta_g vrai = {d['theta_vrai']:+.3f}) avec des
saturations de plan de simulation. Ils montrent la <em>forme</em> de la sortie ;
ils n'ont aucune valeur descriptive. L'annexe de provenance est vide, et c'est la
difference decisive avec un rapport reel.</div>"""

    corps = (section_cadrage()
             + section_profil(res, 100.0, 15.0)
             + section_domaines(res, 100.0, 15.0)
             + section_total(res, 100.0, 15.0, d["sensibilite"])
             + section_residus(res)
             + section_canaux(verification)
             + section_predictions(None)
             + section_provenance(registry.table_annexe())
             + section_reproductibilite(meta))

    from scoring.pipeline import resultat_en_dict
    sortie["resultat"] = resultat_en_dict(res)
    sortie["sensibilite_r_clone"] = d["sensibilite"]
    sortie["theta_vrai_simule"] = d["theta_vrai"]
    return rendre_html(corps, bandeau, "CRIB-1 — rapport de demonstration"), sortie


def section_sans_reference(non_scorables: dict[str, Any],
                           verification: dict[str, Any]) -> str:
    tr = "".join(
        f'<tr><td class="code">{_esc(c)}</td><td>{_esc(d["nom"])}</td>'
        f'<td>{_esc(d["canal"])}</td><td>{_esc(d["source_norme_manquante"])}</td></tr>'
        for c, d in sorted(non_scorables.items()))
    src = "".join(
        f'<tr><td class="code">{_esc(k)}</td><td>{_esc(v.get("statut"))}</td>'
        f'<td class="petit">{_esc((v.get("motif") or "")[:260])}</td></tr>'
        for k, v in sorted(verification.get("sources", {}).items()))
    return f"""
<section id="sans-reference">
  <h2>2. Etat des references</h2>
  <p class="chapo">Aucun score n'est calcule. Voici pourquoi, source par source.</p>
  <table><thead><tr><th>source</th><th>statut</th><th>motif</th></tr></thead>
    <tbody>{src}</tbody></table>
  <h3>Sub-tests sans reference</h3>
  <table><thead><tr><th>code</th><th>sub-test</th><th>canal</th>
    <th>source manquante</th></tr></thead><tbody>{tr}</tbody></table>
  <div class="encadre">
    <h4>Ce que cela veut dire</h4>
    <p>La passation reste possible et la base SQLite enregistre chaque essai au
    grain le plus fin. Ce qui manque est la <em>reference</em> : sans elle, un
    score brut n'est pas interpretable, et le programme refuse de lui en inventer
    une. Relancer <code>python3 fetch_norms.py</code> depuis un poste ayant acces
    au reseau public, puis <code>python3 verify_norms.py</code>, puis regenerer ce
    rapport.</p>
  </div>
</section>"""


def _module_present(nom: str) -> bool:
    try:
        __import__(nom)
        return True
    except Exception:  # noqa: BLE001
        return False


def _version(nom: str) -> str:
    try:
        return __import__(nom).__version__
    except Exception:  # noqa: BLE001
        return "absent"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(RACINE))
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="CRIB-1 — generation du rapport")
    ap.add_argument("--demo-simulation", action="store_true",
                    help="rapport de demonstration sur donnees simulees, estampille")
    ap.add_argument("--graine", type=int, default=20240117)
    ap.add_argument("--r-clone", type=float, default=0.80)
    ap.add_argument("--sortie-html", type=Path, default=SORTIE_HTML)
    ap.add_argument("--sortie-json", type=Path, default=SORTIE_JSON)
    args = ap.parse_args()

    args.sortie_html = args.sortie_html.resolve()
    args.sortie_json = args.sortie_json.resolve()
    html_txt, json_obj = construire(args.demo_simulation, args.graine, args.r_clone)

    erreurs = verifier_sortie(json_obj)
    if erreurs:
        print("REFUS — le rapport viole la regle de provenance (T4) :")
        for e in erreurs:
            print(f"  {e}")
        return 1

    args.sortie_html.parent.mkdir(parents=True, exist_ok=True)
    args.sortie_html.write_text(html_txt, encoding="utf-8")
    args.sortie_json.write_text(
        json.dumps(json_obj, indent=2, ensure_ascii=False, sort_keys=True, default=str),
        encoding="utf-8")
    print(f"HTML : {_rel(args.sortie_html)}  ({len(html_txt)//1024} ko)")
    print(f"JSON : {_rel(args.sortie_json)}")
    print(f"mode : {json_obj['meta']['mode']}")
    print(f"normes employees : {len(json_obj['normes_employees'])} | "
          f"annexe provenance : {len(json_obj['annexe_provenance'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
