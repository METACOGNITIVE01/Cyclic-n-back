"""Graphiques SVG en ligne pour le rapport autonome (aucune ressource externe)."""
from __future__ import annotations

import html
from typing import Sequence


def _esc(t: str) -> str:
    return html.escape(str(t), quote=True)


def barres_intervalles(lignes: Sequence[dict], *, largeur: int = 720,
                       hauteur_ligne: int = 34, xmin: float = -3.0,
                       xmax: float = 3.0, unite: str = "z",
                       zero: float = 0.0) -> str:
    """Profil trie avec barre d'erreur visible (§6.2).

    `lignes` : [{etiquette, point, bas, haut, note}]
    """
    if not lignes:
        return '<p class="vide">aucun sub-test scorable</p>'
    marge_g, marge_d, marge_h, marge_b = 190, 26, 24, 34
    h = marge_h + marge_b + hauteur_ligne * len(lignes)
    ech = lambda v: marge_g + (v - xmin) / (xmax - xmin) * (largeur - marge_g - marge_d)

    out = [f'<svg class="graphe" viewBox="0 0 {largeur} {h}" role="img" '
           f'aria-label="profil avec intervalles a 90 %">']
    # graduations
    pas = 1.0 if (xmax - xmin) <= 8 else 10.0
    v = xmin
    while v <= xmax + 1e-9:
        x = ech(v)
        out.append(f'<line class="grille" x1="{x:.1f}" y1="{marge_h-6}" '
                   f'x2="{x:.1f}" y2="{h-marge_b+4}"/>')
        out.append(f'<text class="axe" x="{x:.1f}" y="{h-marge_b+20}" '
                   f'text-anchor="middle">{v:g}</text>')
        v += pas
    xz = ech(zero)
    out.append(f'<line class="zero" x1="{xz:.1f}" y1="{marge_h-6}" '
               f'x2="{xz:.1f}" y2="{h-marge_b+4}"/>')

    for i, l in enumerate(lignes):
        y = marge_h + hauteur_ligne * i + hauteur_ligne / 2
        xb, xh, xp = ech(l["bas"]), ech(l["haut"]), ech(l["point"])
        out.append(f'<text class="etiq" x="{marge_g-12}" y="{y+4}" '
                   f'text-anchor="end">{_esc(l["etiquette"])}</text>')
        out.append(f'<line class="ic" x1="{xb:.1f}" y1="{y:.1f}" x2="{xh:.1f}" y2="{y:.1f}"/>')
        for xx in (xb, xh):
            out.append(f'<line class="ic" x1="{xx:.1f}" y1="{y-6:.1f}" '
                       f'x2="{xx:.1f}" y2="{y+6:.1f}"/>')
        out.append(f'<circle class="pt" cx="{xp:.1f}" cy="{y:.1f}" r="5"/>')
        if l.get("note"):
            out.append(f'<text class="note" x="{ech(xmax)+4}" y="{y+4}">{_esc(l["note"])}</text>')
    out.append(f'<text class="axe" x="{largeur/2}" y="{h-4}" text-anchor="middle">'
               f'{_esc(unite)} — barres : intervalle a 90 %</text>')
    out.append('</svg>')
    return "\n".join(out)


def courbe_posterieur(theta: Sequence[float], densite: Sequence[float],
                      hdi: tuple[float, float], moyenne: float, *,
                      largeur: int = 720, hauteur: int = 240) -> str:
    """Courbe complete du posterieur de theta_g (§5.2, §6.4)."""
    if not theta:
        return '<p class="vide">pas de posterieur</p>'
    mg, md, mh, mb = 44, 16, 16, 34
    xmin, xmax = min(theta), max(theta)
    dmax = max(densite) or 1.0
    ex = lambda v: mg + (v - xmin) / (xmax - xmin) * (largeur - mg - md)
    ey = lambda v: hauteur - mb - (v / dmax) * (hauteur - mh - mb)

    aire = [f'{ex(t):.1f},{ey(d):.1f}' for t, d in zip(theta, densite)
            if hdi[0] <= t <= hdi[1]]
    trace = " ".join(f'{ex(t):.1f},{ey(d):.1f}' for t, d in zip(theta, densite))

    out = [f'<svg class="graphe" viewBox="0 0 {largeur} {hauteur}" role="img" '
           f'aria-label="courbe du posterieur de theta_g">']
    for v in range(int(xmin), int(xmax) + 1):
        x = ex(v)
        out.append(f'<line class="grille" x1="{x:.1f}" y1="{mh}" x2="{x:.1f}" y2="{hauteur-mb}"/>')
        out.append(f'<text class="axe" x="{x:.1f}" y="{hauteur-mb+18}" '
                   f'text-anchor="middle">{v}</text>')
    if aire:
        out.append(f'<polygon class="hdi" points="{aire[0].split(",")[0]},{ey(0):.1f} '
                   + " ".join(aire) + f' {aire[-1].split(",")[0]},{ey(0):.1f}"/>')
    out.append(f'<polyline class="courbe" points="{trace}"/>')
    xm = ex(moyenne)
    out.append(f'<line class="moy" x1="{xm:.1f}" y1="{mh}" x2="{xm:.1f}" y2="{hauteur-mb}"/>')
    out.append(f'<text class="axe" x="{largeur/2}" y="{hauteur-4}" text-anchor="middle">'
               f'theta_g — zone ombree : intervalle de plus haute densite a 90 %</text>')
    out.append('</svg>')
    return "\n".join(out)


def barres_variance(parts: dict[str, float | None], *, largeur: int = 720,
                    hauteur: int = 150) -> str:
    """Part de VARIANCE de chaque composante du budget (§5.6, §6.4)."""
    noms = list(parts)
    mg, md, mh, mb = 90, 60, 14, 26
    hl = (hauteur - mh - mb) / max(1, len(noms))
    out = [f'<svg class="graphe" viewBox="0 0 {largeur} {hauteur}" role="img" '
           f'aria-label="part de variance par composante">']
    for i, n in enumerate(noms):
        y = mh + i * hl
        p = parts[n]
        out.append(f'<text class="etiq" x="{mg-10}" y="{y+hl/2+4}" text-anchor="end">'
                   f'{_esc(n)}</text>')
        if p is None:
            out.append(f'<text class="absent" x="{mg+4}" y="{y+hl/2+4}">'
                       f'non quantifiable — sigma_total est une borne inferieure</text>')
            continue
        w = p * (largeur - mg - md)
        out.append(f'<rect class="barre" x="{mg}" y="{y+4:.1f}" width="{w:.1f}" '
                   f'height="{hl-8:.1f}" rx="3"/>')
        out.append(f'<text class="val" x="{mg+w+6:.1f}" y="{y+hl/2+4:.1f}">'
                   f'{p*100:.0f} %</text>')
    out.append('</svg>')
    return "\n".join(out)
