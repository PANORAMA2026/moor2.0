"""Controlled exceptions used by OpenMooring engineering workflows."""


class OpenMooringError(Exception):
    """Base exception for controlled application errors."""


class InputValidationError(OpenMooringError):
    """Raised when required engineering input is invalid."""


class CalculationError(OpenMooringError):
    """Raised when an engineering calculation cannot produce a valid result."""


class ConvergenceError(CalculationError):
    """Raised when an iterative engineering solver does not converge."""
