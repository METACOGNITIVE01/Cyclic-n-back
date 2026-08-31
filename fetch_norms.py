#!/usr/bin/env python3
"""CRIB-1 §1 — Acquisition des donnees normatives.

Telecharge, verifie et enregistre les trois sources declarees dans
config/sources.json. Ecrit data/raw/MANIFEST.json (SHA-256, tailles, comptes de
lignes observes, URL, horodatage).

REGLE ABSOLUE (§1, R1) : si un telechargement echoue, ce script s'arrete, dit
lequel, et ne substitue RIEN. Il n'ecrit jamais de valeur de remplacement, ne
devine aucun compte de lignes, et ne recopie aucun chiffre depuis la
documentation. Les champs `advisory_*` de config/sources.json proviennent de
l'enonce humain : ils servent de garde-fou de coherence et sont signales comme
non verifies. Ils ne sont jamais utilises par scoring/.

Usage :
    python3 fetch_norms.py                # tout
    python3 fetch_norms.py --source NCPT  # une seule source
    python3 fetch_norms.py --dry-run      # teste seulement l'accessibilite reseau
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from scoring.provenance import sha256_fichier  # noqa: E402

DATA_RAW = RACINE / "data" / "raw"
MANIFEST = DATA_RAW / "MANIFEST.json"
SOURCES = RACINE / "config" / "sources.json"

TIMEOUT = 120
N_TENTATIVES = 4
BACKOFF = [2, 4, 8, 16]
UA = "CRIB-1/1.0 (batterie cognitive locale ; acquisition de normes publiques)"


class EchecTelechargement(RuntimeError):
    """Un telechargement obligatoire a echoue. Rien n'est substitue."""

    def __init__(self, source_id: str, url: str, motif: str, categorie: str):
        self.source_id = source_id
        self.url = url
        self.motif = motif
        self.categorie = categorie  # "politique_reseau" | "http" | "reseau" | "contenu"
        super().__init__(f"[{source_id}] {url}\n    categorie : {categorie}\n    motif : {motif}")


# ---------------------------------------------------------------------------
# Couche reseau
# ---------------------------------------------------------------------------
def _classer_erreur(exc: Exception) -> tuple[str, str]:
    """Distingue un refus de politique d'egress d'une panne reseau ordinaire."""
    texte = f"{type(exc).__name__}: {exc}"
    marqueurs_politique = (
        "CONNECT tunnel failed", "response 403", "403 Forbidden",
        "ProxyError", "Tunnel connection failed",
    )
    if any(m in texte for m in marqueurs_politique):
        return "politique_reseau", texte
    return "reseau", texte


def http_get(url: str, source_id: str, *, stream: bool = False,
             accept: str | None = None) -> requests.Response:
    """GET avec retentatives a backoff exponentiel. Ne masque aucun echec."""
    entetes = {"User-Agent": UA}
    if accept:
        entetes["Accept"] = accept
    derniere: Exception | None = None
    for i in range(N_TENTATIVES):
        try:
            rep = requests.get(url, headers=entetes, timeout=TIMEOUT, stream=stream)
        except Exception as exc:  # noqa: BLE001
            derniere = exc
            categorie, _ = _classer_erreur(exc)
            if categorie == "politique_reseau":
                # Un refus de politique ne se resout pas par retentative (README du proxy).
                raise EchecTelechargement(
                    source_id, url,
                    f"la politique d'egress de cette session refuse l'hote. Detail : {exc}",
                    "politique_reseau",
                ) from exc
            if i < N_TENTATIVES - 1:
                time.sleep(BACKOFF[i])
            continue
        if rep.status_code == 200:
            return rep
        if rep.status_code in (403, 407):
            raise EchecTelechargement(
                source_id, url,
                f"HTTP {rep.status_code} — acces refuse (politique d'egress ou acces restreint amont)",
                "politique_reseau",
            )
        if rep.status_code in (429, 500, 502, 503, 504) and i < N_TENTATIVES - 1:
            time.sleep(BACKOFF[i])
            derniere = RuntimeError(f"HTTP {rep.status_code}")
            continue
        raise EchecTelechargement(source_id, url, f"HTTP {rep.status_code}", "http")
    categorie, detail = _classer_erreur(derniere) if derniere else ("reseau", "inconnu")
    raise EchecTelechargement(source_id, url, f"{N_TENTATIVES} tentatives echouees : {detail}", categorie)


def ecrire(chemin: Path, contenu: bytes) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)


