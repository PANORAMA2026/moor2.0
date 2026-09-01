# Certificate Review Workflow

The certificate import path is intentionally fail-closed.

```text
PDF
 -> native extraction
 -> fallback extraction
 -> page-level field candidates
 -> validation
 -> ambiguity check
 -> human review
 -> accepted field map
 -> engineering model
```

## Acceptance rules

A certificate is not accepted when:

- required fields are missing;
- conflicting values are detected;
- the PDF has no machine-readable text and OCR/manual review is required;
- a required numeric value is non-positive.

The review object does not modify ship, line, or database data. Only an
explicitly accepted review can produce an engineering field map.

## Traceability

Every extracted field retains source text, page (when PDF page parsing is
available), unit as detected, and confidence. These are review metadata, not
proof of certification.

## OCR policy

Scanned certificates must be detected and routed to an OCR-capable step. The
system must never infer engineering values from an unreadable PDF.

## Future integration

When real vessel certificates are available, their layouts will be added as
regression fixtures after checking confidentiality/distribution rights. The
parser will then be extended using observed layouts rather than assuming a
single universal PDF template.
