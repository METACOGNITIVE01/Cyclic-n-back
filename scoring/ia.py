"""§5.4 — Indice d'adequation descriptive (IA).

    IA = 1 - somme_j max(r_j^2 - psi_j, 0) / somme_j max(z_j^2 - psi_j, 0)

Choix explicite de psi_j : c'est la variance d'ERREUR DE MESURE (non-fidelite),
pas la variance residuelle totale. Justification : §5.4 dit que sans cette
soustraction « un sub-test peu fidele est compte comme de l'heterogeneite
reelle ». Ce qu'il faut retirer est donc le bruit de mesure. La variance de
facteur specifique, elle, EST de l'heterogeneite reelle et doit rester comptee.

Quand la fidelite d'un sub-test n'est pas connue depuis une source telechargee,
psi_j vaut 0 : l'IA est alors CONSERVATEUR (il attribue a l'heterogeneite du
bruit qui n'en est peut-etre pas). Ce cas est signale dans le rapport.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from scoring.model import Observation

PALIER_NORMAL = "total_presente_normalement"
PALIER_SECOND_PLAN = "total_second_plan"
PALIER_RETROGRADE = "total_retrograde"


def indice_adequation(observations: Sequence[Observation], theta_g: float
                      ) -> dict[str, object]:
    obs = [o for o in observations if o.scorable]
    z = np.array([o.z for o in obs])
    lg = np.array([o.lambda_g for o in obs])
    psi_mesure = np.array([o.se_mesure ** 2 for o in obs])
    r = z - lg * theta_g

    num = float(np.sum(np.maximum(r ** 2 - psi_mesure, 0.0)))
    den = float(np.sum(np.maximum(z ** 2 - psi_mesure, 0.0)))
    if den <= 0.0:
        return {
            "ia": None,
            "denominateur_nul": True,
            "motif": ("le profil ne s'ecarte pas de la moyenne de reference au-dela "
                      "du bruit de mesure : l'IA n'est pas defini"),
            "numerateur": num, "denominateur": den,
            "psi_mesure_tous_nuls": bool(np.all(psi_mesure == 0.0)),
        }
    ia = 1.0 - num / den
    return {
        "ia": float(min(max(ia, 0.0), 1.0)),
        "ia_brut": float(ia),
        "denominateur_nul": False,
        "numerateur": num, "denominateur": den,
        "psi_mesure_tous_nuls": bool(np.all(psi_mesure == 0.0)),
    }


def palier(ia: float | None, seuil_haut: float, seuil_bas: float) -> str:
    """§5.4 — trois paliers d'affichage. Le total n'est JAMAIS supprime."""
    if ia is None:
        return PALIER_RETROGRADE
    if ia >= seuil_haut:
        return PALIER_NORMAL
    if ia >= seuil_bas:
        return PALIER_SECOND_PLAN
    return PALIER_RETROGRADE


def mention_palier(p: str) -> str:
    return {
        PALIER_NORMAL: "",
        PALIER_SECOND_PLAN: "predictivement utilisable, descriptivement partiel",
        PALIER_RETROGRADE: ("total retrograde : le vecteur des sous-scores le precede "
                            "et doit etre lu en premier"),
    }[p]
