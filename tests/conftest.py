"""Fixtures communes aux tests d'acceptation CRIB-1."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from scoring.simulation import plan_par_defaut  # noqa: E402

# Graines fixes : R2 exige que la meme entree donne la meme sortie.
GRAINE_T1 = 20240117
GRAINE_T2 = 771
GRAINE_T5 = 4242
GRAINE_T6 = 99


@pytest.fixture(scope="session")
def plan():
    return plan_par_defaut()


@pytest.fixture
def rng_t1():
    return np.random.default_rng(GRAINE_T1)


@pytest.fixture(scope="session")
def racine():
    return RACINE
