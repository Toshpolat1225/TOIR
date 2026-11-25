# Locomotive folder review (2026-11-24)

Source: docs/templates (locomotive folder), 6 files. Cleaned data: docs/imports/norms/loco and docs/imports/loco_*.

- Norms KR and TR-3 for TEM2/TEM18/TEM18DM: 1763 and 1761 lines, 85 assembly groups.
- TR-3 2TE116: 295 lines, quantity is the 2-section column, per-section value in the note.
- Monthly norms TR-1, TO-3, TO-2 (TEM2): 262, 149, 108 lines, basis per month per unit.
- Last repairs: 35 locomotives, date is the maximum of TR-1, TR-3, KR-2.
- Signature rows (positions and person names) are dropped; the importer refuses non-numeric quantities.

Open: lubricants file (sheets 2025 and 2027 disagree), 1C stock and price report, 3 serial mismatches (2689, 2699, 7441).
