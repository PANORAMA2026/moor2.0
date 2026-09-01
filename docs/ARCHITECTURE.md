# OpenMooring Architecture

## Target Architecture

```text
UI / Views
    |
Application Services
    |
Validation + Domain Models
    |
Engineering Core
    |
Repositories / Database / External Services
```

## Core modules

```text
core/
├── environmental_models.py   # SI physical equations
├── environmental_adapters.py # legacy compatibility
├── line_mechanics.py         # geometry and equilibrium
├── solver_status.py          # explicit solver diagnostics
└── units.py                  # canonical conversions
```

## Environmental design
Coefficient sources are deliberately separated from physical equations.
A coefficient provider must carry source provenance before being described as
validated against an external engineering standard.

## Migration strategy
Legacy modules remain operational until adapters and regression tests verify
equivalent or intentionally corrected behaviour.
