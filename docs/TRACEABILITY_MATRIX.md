# OpenMooring Traceability Matrix

| Requirement ID | Description | Implementation | Test | Status |
|---|---|---|---|---|
| REQ-ENG-001 | Environmental loads | Pending audit | Pending | OPEN |
| REQ-ENG-002 | Mooring geometry | Pending audit | Pending | OPEN |
| REQ-ENG-003 | Line mechanics | Pending audit | Pending | OPEN |
| REQ-ENG-004 | Calculation status | Pending refactor | Pending | OPEN |
| REQ-DATA-001 | Canonical engineering entities | domain/models.py | test_domain_models.py | IMPLEMENTED |
| REQ-DATA-002 | Unit consistency | Engineering conventions baseline | Pending audit | OPEN |
| REQ-VAL-001 | Input validation | validation/input_validation.py | test_input_validation.py | IMPLEMENTED |
| REQ-TEST-001 | Unit tests | pytest | tests/unit | STARTED |
| REQ-TEST-002 | Regression tests | tests/regression | Pending | OPEN |
| REQ-ARCH-001 | UI separation | domain + validation layers | Unit tests | STARTED |
| REQ-ARCH-002 | Error transparency | Controlled exception hierarchy | Pending core migration | PARTIAL |
