# Core Rebuild — Stage 3: Line Curves

## Can certificate PDFs be used?

Yes. A manufacturer line certificate is much more valuable than a generic
material-only assumption. Public OCIMF MEG4 certificate forms include Line
Design Break Force (LDBF), material type and grade, line designation, and
Average Immediate Strain at 10%, 20%, 30%, 40% and 50% of LDBF. These fields
can provide discrete load/strain points when the actual supplied certificate
contains the values.

## What the software will do

1. Read the actual line certificate.
2. Store LDBF and certificate identity as provenance.
3. Store the supplied strain points as measured/design data.
4. Interpolate only within the supplied range.
5. Refuse unsupported extrapolation.
6. Calculate secant stiffness from the certificate-derived curve.
7. Keep generic material curves as explicitly non-certified fallbacks.

## What the software will NOT do

It will not claim that a universal polyester, nylon, HMPE or wire-rope curve is
MEG4 compliant merely because the material name matches. A material name alone
does not identify the actual line construction, grade, product, diameter,
jacket, manufacturing process or certificate data.

## Current certificate fields of interest

- Ship Design MBL
- LDBF
- diameter
- length
- material type and grade
- manufacturer part code / unique line identifier
- line design designation
- line construction
- LLD / LBLD
- Average Immediate Strain at 10/20/30/40/50% LDBF
- relevant base design and product supply test report references

## Important limitation

The public certificate form demonstrates what performance data are documented,
but it does not itself provide a complete continuous load-extension curve.
If the certificate contains the five Average Immediate Strain values, the
software can construct a bounded piecewise-linear engineering representation
through those supplied points. This remains certificate-derived data; the
future full MEG4 cross-check must confirm that this representation is the
appropriate method for the intended calculation.

## Generic fallback

A generic material curve exists only for software compatibility/testing. It is
marked `certified=False` and `GENERIC_ENGINEERING_ASSUMPTION` and must not be
used to make a certification or MEG4-compliance claim.