# ---------------------------------------------------------------------------
# Comptages observes (jamais devines)
# ---------------------------------------------------------------------------
def compter_lignes_csv(chemin: Path) -> dict[str, Any]:
    """Compte les lignes de donnees et releve les colonnes REELLEMENT presentes."""
    try:
        texte = chemin.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        texte = chemin.read_text(encoding="latin-1")
    dialecte = csv.Sniffer().sniff(texte[:8192], delimiters=",;\t") if texte[:8192].strip() else csv.excel
    lecteur = csv.reader(io.StringIO(texte), dialecte)
    try:
        entete = next(lecteur)
    except StopIteration:
        return {"n_lignes_donnees": 0, "colonnes": [], "separateur": dialecte.delimiter}
    n = sum(1 for ligne in lecteur if any(c.strip() for c in ligne))
    return {
        "n_lignes_donnees": n,
        "colonnes": [c.strip() for c in entete],
        "separateur": dialecte.delimiter,
    }


def decrire_fichier(chemin: Path, source_id: str, url: str) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source_id": source_id,
        "chemin": str(chemin.relative_to(RACINE)),
        "nom": chemin.name,
        "octets": chemin.stat().st_size,
        "sha256": sha256_fichier(chemin),
        "url": url,
        "telecharge_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if chemin.suffix.lower() in (".csv", ".tsv", ".tab"):
        try:
            meta["csv"] = compter_lignes_csv(chemin)
        except Exception as exc:  # noqa: BLE001
            meta["csv_erreur"] = f"{type(exc).__name__}: {exc}"
    return meta


# ---------------------------------------------------------------------------
# A. ICAR / SAPA — Harvard Dataverse
# ---------------------------------------------------------------------------
def fetch_icar(src: dict[str, Any]) -> list[dict[str, Any]]:
    sid = src["id"]
    dest = DATA_RAW / "icar_sapa"
    acces = src["acces"]
    print(f"  interrogation du dataset Dataverse (DOI {src['doi']}) ...")
    rep = http_get(acces["api_dataset"], sid, accept="application/json")
    meta = rep.json()
    ecrire(dest / "_dataverse_dataset.json", json.dumps(meta, indent=2, ensure_ascii=False).encode())

    try:
        fichiers = meta["data"]["latestVersion"]["files"]
    except (KeyError, TypeError) as exc:
        raise EchecTelechargement(
            sid, acces["api_dataset"],
            "reponse Dataverse inattendue : pas de latestVersion.files", "contenu",
        ) from exc

    if not fichiers:
        raise EchecTelechargement(sid, acces["api_dataset"], "dataset sans fichier", "contenu")

    manifeste: list[dict[str, Any]] = []
    for f in fichiers:
        df = f.get("dataFile", {})
        nom = df.get("filename") or f.get("label")
        fid = df.get("id")
        if fid is None or not nom:
            continue
        url = acces["api_fichier"].format(id=fid)
        print(f"    -> {nom}")
        r = http_get(url, sid, stream=True)
        chemin = dest / nom
        ecrire(chemin, r.content)
        d = decrire_fichier(chemin, sid, url)
        d["dataverse_id"] = fid
        d["md5_dataverse"] = df.get("md5") or df.get("checksum", {}).get("value")
        manifeste.append(d)

    print(f"  documentation descriptive : {src['documentation']}")
    try:
        r = http_get(src["documentation"], sid)
        ecrire(dest / "_article_descriptif.html", r.content)
        manifeste.append(decrire_fichier(dest / "_article_descriptif.html", sid, src["documentation"]))
    except EchecTelechargement as exc:
        # La doc est un complement, pas une norme : on signale sans substituer.
        print(f"  AVERTISSEMENT : article descriptif non recupere ({exc.categorie}). "
              f"Aucune valeur n'en depend.")
    return manifeste


