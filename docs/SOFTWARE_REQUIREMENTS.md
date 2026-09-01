# OpenMooring Software Requirements

## Requirement Format
Each requirement shall have a unique identifier and be traceable to implementation and verification.

## Core Requirements

### REQ-ENG-001 Environmental Loads
The system shall calculate environmental loads using documented input parameters and conventions.

### REQ-ENG-002 Mooring Geometry
The system shall calculate line geometry from explicitly defined ship and shore connection coordinates.

### REQ-ENG-003 Line Mechanics
The system shall calculate line stiffness and tension using documented engineering assumptions.

### REQ-ENG-004 Calculation Status
The system shall explicitly report calculation failure and shall not present failed calculations as valid engineering results.

### REQ-DATA-001 Data Consistency
The application shall use canonical field names for core engineering entities.

### REQ-DATA-002 Unit Consistency
Physical units shall be explicit at module boundaries and conversions shall be documented.

### REQ-VAL-001 Input Validation
Engineering inputs shall be validated before execution of safety-relevant calculations.

### REQ-TEST-001 Unit Testing
Engineering core modules shall have automated unit tests for normal and boundary conditions.

### REQ-TEST-002 Regression Testing
Validated benchmark scenarios shall be preserved as regression tests.

### REQ-ARCH-001 UI Separation
The engineering core shall not depend on Streamlit.

### REQ-ARCH-002 Error Transparency
Broad exception handlers shall not silently suppress engineering calculation errors.
