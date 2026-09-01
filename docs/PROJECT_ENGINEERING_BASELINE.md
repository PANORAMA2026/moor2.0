# OpenMooring Engineering Baseline

## 1. Purpose
OpenMooring is an engineering decision-support application for the assessment and monitoring of ship mooring arrangements.

## 2. Intended Use
The software is intended to assist qualified maritime personnel and engineers by:
- managing mooring line and certificate data;
- modelling berth and mooring geometry;
- estimating environmental loads;
- calculating line geometry, stiffness and tension;
- presenting engineering results and operational trends.

The software does not replace professional engineering judgement, approved ship documentation, class rules, manufacturer limitations, or onboard procedures.

## 3. Initial Scope
Current target: Engineering Decision Support System.

The software shall not:
- autonomously control ship equipment;
- issue safety-critical commands;
- silently convert failed calculations into valid engineering results.

## 4. Engineering Safety Principles
1. No silent calculation failures.
2. Invalid input shall be detected and reported.
3. Units and coordinate conventions shall be explicit.
4. Engineering calculations shall be reproducible from recorded inputs.
5. Validated logic shall be separated from the user interface.
6. Every safety-relevant requirement shall be traceable to tests.

## 5. Software Boundaries
### Inputs
- Ship geometry and characteristics
- Mooring line properties and certificates
- Berth and bollard geometry
- Environmental conditions
- User-selected operational configuration

### Outputs
- Environmental forces and moments
- Mooring line geometry
- Line tensions and utilization
- Warnings and calculation status

## 6. Validation Philosophy
A result is valid only when:
- required inputs are present;
- input ranges pass validation;
- the calculation converges where convergence is required;
- no internal calculation error occurred.

Otherwise the result shall be explicitly marked INVALID, FAILED, or OUTSIDE VALIDATED RANGE.

## 7. Change Control
Engineering logic changes require:
- documented reason;
- code review;
- associated tests;
- regression testing where applicable;
- traceability update.

## 8. Versioning
Releases shall use semantic versioning where practical: MAJOR.MINOR.PATCH.

## 9. Current Status
This document establishes the engineering baseline. It does not claim approval, certification, or compliance with any classification society rule.
