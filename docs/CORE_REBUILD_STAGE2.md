# Core Rebuild — Stage 2: Environmental Loads

## Architecture
Environmental calculations are now separated into:
- coefficient providers;
- physical load equations;
- projected area definitions;
- load combination;
- legacy unit adapters.

## Safety rule
No coefficient provider in the new architecture may claim MEG4 validation
without a source reference and verification record.

## Units
Internal environmental calculations use:
- force: N
- moment: N·m
- speed: m/s
- area: m²
- density: kg/m³

Legacy tonne-force outputs are generated only through an explicit adapter.

## Benefits
- source-sensitive coefficient tables can be replaced independently;
- projected areas are explicit inputs;
- current calculations no longer silently reconstruct areas from LOA × draft;
- wind/current equations can be benchmarked independently;
- unit conversion is isolated.

## Pending source validation
The temporary AssumptionCoefficientProvider is not a certification model.
It must be replaced by a documented vessel/model-specific provider during
the future MEG4/source cross-check.
