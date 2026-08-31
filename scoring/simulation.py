"""SIMULATION UNIQUEMENT — ce module ne contient AUCUNE norme (R1).

Les parametres definis ici servent exclusivement a tester la machinerie
d'estimation (tests d'acceptation T1, T2, T3, T5, T6). Ils ne touchent jamais
le score du sujet reel : le pipeline de scoring ne les importe pas.

Le lint de provenance (T4) exclut ce module par declaration explicite dans
config/lint_provenance.json, avec justification.

Tous les tirages passent par un `numpy.random.Generator` explicitement graine
(R2 — determinisme).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from scoring.battery import Domaine, ModeItems
from scoring.model import Observation

MARQUEUR = "SIMULATION_SEULEMENT_PAS_UNE_NORME"


@dataclass(frozen=True)
class PlanSimulation:
    """Plan d'une batterie virtuelle. Valeurs plausibles, jamais normatives."""
    codes: tuple[str, ...]
    domaines: tuple[Domaine, ...]
    lambda_g: np.ndarray
    lambda_s: np.ndarray
    n_items: tuple[int | None, ...]   # None = sub-test modelise directement en z
    modes: tuple[ModeItems, ...]

    def __post_init__(self) -> None:
        n = len(self.codes)
        for nom, seq in (("domaines", self.domaines), ("lambda_g", self.lambda_g),
                         ("lambda_s", self.lambda_s), ("n_items", self.n_items),
                         ("modes", self.modes)):
            if len(seq) != n:
                raise ValueError(f"longueur de {nom} incoherente ({len(seq)} vs {n})")
        com = self.lambda_g ** 2 + self.lambda_s ** 2
        if np.any(com >= 1.0):
            raise ValueError("communalite >= 1 : psi structurel non positif")

    @property
    def psi_structurel(self) -> np.ndarray:
        return 1.0 - self.lambda_g ** 2 - self.lambda_s ** 2


def plan_par_defaut() -> PlanSimulation:
    """Batterie virtuelle a 7 sub-tests, calquee sur la STRUCTURE du noyau.

    Les saturations sont des valeurs de travail plausibles, PAS des estimations
    empiriques. Elles ne servent qu'a verifier que l'estimateur retrouve le
    theta qu'on lui a donne.
    """
    return PlanSimulation(
        codes=("C1", "C2", "C3", "C4", "C5", "C6", "C7"),
        domaines=(Domaine.INDUCTION, Domaine.SPATIAL, Domaine.MEMOIRE_TRAVAIL,
                  Domaine.MEMOIRE_TRAVAIL, Domaine.MEMOIRE_TRAVAIL,
                  Domaine.INDUCTION, Domaine.SPATIAL),
        # Saturations de TRAIT VRAI (avant erreur de mesure d'item), choisies dans
        # la plage d'une batterie de raisonnement bien construite. Ce sont des
        # parametres de plan de simulation, PAS des estimations empiriques : ils
        # fixent le niveau d'information de la batterie virtuelle sur lequel T1
        # se prononce.
        lambda_g=np.array([0.80, 0.72, 0.68, 0.70, 0.74, 0.80, 0.68]),
        lambda_s=np.array([0.30, 0.40, 0.44, 0.42, 0.38, 0.30, 0.42]),
        n_items=(11, 24, None, None, None, 17, 40),
        modes=(ModeItems.CLONES,) * 7,
    )


def parametres_irt_simules(n_items: int, rng: np.random.Generator
                           ) -> tuple[np.ndarray, np.ndarray]:
    """Parametres 2PL simules (discrimination, difficulte). Jamais des normes."""
    a = rng.uniform(0.9, 2.1, size=n_items)
    b = np.linspace(-1.8, 1.8, n_items) + rng.normal(0.0, 0.25, size=n_items)
    return a, b


