# v53 Phase 12 plan: cutover checklist automation

Date: 2026-03-27
Stage target: 59
Status: Completed

## Goal

Turn the rehearsal evidence bundle into an operator-facing go/no-go checklist so the first live staging release can end with an explicit cutover review packet instead of raw logs only.

## Scope

### Checklist generation

- add a reusable cutover checklist generator that reads the release evidence report
- produce:
  - markdown checklist for operator review
  - JSON checklist for machine-readable archival
- classify each gate as:
  - done
  - manual-review
  - blocked

### Workflow integration

- extend staging and production deploy workflows to generate `cutover-checklist.md` and `cutover-checklist.json`
- keep checklist generation in `always()` steps so failed rehearsals still emit a review packet

### Release contract documentation

- document the GitHub environment secret contract in `.env.example`
- extend release asset validation so the secret-contract reference and checklist wiring cannot silently drift

### Regression and system verification

- add unit coverage for ready-for-review and no-go checklist outcomes
- extend `verify_system.sh` with checklist CLI validation and workflow wiring checks

## Exit criteria

- every rehearsal artifact bundle includes both a release report and a cutover checklist
- the repo contains a durable reference for required staging and production GitHub environment secrets
- full quality gates remain green after checklist automation is added