# ---------------------------------------------------------------------------
# B. NCPT — Zenodo
# ---------------------------------------------------------------------------
def fetch_ncpt(src: dict[str, Any]) -> list[dict[str, Any]]:
    sid = src["id"]
    dest = DATA_RAW / "ncpt"
    acces = src["acces"]
    print(f"  interrogation du record Zenodo {acces['record']} ...")
    rep = http_get(acces["api_record"], sid, accept="application/json")
    meta = rep.json()
    ecrire(dest / "_zenodo_record.json", json.dumps(meta, indent=2, ensure_ascii=False).encode())

    fichiers = meta.get("files") or []
    if not fichiers:
        raise EchecTelechargement(sid, acces["api_record"], "record sans fichier", "contenu")

    motif = re.compile(src["motif_fichiers"], re.IGNORECASE)
    cibles = [f for f in fichiers if motif.search(f.get("key") or f.get("filename") or "")]
    if not cibles:
        noms = [f.get("key") or f.get("filename") for f in fichiers]
        raise EchecTelechargement(
            sid, acces["api_record"],
            f"aucun fichier ne correspond a {src['motif_fichiers']!r}. Presents : {noms}",
            "contenu",
        )

    manifeste: list[dict[str, Any]] = []
    for f in cibles:
        nom = f.get("key") or f.get("filename")
        url = (f.get("links", {}) or {}).get("self") or (f.get("links", {}) or {}).get("download")
        if not url:
            raise EchecTelechargement(sid, acces["api_record"], f"pas d'URL pour {nom}", "contenu")
        print(f"    -> {nom}")
        r = http_get(url, sid, stream=True)
        chemin = dest / nom
        ecrire(chemin, r.content)
        d = decrire_fichier(chemin, sid, url)
        d["checksum_zenodo"] = f.get("checksum")
        manifeste.append(d)

    trouvees = sorted({m for c in manifeste
                       for m in re.findall(r"battery(\d+)", c["nom"], re.IGNORECASE)})
    print(f"  batteries trouvees dans les noms de fichiers : {trouvees}")
    attendues = {str(b) for b in src.get("batteries_attendues", [])}
    manquantes = sorted(attendues - set(trouvees))
    if manquantes:
        print(f"  AVERTISSEMENT : batteries attendues absentes : {manquantes} "
              f"(attente issue de l'enonce, non verifiee en amont)")
    return manifeste


# ---------------------------------------------------------------------------
# C. UK Biobank — champ 20016
# ---------------------------------------------------------------------------
def _extraire_ukb(html: str) -> dict[str, Any]:
    """Extrait N / moyenne / ecart-type / mediane et la table 0-13 SI presents.

    N'invente rien : toute valeur absente de la page reste absente du resultat.
    """
    texte = re.sub(r"<[^>]+>", " ", html)
    texte = re.sub(r"&nbsp;?", " ", texte)
    texte = re.sub(r"\s+", " ", texte)
    out: dict[str, Any] = {"_methode": "regex sur le HTML brut telecharge ; aucune valeur devinee"}

    motifs = {
        "N": r"(?:Count|N)\s*[:=]?\s*([0-9][0-9\s,]{2,})",
        "moyenne": r"Mean\s*[:=]?\s*(-?\d+\.?\d*)",
        "ecart_type": r"(?:Std\.?\s*dev\.?|Standard deviation|SD)\s*[:=]?\s*(-?\d+\.?\d*)",
        "mediane": r"Median\s*[:=]?\s*(-?\d+\.?\d*)",
    }
    for cle, motif in motifs.items():
        m = re.search(motif, texte, re.IGNORECASE)
        if m:
            brut = m.group(1).replace(",", "").replace(" ", "")
            try:
                out[cle] = float(brut) if "." in brut else int(brut)
                out[f"{cle}_contexte"] = texte[max(0, m.start() - 80):m.end() + 80].strip()
            except ValueError:
                pass

    # Table de frequence par valeur 0-13, si la page en publie une.
    freq: dict[str, int] = {}
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL):
        cellules = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.IGNORECASE | re.DOTALL)
        cellules = [re.sub(r"<[^>]+>", "", c).strip() for c in cellules]
        if len(cellules) >= 2 and re.fullmatch(r"\d{1,2}", cellules[0]):
            val = int(cellules[0])
            if 0 <= val <= 13:
                cpt = cellules[1].replace(",", "").replace(" ", "").strip()
                if re.fullmatch(r"\d+", cpt):
                    freq[str(val)] = int(cpt)
    if freq:
        out["table_frequence_0_13"] = dict(sorted(freq.items(), key=lambda kv: int(kv[0])))
    else:
        out["table_frequence_0_13"] = None
        out["_note_table"] = "aucune table de frequence 0-13 detectee dans le HTML telecharge"
    return out


