# Certificate PDF Extraction — Engineering Design

The importer is intentionally conservative. It extracts candidate values from PDF text, preserves source text and confidence, and validates before data can enter the engineering model.

## Supported first-pass fields
- Ship Design MBL
- LDBF
- Diameter
- Length
- Line Linear Density
- Average Immediate Strain at 10/20/30/40/50% LDBF when the PDF text exposes the table clearly

## Important limitation
PDF extraction is not the same as engineering verification. A value is not treated as certified merely because OCR/text extraction found it. Ambiguous tables, scanned pages, unit ambiguity, duplicated values, or unusual manufacturer layouts must be routed to manual review.

## Why this matters
The official OCIMF MEG4 line certificate identifies Ship Design MBL, diameter, length, material/grade, manufacturer identifier, line construction, LDBF, LLD, LBLD and Average Immediate Strain at 10–50% LDBF among its fields. The official certificate also states that certification is performed by the manufacturer and may be verified by an independent inspector; it is not approval by OCIMF.

## Future ingestion pipeline
PDF → text/table extraction → field candidates → unit normalization → validation → human confirmation for ambiguous fields → immutable certificate record → engineering model.

Scanned/image-only PDFs will require OCR and page-region/table detection. The parser must never silently guess values from a failed OCR result.
