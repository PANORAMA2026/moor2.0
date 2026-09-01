# Core Rebuild — Stage 1

## Implemented safety changes

### 1. Strength terminology
A new explicit `StrengthLimits` domain model separates:
- Ship Design MBL
- Line LDBF
- Working Load Limit
- Brake Rendering

Legacy `mbl_tons` remains temporarily for compatibility.

### 2. Tail strength correctness
Composite stiffness now requires and uses the actual `tail_mbl_tons` whenever a tail length is present.

### 3. Geometry integrity
Missing engineering coordinates are no longer silently converted to zero.

### 4. Solver diagnostics
The solver now reports:
- CONVERGED
- MAX_ITERATIONS
- SINGULAR_SYSTEM
- INVALID_INPUT
- FAILED

Non-converged results are invalidated rather than presented as valid tensions.

### 5. Residual verification
Convergence now requires both:
- tension update convergence;
- equilibrium residual below configured tolerance.

## Important limitation
The current stiffness fallback remains a compatibility model. It is not a substitute for manufacturer-certified load-extension data.

## Next stage
- SI-native environmental force API;
- separation of coefficient providers from force equations;
- benchmark cases;
- operational limits derived from explicit policy rather than hard-coded thresholds.
