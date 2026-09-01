# OpenMooring Core Engineering Audit — Phase A

## Scope
Audit of the current engineering core implementation:
- `core/hydrodynamic_forces.py`
- `core/line_mechanics.py`

Status: PRELIMINARY. This is not a declaration of MEG4 compliance.

## Critical findings

### CEA-001 — Environmental coefficients are not traceable
**Severity: CRITICAL**

Current wind and current coefficients are hard-coded as simple trigonometric curves. No source table, vessel category, interpolation method, or exact MEG4 section is recorded.

Action: replace with source-traceable coefficient providers after validation against authorised MEG4 material and applicable vessel-specific methodology.

### CEA-002 — Current force implementation ignores supplied lateral current area
**Severity: HIGH**

`calculate_environmental_forces(... alc ...)` receives `alc`, but `calculate_current_forces` recalculates submerged areas from LOA × draft and beam × draft.

Action: define canonical projected areas and calculation provenance.

### CEA-003 — Moment coefficients and moment arms are not traceable
**Severity: CRITICAL**

Yaw moments use simplified coefficients and LOA as lever arm without demonstrated equivalence to the applicable source methodology.

Action: isolate moment calculation and validate against benchmark examples.

### CEA-004 — Units are mixed
**Severity: HIGH**

The core internally calculates in tonnes-force and tonne-metres using division by standard gravity while inputs use SI dimensions and densities.

Action: use SI internally (N/kN/kN·m) and convert only at presentation boundaries.

### CEA-005 — Line elongation curves are unverified
**Severity: CRITICAL**

Material constants A/B are hard-coded without manufacturer curve provenance. The comment claims MEG4 conformity but no exact source exists.

Action: replace generic curves with certificate/manufacturer load-extension data or explicitly labelled engineering assumptions.

### CEA-006 — Tail MBL bug
**Severity: CRITICAL**

The solver passes main-line MBL as the tail MBL when calculating composite stiffness.

Action: use `tail_mbl_tons` explicitly and reject invalid tail data.

### CEA-007 — Pretension is presented as a fixed MEG4 value
**Severity: CRITICAL**

A default 10% MBL is hard-coded and described as fixed MEG4 pretension. This must not be treated as universally compliant without an applicable operational/design basis.

Action: make pretension explicit input and remove compliance claim.

### CEA-008 — Solver can fail silently
**Severity: CRITICAL**

A singular global stiffness matrix causes `break`, after which the function can return tensions without a failure status.

Action: raise controlled `ConvergenceError` or return an explicit failed result.

### CEA-009 — No equilibrium residual verification
**Severity: CRITICAL**

Convergence checks only tension change, not force/moment residual.

Action: validate equilibrium residual and displacement convergence.

### CEA-010 — Geometry zero-fills missing coordinates
**Severity: HIGH**

Missing engineering coordinates are converted to 0.0, potentially producing plausible but incorrect geometry.

Action: fail validation for required coordinates.

### CEA-011 — Operational utilization uses generic MBL
**Severity: HIGH**

Utilization is calculated against `mbl_tons`, while MEG4 terminology distinguishes Ship Design MBL, LDBF and WLL.

Action: redesign strength/limit data model.

### CEA-012 — Operability envelope uses hard-coded 55%
**Severity: CRITICAL**

The 55% threshold is undocumented and is not linked to a validated requirement or vessel procedure.

Action: move operational limits to explicit validated policy/configuration.

## Immediate conclusion
The current core is a prototype engineering model and must **not** be described as MEG4 compliant at this stage.

The next implementation phase will first harden failure handling, units, geometry validation and strength terminology before replacing source-sensitive environmental coefficients and line load-extension models.
