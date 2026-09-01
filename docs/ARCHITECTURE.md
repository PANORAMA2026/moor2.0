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

## Layer Rules

### Views
Streamlit presentation and user interaction only.

### Services
Orchestrate workflows without embedding engineering mathematics.

### Domain
Typed representations of ship, line, berth, environment and simulation data.

### Core
Deterministic engineering calculations. No Streamlit imports.

### Validation
Input and engineering-range validation.

### Data
Persistence and external integrations.

## Refactoring Strategy
The existing application will be migrated incrementally. Existing modules remain operational until replacement modules are validated.
