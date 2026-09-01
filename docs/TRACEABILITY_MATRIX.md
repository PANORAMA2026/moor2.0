# OpenMooring Traceability Matrix

| ID | Requirement / Finding | Implementation | Verification | Status |
|---|---|---|---|---|
| REQ-ENG-001 | Environmental loads | Legacy core | Core audit | REQUIRES REWORK |
| REQ-ENG-002 | Mooring geometry | Legacy core | Core audit | REQUIRES HARDENING |
| REQ-ENG-003 | Line mechanics | Legacy core | Core audit | REQUIRES REWORK |
| REQ-ENG-004 | Calculation status | validation exceptions | Pending integration | PARTIAL |
| REQ-DATA-001 | Canonical engineering entities | domain/models.py | Unit tests | IMPLEMENTED |
| REQ-VAL-001 | Input validation | validation/input_validation.py | Unit tests | IMPLEMENTED |
| CEA-001 | Traceable environmental coefficients | Pending | MEG4/source validation | OPEN |
| CEA-002 | Canonical current projected area | Pending | Unit test | OPEN |
| CEA-004 | SI internal units | Pending | Unit tests | OPEN |
| CEA-005 | Traceable load-extension curves | Pending | Certificate benchmark | OPEN |
| CEA-006 | Tail MBL correctness | Pending | Regression test | OPEN |
| CEA-008 | No silent solver failure | Pending | Failure-mode tests | OPEN |
| CEA-009 | Equilibrium residual verification | Pending | Benchmark tests | OPEN |
| CEA-010 | No zero-filled geometry | Pending | Validation tests | OPEN |
| CEA-011 | Strength terminology | Pending | Domain tests | OPEN |
| CEA-012 | Validated operational limits | Pending | Configuration review | OPEN |
