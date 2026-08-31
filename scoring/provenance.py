"""R1 — Provenance. Le coeur du dispositif.

Regle appliquee ici, mecaniquement :

    Aucune valeur normative ne peut etre produite par ce programme si elle ne
    provient pas d'un fichier reellement present sur ce disque, identifie par
    chemin + colonne + index de ligne + SHA-256.

Consequences implementees :
  * `ProvenanceRegistry.norme(...)` est le SEUL point d'entree des valeurs
    normatives. Il renvoie un `NormValue` (valeur + identifiant de provenance)
    ou leve `NoReferenceError`.
  * Toute lecture est inscrite dans un registre d'usage (`ledger`), qui alimente
    l'annexe « provenance » du rapport et le test d'acceptation T4.
  * Il n'existe aucun moyen d'obtenir un float normatif sans passer par la, et
    aucune valeur normative n'est ecrite en dur dans le code source.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator

RACINE = Path(__file__).resolve().parent.parent
DATA_RAW = RACINE / "data" / "raw"
MANIFEST = DATA_RAW / "MANIFEST.json"


class NoReferenceError(LookupError):
    """Levee quand une norme demandee n'est pas disponible sur ce disque.

    L'appelant DOIT traiter cette exception en excluant le sub-test du score et
    en affichant « pas de reference ». Il ne doit jamais lui substituer une
    valeur (R1).
    """

    def __init__(self, cle: str, motif: str):
        self.cle = cle
        self.motif = motif
        super().__init__(f"pas de reference pour {cle!r} : {motif}")


@dataclass(frozen=True)
class ProvenanceRecord:
    """Tracabilite complete d'une valeur normative unique."""
    provenance_id: str
    source_id: str          # ICAR_SAPA | NCPT | UKB_20016
    fichier: str            # chemin relatif a la racine du projet
    sha256: str
    colonne: str
    index_ligne: int        # index de ligne 0-base dans le fichier (-1 = scalaire de page)
    valeur: float | str
    description: str
    telecharge_le: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_fichier(chemin: Path, taille_bloc: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        while bloc := f.read(taille_bloc):
            h.update(bloc)
    return h.hexdigest()


@dataclass(frozen=True)
class NormValue:
    """Une valeur normative, indissociable de sa provenance.

    On ne peut pas l'utiliser sans passer par `.get(registry)`, qui inscrit
    l'usage au registre. C'est ce qui rend l'annexe de provenance exhaustive
    par construction plutot que par discipline.
    """
    valeur: float
    provenance_id: str

    def get(self, registry: "ProvenanceRegistry") -> float:
        registry.marquer_usage(self.provenance_id)
        return self.valeur

    def __float__(self) -> float:  # pragma: no cover - garde-fou
        raise TypeError(
            "Une NormValue ne se convertit pas implicitement en float. "
            "Utiliser .get(registry) pour inscrire l'usage au registre de provenance (R1)."
        )


class ProvenanceRegistry:
    """Index des fichiers bruts verifies + registre d'usage des normes."""

    def __init__(self, manifest_path: Path = MANIFEST, racine: Path = RACINE):
        self.racine = racine
        self.manifest_path = manifest_path
        self._manifest: dict[str, Any] = {}
        self._records: dict[str, ProvenanceRecord] = {}
        self._ledger: list[str] = []
        self._indisponibles: dict[str, str] = {}
        self._charger_manifest()

    # ---------------------------------------------------------------- manifest
    def _charger_manifest(self) -> None:
        if not self.manifest_path.exists():
            self._manifest = {"fichiers": {}, "sources": {}}
            return
        self._manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    @property
    def fichiers(self) -> dict[str, Any]:
        return self._manifest.get("fichiers", {})

    def source_disponible(self, source_id: str) -> bool:
        """Vrai si au moins un fichier verifie existe pour cette source."""
        for meta in self.fichiers.values():
            if meta.get("source_id") == source_id and (self.racine / meta["chemin"]).exists():
                return True
        return False

    def fichiers_de(self, source_id: str) -> list[dict[str, Any]]:
        return [m for m in self.fichiers.values() if m.get("source_id") == source_id]

    # -------------------------------------------------------------- disponible
    def declarer_indisponible(self, cle: str, motif: str) -> None:
        self._indisponibles[cle] = motif

    @property
    def indisponibles(self) -> dict[str, str]:
        return dict(self._indisponibles)

    # ------------------------------------------------------------------ normes
    def enregistrer(self, rec: ProvenanceRecord) -> NormValue:
        """Enregistre une valeur normative extraite d'un fichier verifie."""
        existant = self._records.get(rec.provenance_id)
        if existant is not None and existant != rec:
            raise ValueError(
                f"conflit de provenance sur {rec.provenance_id!r} : "
                "deux valeurs differentes revendiquent le meme identifiant"
            )
        self._records[rec.provenance_id] = rec
        if not isinstance(rec.valeur, (int, float)):
            raise TypeError("NormValue n'accepte qu'une valeur numerique")
        return NormValue(valeur=float(rec.valeur), provenance_id=rec.provenance_id)

    def norme(self, provenance_id: str) -> NormValue:
        rec = self._records.get(provenance_id)
        if rec is None:
            motif = self._indisponibles.get(
                provenance_id, "aucun fichier telecharge ne fournit cette valeur"
            )
            raise NoReferenceError(provenance_id, motif)
        return NormValue(valeur=float(rec.valeur), provenance_id=provenance_id)

    def marquer_usage(self, provenance_id: str) -> None:
        if provenance_id not in self._records:
            raise NoReferenceError(provenance_id, "usage d'une norme absente du registre")
        self._ledger.append(provenance_id)

    # ------------------------------------------------------------------ sortie
    @property
    def ledger(self) -> list[str]:
        return list(self._ledger)

    def records_utilises(self) -> list[ProvenanceRecord]:
        vus: dict[str, ProvenanceRecord] = {}
        for pid in self._ledger:
            vus[pid] = self._records[pid]
        return sorted(vus.values(), key=lambda r: r.provenance_id)

    def table_annexe(self) -> list[dict[str, Any]]:
        """Annexe « provenance » du rapport (§6.8) : chaque norme employee."""
        return [r.to_dict() for r in self.records_utilises()]

    def __iter__(self) -> Iterator[ProvenanceRecord]:
        return iter(sorted(self._records.values(), key=lambda r: r.provenance_id))

    def __len__(self) -> int:
        return len(self._records)


def id_norme(source_id: str, fichier: str, colonne: str, ligne: int) -> str:
    """Identifiant de provenance canonique, stable et lisible."""
    tige = Path(fichier).name
    return f"{source_id}:{tige}:{colonne}:L{ligne}"
