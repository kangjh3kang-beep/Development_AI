# PropAI v53 rebaseline plan

Date: 2026-03-24
Stage: 59
Status: Active v53 roadmap; Phases v53.1 through v53.12 completed and the next execution target is the first live staging release rehearsal with cutover packet review

## Source set

This plan is now based on the actual workspace v53 documents:

- `../PropAI_v53_PartA_마스터인덱스.md`
- `../PropAI_v53_PartB_백엔드코어.md`
- `../PropAI_v53_PartC_ESG_고급서비스.md`
- `.build-journal/implementation-status-gap-analysis-stage-46-2026-03-23.md`
- `.build-journal/current-stage.json`

The previous assumption that no official v53 spec existed was incorrect. This document replaces that assumption with a document-backed delta plan.

## Executive conclusion

The current codebase is strong on broad feature coverage, but it is not yet aligned with the official v53 promise of fully resolved `G158` through `G165`.

The main planning error to avoid is this:

- if the roadmap focuses only on generic release hardening, it will miss the official v53 delta
- if the roadmap focuses only on new v53 features, it will leave release-critical operator gaps unresolved

So the correct v53 plan is a combined strategy:

1. close the official `G158` to `G165` feature gaps first
2. then harden the remaining operator surfaces and release gates

## Official v53 delta from Part A

The official v53 master index defines the new release delta as `G158` through `G165`:

- `G158` real-time construction material price integration
- `G159` basic real-time digital twin linkage
- `G160` automated AI risk grading
- `G161` smart contract generation with e-sign support
- `G162` multilingual support
- `G163` full mobile PWA support
- `G164` automated permit submission integration
- `G165` construction-cost escalation based on PPI and index data

That means the v53 plan must be judged primarily by those eight items, not only by the older `v43` completion track.

## Verified current baseline

The verified implementation baseline entering this plan is still strong:

- backend live APIs exist for underwriting, climate, compliance, leases, ESG, marketing, domain agents, maintenance, tenant, digital twin, portals, investor reports, AI costs, energy, chatbot, auction, contractors, KDX, and feasibility
- frontend live bindings exist across the main dashboard, analytics, project subroutes, auth, agent orchestration, and several operations pages
- regression gates remain recorded as green in `current-stage.json`

Current execution status:

- `Phase v53.1` completed in stage 48
- `Phase v53.2` completed in stage 49
- `Phase v53.3` completed in stage 50
- `Phase v53.4` completed in stage 51
- `Phase v53.5` completed in stage 52
- `Phase v53.6` completed in stage 53
- `Phase v53.7` completed in stage 54
- `Phase v53.8` completed in stage 55
- `Phase v53.9` completed in stage 56
- `Phase v53.10` completed in stage 57
- `Phase v53.11` completed in stage 58
- `Phase v53.12` completed in stage 59

But that baseline does not automatically satisfy the v53 delta.

## Gap matrix against official v53

| v53 item | Official target | Current evidence | Status | Required action |
|------|------|------|------|------|
| `G158` | `kcci_material_price_service.py`, material price history, update jobs, cost-risk alerts | cost-intelligence backend, persistence, and live workspace exist | implemented | keep ingestion credentials and monitoring as release hardening |
| `G159` | `digital_twin_basic.py`, BIM + IoT status, energy dashboard linkage | `digital_twin_status_service.py` plus live control-tower route exist | implemented | extend with future live sensor providers as needed |
| `G160` | `risk_scoring_engine.py`, seven risk dimensions, P90/VaR | unified risk engine and live APIs now exist | implemented | connect downstream consumers more deeply in future optimization passes |
| `G161` | `contract_generator.py`, auto-generated contracts, PDF/A, e-sign | contract generation, persistence, and e-sign handoff are now live | implemented | extend document export fidelity and provider integrations later |
| `G162` | Korean + English + Chinese UI and translated summaries | locale structure and new contract surface are localized in `ko`, `en`, and `zh-CN` | implemented | keep translation QA in release gating |
| `G163` | manifest plus service worker, offline cache, web push | runtime provider, dashboard install surface, offline route, upgraded `sw.js`, and manifest shortcuts now exist | implemented | extend browser E2E and field-route coverage in release hardening |
| `G164` | `seumter_permit_service.py`, auto-submit, status tracking | permit submission, readiness, and tracking routes now exist | implemented | deepen live integration with provider credentials later |
| `G165` | `cost_escalation_engine.py`, PPI-based escalation simulation | cost escalation engine and live analytics workspace now exist | implemented | keep downstream finance coupling as a later optimization |

