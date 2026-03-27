# v53 Phase 11 plan: rehearsal evidence automation

Date: 2026-03-27
Stage target: 58
Status: Completed

## Goal

Make the first live staging rehearsal auditable by ensuring the deploy workflows always capture rollout evidence and generate a cutover-ready summary artifact.

## Scope

### Evidence report generation

- add a reusable release evidence report generator that produces:
  - markdown summary
  - JSON machine-readable evidence
- include step outcomes, image refs, artifact inventory, missing evidence detection, and release recommendation logic

### Workflow artifact capture

- capture rollout logs, kubectl inventory, pod snapshots, and event logs in staging and production deploy workflows
- generate the evidence report in an `always()` step so failure cases still produce artifacts
- upload the evidence bundle with `actions/upload-artifact@v4`

### Regression and validation

- add unit tests for report generation and recommendation logic
- extend release asset validation to require report generation and artifact upload wiring
- extend `verify_system.sh` with release report CLI validation

## Exit criteria

- deploy workflows produce a reusable evidence bundle for staging or production rehearsal
- evidence generation works on both successful and failing step combinations
- local quality gates remain green after the evidence automation is added