def fetch_ukb(src: dict[str, Any]) -> list[dict[str, Any]]:
    sid = src["id"]
    dest = DATA_RAW / "ukb_20016"
    acces = src["acces"]
    manifeste: list[dict[str, Any]] = []

    print(f"  page du champ 20016 ...")
    r = http_get(acces["page_champ"], sid)
    chemin_html = dest / "field_20016.html"
    ecrire(chemin_html, r.content)
    manifeste.append(decrire_fichier(chemin_html, sid, acces["page_champ"]))

    extraits = _extraire_ukb(r.content.decode("utf-8", errors="replace"))
    extraits["_source_html"] = str(chemin_html.relative_to(RACINE))
    extraits["_sha256_html"] = sha256_fichier(chemin_html)
    extraits["_url"] = acces["page_champ"]
    chemin_extraits = dest / "field_20016_extraits.json"
    ecrire(chemin_extraits, json.dumps(extraits, indent=2, ensure_ascii=False).encode())
    manifeste.append(decrire_fichier(chemin_extraits, sid, acces["page_champ"]))
    print(f"    extraits : {[k for k in extraits if not k.startswith('_')]}")

    print(f"  PDF de description des items ...")
    try:
        r = http_get(acces["pdf_items"], sid, stream=True)
        chemin_pdf = dest / "Fluidintelligence.pdf"
        ecrire(chemin_pdf, r.content)
        manifeste.append(decrire_fichier(chemin_pdf, sid, acces["pdf_items"]))
    except EchecTelechargement as exc:
        print(f"  AVERTISSEMENT : PDF non recupere ({exc.categorie}). "
              f"K2 restera sans enonces d'items exacts.")
    return manifeste


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
FETCHERS = {"ICAR_SAPA": fetch_icar, "NCPT": fetch_ncpt, "UKB_20016": fetch_ukb}


def dry_run(sources: list[dict[str, Any]]) -> int:
    print("Test d'accessibilite reseau (aucun fichier ecrit)\n")
    echecs = 0
    for src in sources:
        hote = src["acces"]["hote"]
        url = f"https://{hote}/"
        try:
            requests.head(url, timeout=30, headers={"User-Agent": UA}, allow_redirects=True)
            print(f"  {src['id']:<12} {hote:<34} ATTEIGNABLE")
        except Exception as exc:  # noqa: BLE001
            categorie, detail = _classer_erreur(exc)
            print(f"  {src['id']:<12} {hote:<34} ECHEC ({categorie})")
            print(f"               {detail[:150]}")
            echecs += 1
    return 1 if echecs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CRIB-1 §1 — acquisition des normes")
    ap.add_argument("--source", action="append", choices=list(FETCHERS),
                    help="limiter a une ou plusieurs sources")
    ap.add_argument("--dry-run", action="store_true",
                    help="tester seulement l'accessibilite des hotes")
    args = ap.parse_args()

    config = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = [s for s in config["sources"]
               if not args.source or s["id"] in args.source]

    if args.dry_run:
        return dry_run(sources)

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"fichiers": {}, "sources": {}, "echecs": {}}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest.setdefault("echecs", {})

    fatal: EchecTelechargement | None = None
    for src in sources:
        sid = src["id"]
        print(f"\n=== {sid} — {src['titre']} ===")
        try:
            entrees = FETCHERS[sid](src)
        except EchecTelechargement as exc:
            manifest["echecs"][sid] = {
                "url": exc.url, "categorie": exc.categorie, "motif": exc.motif,
                "obligatoire": src.get("obligatoire", True),
                "constate_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            manifest["sources"].pop(sid, None)
            print(f"\n  ECHEC — {exc}")
            if src.get("obligatoire", True):
                fatal = exc
                break
            continue

        for e in entrees:
            manifest["fichiers"][e["chemin"]] = e
        manifest["echecs"].pop(sid, None)
        manifest["sources"][sid] = {
            "titre": src["titre"],
            "licence": src.get("licence", ""),
            "doi": src.get("doi", ""),
            "n_fichiers": len(entrees),
            "telecharge_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "advisory_n_sujets": src.get("advisory_n_sujets"),
            "advisory_source": src.get("advisory_source", ""),
            "_note_advisory": ("valeur issue de l'enonce humain, non verifiee en amont ; "
                               "garde-fou de coherence uniquement, interdite dans scoring/"),
        }
        print(f"  OK — {len(entrees)} fichier(s) enregistre(s)")

    manifest["ecrit_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
                        encoding="utf-8")
    print(f"\nManifeste ecrit : {MANIFEST.relative_to(RACINE)}")

    if fatal is not None:
        print("\n" + "=" * 72)
        print("ARRET — telechargement obligatoire echoue. Rien n'a ete substitue.")
        print(f"  source    : {fatal.source_id}")
        print(f"  url       : {fatal.url}")
        print(f"  categorie : {fatal.categorie}")
        print(f"  motif     : {fatal.motif}")
        if fatal.categorie == "politique_reseau":
            print("\n  Cet hote est refuse par la politique d'egress de la session.")
            print("  Rejouer ce script depuis un poste ayant acces au reseau public.")
        print("=" * 72)
        return 2

    if manifest["echecs"]:
        print(f"\nSources facultatives en echec : {sorted(manifest['echecs'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
