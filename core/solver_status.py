"""Explicit status objects for engineering solver execution."""

from dataclasses import dataclass
from enum import Enum


class SolverStatus(str, Enum):
    CONVERGED = "CONVERGED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    SINGULAR_SYSTEM = "SINGULAR_SYSTEM"
    INVALID_INPUT = "INVALID_INPUT"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SolverDiagnostics:
    status: SolverStatus
    iterations: int
    residual_norm: float
    message: str = ""
