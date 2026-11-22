# 09 — Final technical assessment

> Audit 2026-11-22, READ-ONLY. Based on code reading + read-only SQL by 4 workers; headline numbers re-checked by me. Authenticated UI/API behaviour: INSUFFICIENT EVIDENCE.

**Overall grade: C (needs improvement).** The architecture is sound (clean layers, consistent scoping, single asset spine), but several data pipelines are stale or never started, and key tables are empty. No Critical issue proven; 11 High reported (with overlap, about 6 distinct problems).

## The 14 questions

| # | Question | Grade | Short answer |
|---|---|---|---|
| 1 | Architecture | B | Layers respected; large files (3001-line page), many duplicated rules (online threshold, type sets, scope helper). |
| 2 | GPS Wialon ↔ GTK | B- | Works by code; 3 position rules differ (SOS-10); recompute per request (PERF-1). Live not tested. |
| 3 | Map | B- | Reads same verdict as GPS; polls in hidden tabs; GTK carriage coordinates are not real (SOS-06). |
| 4 | GTK data | C | Sync running now, but `is_open` never closes (116/116 open), ~38 h gap, HTML scraping risk (MOD-15). |
| 5 | Wialon data | B- | ~2-min pull; gaps when PC is off (INT-2); 50 % of readings unlinked (INT-9); no retention (PERF-3). |
| 6 | Wagons by sostav | C | Counts differ by 1 vs map (SOS-04); duplicate numbers; identity typos (SOS-05). |
| 7 | Scales | D | Not delivering since 2026-11-20; 96.6 % unmatched to GTK (MOD-02, INT-6). |
| 8 | TO and repairs | D | Engine exists, but 0 plans, 0 baselines, 0 work orders, 0 employees (MOD-03, INT-8). |
| 9 | Asset directory | C+ | 1075 assets; two identity stores drift; non-unique inv numbers; 153 assets outside matching (MOD-04/06). |
| 10 | PROBEG | C- | Wagon engine off and ledger frozen since 2026-11-16; three mileage figures disagree. |
| 11 | SOSTAV | C | Membership tracking OK; train lifecycle broken (SOS-01); train number reused (SOS-02). |
| 12 | Cross-module integration | C | Shared spine good; feeds depend on host uptime; no auto-refresh on most pages (MOD-13). |
| 13 | Security | B- | Master scoping solid in code; HTTP login open (SEC-1); plain dumps in OneDrive folder (SEC-4). |
| 14 | Testing / maintainability | C | No CI (DEBT-1); schema drift test partial; settings not forwarded by compose (DEBT-3). |

## Top 10 problems (see 07)
1. Wagon mileage engine off / ledger frozen since 2026-11-16 (PRB, MOD-01, INT-1).
2. `gtk_trains.is_open` never set to false: 116/116 open (SOS-01).
3. Scales collector silent since 2026-11-20 and 96.6 % unmatched (MOD-02, INT-6).
4. Maintenance has no baselines/plans/orders (MOD-03, INT-8).
5. Feeds (Wialon/GTK/scales) have gaps whenever the PC is down (INT-2, SOS-03).
6. Mileage numbers disagree between views (36,084 vs 748,196 km).
7. Identity drift: `fixed_assets.gtk_id/wialon_id` vs `asset_source_links`; manual-link typos (MOD-04/07, SOS-05).
8. Plain HTTP login stays open (SEC-1).
9. ~3.4 GB plain DB dumps in a OneDrive folder, off-host copy unknown (SEC-4).
10. No retention on raw feed tables, GPS recompute per request (PERF-3, PERF-1).

## NOT verified
Browser/API behaviour of all 8 pages; `.env` flag values (never opened); causes of feed gaps (likely host downtime, unproven); backup encryption/off-host; per-endpoint master scoping for maintenance/nomenclature/ML; test suites; GPS recompute latency; why maintenance data (87 assets/775 obligations in an earlier note) is now 0.
