# Mooring geometry data requirements

The interactive mooring model is intentionally data-driven. Drawing-derived equipment IDs are imported without inventing coordinates.

## Required before engineering geometry can be finalized

### 1. Ship coordinate reference
- Origin/reference point used for the vessel mooring geometry.
- X convention (normally longitudinal), Y convention (transverse), Z convention (vertical).
- Units and sign convention.

### 2. Ship-side component coordinates
For each used winch, fairlead/chock/guide and other line-contact component:
- component ID / drawing piece number;
- X, Y, Z in the agreed ship coordinate system;
- roller/fairlead axis direction where applicable;
- roller/fairlead diameter where applicable.

### 3. Fairlead / roller data
For each roller actually used by a mooring route:
- diameter;
- axis orientation;
- if available, manufacturer minimum rope bend radius or D/d requirement;
- identification of the actual roller in multi-roller fairleads.

### 4. Shore bollard geometry
The existing port database must contain, for the selected berth:
- bollard ID;
- X, Y, Z in a berth coordinate system compatible with the station geometry;
- SWL where available.

If berth coordinates are not available, the line geometry can still be configured, but line length and 3D load geometry remain incomplete.

## Important modelling rule

A drawing pixel coordinate is never treated as a vessel engineering coordinate without calibration. Contact angle is not converted into tension amplification unless a separately justified friction/contact model and required coefficient are available.