def _p2pl(theta: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """P(correct) 2PL. theta (n,1) x items (m,) -> (n,m)."""
    return 1.0 / (1.0 + np.exp(-a[None, :] * (theta[:, None] - b[None, :])))


def eap_2pl(reponses: np.ndarray, a: np.ndarray, b: np.ndarray,
            grille: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """EAP et erreur-type a posteriori sous prior N(0,1). Vectorise sur les sujets."""
    if grille is None:
        grille = np.arange(-4.0, 4.0 + 1e-9, 0.02)
    prior = np.exp(-0.5 * grille ** 2)
    prior /= prior.sum()
    p = _p2pl(grille, a, b)                     # (G, m)
    p = np.clip(p, 1e-12, 1 - 1e-12)
    logp, log1p = np.log(p), np.log(1.0 - p)
    # (n, G) = reponses (n,m) @ logp.T (m,G)
    ll = reponses @ logp.T + (1.0 - reponses) @ log1p.T
    ll -= ll.max(axis=1, keepdims=True)
    post = np.exp(ll) * prior[None, :]
    post /= post.sum(axis=1, keepdims=True)
    moy = post @ grille
    var = post @ (grille ** 2) - moy ** 2
    return moy, np.sqrt(np.maximum(var, 1e-12))


def simuler_population(n_sujets: int, plan: PlanSimulation, rng: np.random.Generator
                       ) -> dict[str, np.ndarray]:
    """Tire theta_g, theta_s, les traits de sub-test et les reponses items.

    Renvoie z (n, J) sur l'echelle du trait latent de sub-test, et psi (J,)
    coherent avec la facon dont z a ete produit.
    """
    J = len(plan.codes)
    if any(m is not None for m in plan.n_items) and n_sujets < 50:
        raise ValueError(
            f"n_sujets = {n_sujets} : la fidelite de l'EAP (rho) est estimee sur la "
            "variance de l'echantillon simule et n'est pas definie pour un echantillon "
            "aussi petit. Simuler une population, puis en extraire le sujet voulu.")
    theta_g = rng.standard_normal(n_sujets)

    doms = sorted({d.value for d in plan.domaines})
    theta_s_par_dom = {d: rng.standard_normal(n_sujets) for d in doms}
    theta_s = np.column_stack([theta_s_par_dom[d.value] for d in plan.domaines])

    eps = rng.standard_normal((n_sujets, J)) * np.sqrt(plan.psi_structurel)[None, :]
    eta = plan.lambda_g[None, :] * theta_g[:, None] + plan.lambda_s[None, :] * theta_s + eps

    z = np.empty_like(eta)
    psi = np.empty(J)
    se_mesure = np.zeros(J)
    params_irt: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for j, (code, m) in enumerate(zip(plan.codes, plan.n_items)):
        if m is None:
            # Sub-test modelise directement en z : pas d'erreur item supplementaire.
            z[:, j] = eta[:, j]
            psi[j] = plan.psi_structurel[j]
            continue
        a, b = parametres_irt_simules(m, rng)
        params_irt[code] = (a, b)
        p = _p2pl(eta[:, j], a, b)
        reponses = (rng.random((n_sujets, m)) < p).astype(float)
        eap, _ = eap_2pl(reponses, a, b)
        # L'EAP retrecit vers 0 : on le remet a l'echelle du trait par sa fidelite.
        rho = float(np.clip(np.var(eap) / max(np.var(eta[:, j]), 1e-12), 1e-6, 0.999999))
        z[:, j] = eap / rho
        var_mesure = (1.0 - rho) / rho
        se_mesure[j] = np.sqrt(var_mesure)
        psi[j] = plan.psi_structurel[j] + var_mesure

    return {"theta_g": theta_g, "theta_s": theta_s, "eta": eta, "z": z,
            "psi": psi, "se_mesure": se_mesure, "params_irt": params_irt,
            "_marqueur": np.array([MARQUEUR], dtype=object)}


def observations_depuis(plan: PlanSimulation, z_ligne: np.ndarray, psi: np.ndarray,
                        se_mesure: np.ndarray | None = None) -> list[Observation]:
    """Construit les Observation d'UN sujet simule."""
    if se_mesure is None:
        se_mesure = np.zeros(len(plan.codes))
    return [
        Observation(
            code=code, z=float(z_ligne[j]),
            lambda_g=float(plan.lambda_g[j]), lambda_s=float(plan.lambda_s[j]),
            psi=float(psi[j]), domaine=plan.domaines[j], mode_items=plan.modes[j],
            se_mesure=float(se_mesure[j]),
            provenance_ids=(f"{MARQUEUR}:{code}",),
        )
        for j, code in enumerate(plan.codes)
    ]


def profil_constant(plan: PlanSimulation, valeur: float, psi: np.ndarray | None = None
                    ) -> list[Observation]:
    """Profil parfaitement plat (T3)."""
    psi = plan.psi_structurel if psi is None else psi
    return observations_depuis(plan, np.full(len(plan.codes), valeur), psi)


def profil_disperse(plan: PlanSimulation, moyenne: float, amplitude: float,
                    psi: np.ndarray | None = None) -> list[Observation]:
    """Profil de MEME moyenne, disperse de +/- `amplitude` (T2).

    Le vecteur de signes est construit a somme exactement nulle : les sub-tests
    sont apparies +1 / -1 et le sub-test restant, s'il y en a un, recoit 0.
    La moyenne du profil est donc identique a celle du profil plat, au bit pres,
    ce qui est la condition meme du test T2.
    """
    psi = plan.psi_structurel if psi is None else psi
    J = len(plan.codes)
    signes = np.zeros(J)
    for k in range(J // 2):
        signes[2 * k] = 1.0
        signes[2 * k + 1] = -1.0
    # J impair -> le dernier reste a 0, la somme est nulle par construction.
    assert abs(signes.sum()) < 1e-12
    return observations_depuis(plan, moyenne + amplitude * signes, psi)
