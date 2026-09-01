# Core Rebuild — Stage 4: Certificate PDF Extraction

## Goal
Convert real mooring-line/tail certificate PDFs into reviewable engineering data without silently inventing values.

## Extraction layers
1. PyMuPDF native text extraction.
2. pypdf fallback.
3. Explicit detection of image-only/scanned PDFs.
4. Page-level provenance for extracted fields.
5. Engineering validation before data can be accepted.

## Safety rules
- Extraction confidence is not certification.
- Conflicting values are flagged as ambiguous.
- Missing required values block acceptance.
- OCR is an explicit future integration point; scanned PDFs are not silently guessed.
- Generic material curves remain preliminary assumptions only.

## Supported concepts
Main-line certificates can expose LDBF, Ship Design MBL, diameter, length, linear density and immediate-strain values.
Tail certificates can expose TDBF and tail-specific values.

## Test workflow
Upload actual certificates to the development/test workflow, inspect extracted fields and source pages, correct layout-specific patterns, then add the certificate as a regression fixture (with sensitive information removed if necessary).

## Future UI
The Streamlit UI should show:
- detected certificate type;
- extracted value;
- unit;
- page/source text;
- confidence;
- validation status;
- Accept / Reject / Edit controls.

No accepted certificate should overwrite existing ship data automatically.
