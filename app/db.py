"""Base SQLite des donnees brutes de passation (§7).

« une ligne par essai : item, reponse, latence en ms, horodatage monotone »

Rien n'est agrege ici : la base garde le grain le plus fin, y compris les
demonstrations et les essais de qualification, pour que le scoring puisse etre
rejoue sans repasser le test (R2).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_DB = RACINE / "data" / "derived" / "crib1.sqlite"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sujet (
    id                TEXT PRIMARY KEY,
    age_annees        INTEGER NOT NULL,
    sexe              TEXT NOT NULL,
    langue            TEXT NOT NULL,
    main_dominante    TEXT,
    niveau_education  TEXT NOT NULL,
    cree_le           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    sujet_id          TEXT NOT NULL REFERENCES sujet(id),
    numero            INTEGER NOT NULL,
    graine            INTEGER NOT NULL,
    ordre_taches      TEXT NOT NULL,
    debut_utc         TEXT NOT NULL,
    fin_utc           TEXT,
    fuseau_local      TEXT,
    refresh_hz_initial REAL,
    statut            TEXT NOT NULL DEFAULT 'en_cours',
    UNIQUE (sujet_id, numero)
);

CREATE TABLE IF NOT EXISTS questionnaire (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES session(id),
    moment      TEXT NOT NULL CHECK (moment IN ('avant','apres')),
    cle         TEXT NOT NULL,
    valeur      REAL,
    valeur_texte TEXT,
    horodatage_utc TEXT NOT NULL,
    UNIQUE (session_id, moment, cle)
);

CREATE TABLE IF NOT EXISTS tache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES session(id),
    code            TEXT NOT NULL,
    rang            INTEGER NOT NULL,
    mode_items      TEXT NOT NULL,
    graine_tache    INTEGER NOT NULL,
    qualifie        INTEGER,
    statut          TEXT NOT NULL DEFAULT 'en_attente',
    motif_non_score TEXT,
    debut_utc       TEXT,
    fin_utc         TEXT,
    UNIQUE (session_id, code)
);

CREATE TABLE IF NOT EXISTS essai (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tache_id          INTEGER NOT NULL REFERENCES tache(id),
    phase             TEXT NOT NULL CHECK (phase IN ('demo','qualification','test')),
    index_essai       INTEGER NOT NULL,
    item              TEXT NOT NULL,
    reponse           TEXT,
    correct           INTEGER,
    latence_ms        REAL,
    latence_corrigee_ms REAL,
    t_monotone_ms     REAL NOT NULL,
    horodatage_utc    TEXT NOT NULL,
    item_facile       INTEGER NOT NULL DEFAULT 0,
    drapeaux          TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_essai_tache ON essai(tache_id, phase, index_essai);

CREATE TABLE IF NOT EXISTS chronometrie (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    tache_id              INTEGER NOT NULL REFERENCES tache(id),
    refresh_hz_median     REAL,
    refresh_hz_min        REAL,
    refresh_hz_max        REAL,
    variation_relative    REAL,
    latence_affichage_ms  REAL,
    n_frames              INTEGER,
    passation_refusee     INTEGER NOT NULL DEFAULT 0,
    motif                 TEXT,
    horodatage_utc        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS controle_effort (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tache_id       INTEGER NOT NULL REFERENCES tache(id),
    type           TEXT NOT NULL,
    detail         TEXT NOT NULL,
    horodatage_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pause (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER NOT NULL REFERENCES session(id),
    apres_rang     INTEGER NOT NULL,
    duree_s        REAL NOT NULL,
    respectee      INTEGER NOT NULL,
    horodatage_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER REFERENCES session(id),
    niveau         TEXT NOT NULL,
    message        TEXT NOT NULL,
    detail         TEXT,
    horodatage_utc TEXT NOT NULL
);
"""


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


#: FastAPI execute les routes synchrones dans un pool de threads : la connexion
#: doit donc etre partageable entre threads, et les ecritures serialisees par un
#: verrou. C'est suffisant et correct pour une application locale mono-sujet.
_VERROU = threading.RLock()


def connecter(chemin: Path | None = None) -> sqlite3.Connection:
    chemin = chemin or CHEMIN_DB
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(chemin, isolation_level=None, check_same_thread=False,
                         timeout=30.0)
    cx.row_factory = sqlite3.Row
    with _VERROU:
        cx.executescript(SCHEMA)
    return cx


@contextmanager
def transaction(cx: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transaction serialisee : un seul thread ecrit a la fois."""
    with _VERROU:
        cx.execute("BEGIN IMMEDIATE")
        try:
            yield cx
        except Exception:
            cx.execute("ROLLBACK")
            raise
        else:
            cx.execute("COMMIT")


def lire(cx: sqlite3.Connection, requete: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Lecture serialisee par le meme verrou que les ecritures."""
    with _VERROU:
        return cx.execute(requete, params).fetchall()


def journaliser(cx: sqlite3.Connection, niveau: str, message: str,
                session_id: int | None = None, detail: Any = None) -> None:
    cx.execute(
        "INSERT INTO journal (session_id, niveau, message, detail, horodatage_utc) "
        "VALUES (?,?,?,?,?)",
        (session_id, niveau, message,
         json.dumps(detail, ensure_ascii=False) if detail is not None else None,
         maintenant()))


def enregistrer_essai(cx: sqlite3.Connection, tache_id: int, phase: str,
                      index_essai: int, item: dict[str, Any], reponse: Any,
                      correct: bool | None, latence_ms: float | None,
                      latence_corrigee_ms: float | None, t_monotone_ms: float,
                      item_facile: bool = False,
                      drapeaux: list[str] | None = None) -> int:
    cur = cx.execute(
        "INSERT INTO essai (tache_id, phase, index_essai, item, reponse, correct, "
        "latence_ms, latence_corrigee_ms, t_monotone_ms, horodatage_utc, "
        "item_facile, drapeaux) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (tache_id, phase, index_essai, json.dumps(item, ensure_ascii=False, sort_keys=True),
         json.dumps(reponse, ensure_ascii=False) if reponse is not None else None,
         None if correct is None else int(correct),
         latence_ms, latence_corrigee_ms, t_monotone_ms, maintenant(),
         int(item_facile), json.dumps(drapeaux or [], ensure_ascii=False)))
    return int(cur.lastrowid)


def essais_de(cx: sqlite3.Connection, tache_id: int,
              phase: str | None = None) -> list[sqlite3.Row]:
    if phase:
        return lire(cx, "SELECT * FROM essai WHERE tache_id=? AND phase=? "
                        "ORDER BY index_essai", (tache_id, phase))
    return lire(cx, "SELECT * FROM essai WHERE tache_id=? ORDER BY phase, index_essai",
                (tache_id,))
