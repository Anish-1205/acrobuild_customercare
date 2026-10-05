# Verification evidence

This directory contains dated artifacts, not current product documentation.
Property catalogues, project names, response text, performance, and pass counts
can change after capture.

## Manual acceptance

`manual/` contains the 2026-10-01, 91-case acceptance package:

- `acceptance-report-2026-10-01.md` — human-readable verdict and environment.
- `acceptance-cases-2026-10-01.csv` — case-by-case results.
- `acceptance-evidence-2026-10-01.json` — captured browser/API evidence.

The report records 90 passes and one case blocked by live data. Keep the CSV and
JSON together because the report links to them.

## Live acceptance snapshots

`live/` contains output from the real-service scripts:

| File | Writer |
| --- | --- |
| `disambiguation.json` | `scripts/live_disambiguation_check.py` |
| `disambiguation-timeout-observed.json` | retained incident evidence; not the final acceptance result |
| `project-discovery.json` | `scripts/live_project_discovery_check.py` |
| `project-home-types.json` | `scripts/live_project_home_type_check.py` |

The scripts overwrite their active result file. Do not hand-edit a transcript to
make an acceptance run pass. Do not commit secrets, headers, `.env` contents, or
customer data in evidence.

Before relying on any file as evidence of current behavior, check its capture
date and rerun the relevant script if the external catalogue or code has changed.
