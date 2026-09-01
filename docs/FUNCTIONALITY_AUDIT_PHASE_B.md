# Functionality Audit — Phase B

## Scope
Review of application/UI services after the engineering-core hardening work.

## Findings

### FB-001 — Automatic weather was fabricated
**Severity: CRITICAL**
`core/auto_mooring_engine.py` previously returned a hard-coded 18.5 kt / 45 deg reading while reporting `Live API`.

**Action taken:** removed fabricated weather. The service now returns `DATA_UNAVAILABLE` until a real provider or an explicit operator override is supplied.

### FB-002 — Automatic line tension was fabricated
**Severity: CRITICAL**
The previous automatic logger calculated tension as `mbl_percentage * (1 + wind/50)`. This is not a physical mooring model and must never create engineering exposure records.

**Action taken:** removed the arbitrary tension formula. Automatic logging accepts only already-calculated engineering exposure records explicitly marked `VALID`.

### FB-003 — Streamlit execution is not a background scheduler
**Severity: HIGH**
A function called during a Streamlit render cannot guarantee execution every 30 minutes when the browser/app has no rerun.

**Action:** service documentation now treats the function as a single monitoring cycle. A true scheduler/telemetry source remains a separate integration requirement.

### FB-004 — PDF parser used LLM output as primary extraction fallback
**Severity: HIGH**
The previous PDF facade could send certificate content/images to an LLM and directly return generated JSON as application data.

**Action taken:** deterministic engineering parser is now the primary path; extracted values are marked review-required. AI is not silently trusted as certified data.

### FB-005 — Certificate UI invented elastic modulus and MEG4 default
**Severity: HIGH**
The previous UI estimated E from material and defaulted the standard to MEG4.

**Action taken:** those defaults were removed. Engineering properties must come from certificate/source data or explicit future assumptions.

### FB-006 — Certificate data model was incomplete
**Severity: HIGH**
Legacy storage could not retain the full reviewed engineering record, including strain points and provenance.

**Action taken:** added `database/certificate_repository.py` with a dedicated traceable record containing certificate identity, LDBF/TDBF, strain data, source text, extraction method and review status.

## Remaining priorities
1. Replace legacy environmental path in `app.py` with the new SI architecture without changing verified outputs unexpectedly.
2. Remove demo/mock simulation results from UI.
3. Replace hard-coded operational thresholds with explicit policy configuration.
4. Validate berth/bollard geometry and SWL calculations.
5. Add end-to-end regression tests around a known engineering benchmark.
6. Integrate a real weather provider with timestamp, source, quality and stale-data checks.
7. Cross-check all source-sensitive calculations against authorised MEG4 material supplied by the user.

## Compliance statement
This audit does not declare MEG4, class, IACS or statutory compliance. It records software-hardening actions and identifies source-validation work still required.