## Additional release gaps not covered by G158 to G165

The official v53 delta is not the whole story. The remaining non-delta work is now mostly release-operational rather than feature-functional:

- real provider credentials still need deployment-time cutover for external integrations
- staging deployment, observability, and release-note validation still need a final release-candidate pass
- Playwright boot emits a non-blocking Next.js workspace-root warning because the machine contains an external `/home/kangjh3kang/package-lock.json`

So the v53 roadmap must close both:

- official feature delta gaps
- operator and release hardening gaps

## Optimal v53 execution order

The best order is:

1. `G158` and `G165` together as a shared cost-intelligence foundation
2. `G159`, `G160`, and `G164` as a shared operations and decisioning layer
3. `G161` plus final `G162` hardening
4. `G163` mobile and PWA completion
5. remaining operator-surface and auth hardening
6. approval operations center
7. executable E2E, accessibility, and release cutover

This order is deliberate:

- `G158` and `G165` share the same index-data and cost pipeline
- `G159`, `G160`, and `G164` all feed operator workflows and project-level operational decisions
- `G161` should sit on top of the permit/risk context rather than precede it
- `G163` must stabilize after the primary live surfaces exist
- release gates should validate stable flows, not moving targets

## Phase plan

### Phase v53.1: Cost intelligence foundation (`G158` + `G165`)

Goal:
establish the missing market-index backbone for material pricing and construction-cost escalation

Backend scope:

- add `material_price_history` and related cache tables if absent
- implement `kcci_material_price_service.py`
- implement `cost_escalation_engine.py`
- support KCCI and PPI ingestion with a mock-first fallback that can later use live credentials
- expose read APIs for:
  - latest material prices
  - historical price trend
  - project cost escalation simulation
  - risk alert summary

Frontend scope:

- add a construction-cost intelligence workspace or extend an existing construction/finance surface
- render current material trend, escalation scenario, and alert cards
- keep all read-side failures on the shared retryable query contract

Tests and verification:

- service unit tests for material-price parsing and escalation math
- router tests for new endpoints
- web component tests for trend and retry states

Exit criteria:

- `G158` and `G165` each have real backend services, route contracts, persistence, and a visible operator surface

Current status:

- completed in stage 48
- implementation record: `.build-journal/v53-cost-intelligence-foundation-update-2026-03-25.md`

### Phase v53.2: Twin, risk, and permit operations (`G159` + `G160` + `G164`)

Goal:
close the v53 operations loop from building telemetry to risk scoring to permit readiness

Backend scope:

- add `digital_twin_basic.py` or equivalent v53 status engine
- expose a digital twin status read endpoint that combines BIM context, sensor aggregates, energy state, and anomalies
- add `risk_scoring_engine.py` with seven risk dimensions and scenario-level VaR/P90 outputs
- add `seumter_permit_service.py`
- expose permit submission and permit-status endpoints
- bind the new risk engine into finance, underwriting, and project-read models instead of keeping separate local formulas only

Frontend scope:

- promote digital twin from anomaly-only monitoring to a fuller operations status page
- add permit-status and permit-submission workspace flows at project level
- expose unified risk summaries in the relevant project and dashboard views

Tests and verification:

- unit tests for risk scoring weights, VaR, and digital-twin status aggregation
- contract tests for permit submit and tracking routes
- route-shell and component tests for permit and digital-twin surfaces

Exit criteria:

- `G159`, `G160`, and `G164` are all supported by concrete APIs and visible workflow surfaces

Current status:

- completed in stage 49
- implementation record: `.build-journal/v53-phase-2-operations-risk-permit-update-2026-03-25.md`

### Phase v53.3: Contract automation and i18n hardening (`G161` + `G162`)

Goal:
move from raw e-sign capability to actual auto-generated contract workflows and finish multilingual consistency

Backend scope:

- implement `contract_generator.py`
- persist generated contract drafts and artifacts
- bind generated contracts to the existing `esign` write path
- define contract types for sale, lease, construction, and consulting

Frontend scope:

- add contract-generation entry points from project, lease, or contractor workflows
- surface generated document metadata and sign status
- close remaining untranslated labels on newly added v53 routes

Tests and verification:

- template and payload tests for contract generation
- router tests for draft generation and sign handoff
- locale coverage checks for newly added strings

