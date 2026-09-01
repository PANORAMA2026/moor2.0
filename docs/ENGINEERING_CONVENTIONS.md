# OpenMooring Engineering Conventions

## Status
This document defines conventions that must be confirmed against the validated engineering model before final release.

## Units
Canonical units shall be documented at every engineering module boundary.

Recommended internal convention:
- Length: m
- Force: kN
- Moment: kN·m
- Mass: t only for reporting where explicitly labelled
- Wind speed: m/s internally
- Current speed: m/s internally
- Angles: degrees at user interface boundaries, radians only inside trigonometric calculations

## Coordinates
A single right-handed vessel/berth coordinate system shall be defined and used consistently.

## Angles
The application shall document:
- zero reference direction;
- positive rotation;
- direction of environmental vectors;
- whether values indicate direction-from or direction-to.

## Error Handling
Engineering calculation errors shall never be silently ignored.