Exit criteria:

- `G161` is not merely "esign exists", but "contracts can be generated and signed"
- `G162` remains green after the new v53 surfaces are added

Current status:

- completed in stage 50
- implementation record: `.build-journal/v53-phase-3-contracts-i18n-update-2026-03-25.md`

### Phase v53.4: Mobile PWA completion (`G163`)

Goal:
turn the current manifest-only baseline into an actual installable field-operations surface

Scope:

- add service worker registration
- define offline cache strategy for primary operator routes
- add install prompt handling
- establish web-push baseline, even if notifications remain mock-first behind config

Tests and verification:

- smoke test for manifest and service-worker registration
- browser validation for offline fallback on designated routes
- push capability and graceful failure handling

Exit criteria:

- `G163` is satisfied by real install/offline behavior, not only by the presence of `manifest.webmanifest`

Current status:

- completed in stage 51
- implementation plan: `.build-journal/v53-phase-4-pwa-plan-2026-03-25.md`
- implementation record: `.build-journal/v53-phase-4-pwa-update-2026-03-25.md`

### Phase v53.5: Remaining operator hardening

Goal:
remove the main remaining trust gaps outside the official delta

Scope:

- replace placeholder-heavy `safety`, `webrtc`, and `sre` route shells with explicit live workspaces
- harden auth lifecycle:
  - refresh flow in browser
  - expiry recovery
  - Kakao callback completion page
  - logout flow
- keep query error and retry behavior standardized

Exit criteria:

- no primary operator route depends on a `ModulePlaceholder` wrapper for its identity
- auth covers login, register, restore, refresh, callback, and logout

Current status:

- completed in stage 52
- implementation plan: `.build-journal/v53-phase-5-operator-auth-plan-2026-03-26.md`
- implementation record: `.build-journal/v53-phase-5-operator-auth-update-2026-03-26.md`

### Phase v53.6: Approval operations center

Goal:
promote domain-agent approvals into a first-class operational workflow

Scope:

- add a dedicated approval-operations route
- expose cross-project queue, resolved history, approver-role filters, and rationale visibility
- keep project-scoped batch actions where policy allows

Exit criteria:

- approval review is usable without opening the agent analysis route first
- tenant-wide and project-scoped approval review share a dedicated live route with explicit filters and batch-policy guardrails

Current status:

- completed in stage 53
- implementation plan: `.build-journal/v53-phase-6-approval-ops-plan-2026-03-26.md`
- implementation record: `.build-journal/v53-phase-6-approval-ops-update-2026-03-26.md`

### Phase v53.7: E2E, accessibility, and release cutover

Goal:
make v53 releasable, not just feature-complete

Scope:

- verify Playwright browser runtime
- run E2E against the actual live-first application state
- add accessibility execution for release-critical flows
- define final cross-domain smoke chains:
  - auth -> dashboard
  - project -> finance -> report -> design -> BIM
  - maintenance -> tenant -> digital twin
  - permit -> contract -> esign
  - agent -> approval operations
  - KDX -> feasibility

Exit criteria:

- browser E2E runs cleanly
- accessibility checks run on designated routes
- remaining descopes are explicit in release notes

Current status:

- completed in stage 54
- implementation plan: `.build-journal/v53-phase-7-release-cutover-plan-2026-03-26.md`
- implementation record: `.build-journal/v53-phase-7-release-cutover-update-2026-03-26.md`

### Phase v53.8: Release deployment hardening

Goal:
make the deployment path fail fast on bad release contracts and validate more than a single health URL after rollout

Scope:

- add release preflight validation for staging and production deploy secrets
- standardize deploy-time environment contract for:
  - kubeconfig
  - API URL
  - web URL
  - release smoke token
- replace shallow curl-based deploy checks with scripted release smoke coverage for:
  - `/health`
  - `/api/v1/auth/me`
  - `/api/v1/system/version`
  - `/api/v1/system/health/full`
  - `/api/v1/dashboard/stats`
  - key live web routes
- extend `verify_system.sh` with release automation verification

Exit criteria:

- deploy workflows both run preflight validation before build and deploy
- deploy workflows both run post-deploy scripted smoke validation
- release automation stays green inside the existing quality-gate bundle

Current status:

- completed in stage 55
- implementation plan: `.build-journal/v53-phase-8-deployment-hardening-plan-2026-03-26.md`
- implementation record: `.build-journal/v53-phase-8-deployment-hardening-update-2026-03-26.md`

### Phase v53.9: Release rehearsal hardening

Goal:
remove the last deployment and browser drift before the first live staging rehearsal

Scope:

- pin rollout images explicitly in staging and production deploy workflows
- remove the legacy deploy path from the generic CI workflow
- align worker image and production namespace contracts in k8s manifests
- validate release assets statically:
  - deploy workflow contracts
  - k8s overlays
  - monitoring alerts and webhook routing
  - Grafana dashboard assets
- stabilize the project release Playwright chain against route and autofill flakiness

Exit criteria:

- deploy workflows pin the exact built images they intend to roll out
- generic CI no longer triggers a competing deploy path
- static release asset validation is part of the system verification bundle
- Playwright release cutover remains green after the rehearsal hardening

Current status:

- completed in stage 56
- implementation plan: `.build-journal/v53-phase-9-release-rehearsal-hardening-plan-2026-03-27.md`
- implementation record: `.build-journal/v53-phase-9-release-rehearsal-hardening-update-2026-03-27.md`

### Phase v53.10: Observability rehearsal readiness

Goal:
make the first live staging rehearsal executable with manual workflow entry points and a coded observability gate

Scope:

- add `workflow_dispatch` to staging and production deploy workflows
- add post-deploy observability smoke validation for:
  - Prometheus readiness and query API
  - Alertmanager status and receivers
  - Grafana health and dashboard search
- extend release asset validation and system verification to cover the new rehearsal contract

Exit criteria:

- release workflows can be launched manually for staging rehearsal
- observability smoke validation is present as executable code
- quality gates remain green after the new rehearsal gate is added

Current status:

- completed in stage 57
- implementation plan: `.build-journal/v53-phase-10-observability-rehearsal-plan-2026-03-27.md`
- implementation record: `.build-journal/v53-phase-10-observability-rehearsal-update-2026-03-27.md`

### Phase v53.11: Rehearsal evidence automation

Goal:
ensure the first live staging rehearsal leaves a cutover-ready evidence bundle even when failures occur

Scope:

- generate markdown and JSON release evidence reports
- capture rollout logs, kubectl inventory, pod snapshots, and event logs
- upload the evidence bundle from staging and production deploy workflows
- validate the evidence wiring inside release asset checks and system verification

Exit criteria:

- release workflows always emit a structured evidence bundle
- report generation works for both success and failure combinations
- quality gates remain green after the evidence automation is added

Current status:

- completed in stage 58
- implementation plan: `.build-journal/v53-phase-11-rehearsal-evidence-automation-plan-2026-03-27.md`
- implementation record: `.build-journal/v53-phase-11-rehearsal-evidence-automation-update-2026-03-27.md`

### Phase v53.12: Cutover checklist automation

Goal:
turn the rehearsal evidence bundle into an operator-facing signoff packet before the first live staging release

Scope:

- generate markdown and JSON cutover checklists from the release evidence report
- wire checklist generation into staging and production deploy workflows
- document the GitHub environment secret contract in `.env.example`
- validate the checklist wiring and secret reference contract in release asset checks and system verification

Exit criteria:

- every deploy rehearsal artifact bundle contains both a release report and a cutover checklist
- the required GitHub environment secret contract is explicitly documented in-repo
- full quality gates remain green after the checklist automation is added

Current status:

- completed in stage 59
- implementation plan: `.build-journal/v53-phase-12-cutover-checklist-plan-2026-03-27.md`
- implementation record: `.build-journal/v53-phase-12-cutover-checklist-update-2026-03-27.md`

## Immediate next action

Start live release rehearsal against real infrastructure.

The first concrete execution order should be:

1. populate the standardized release secrets for staging and production environments
2. run the staging deployment workflow end-to-end with the new image-pinning, smoke, evidence, and checklist gates
3. verify observability, alert routing, and operational dashboards against the live rollout
4. review the generated release report and cutover checklist for operator signoff
5. schedule production cutover only after the staging rehearsal remains green and the cutover packet is accepted

## What should not be treated as the v53 driver

These should not outrank the official delta and release completion work:

- more broad Part E/F/G expansion without a v53 document tie-back
- speculative new AI modules with no operator route impact
- schema growth that does not close `G158` to `G165` or release readiness gaps

## Revalidation rule

If the v53 documents are revised again, rerun the delta analysis against:

- official v53 Part A, B, and C
- current implementation state
- recorded quality gates
- current route inventory
