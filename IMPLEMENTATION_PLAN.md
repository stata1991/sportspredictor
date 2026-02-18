# Implementation Plan - Product Truth Alignment

## Goals
- Reorient product from prediction outputs to real-time decision assistance.
- Enforce decision-moment gating and noise suppression on all live recommendations.
- Preserve non-cricket lanes as discovery placeholders until decision engines are ready.
- Add minimal metrics capture to validate decision timing and usage.

## Phase 0 - Audit And Safety Rails
- Inventory and tag all endpoints and UI surfaces that produce predictions.
- Add feature flags or config toggles to disable prediction endpoints in production mode.
- Update API and UI copy to consistently present as a decision assistant.

Deliverables
- Config flag: `DECISION_ASSIST_ONLY=true` (or similar) to gate prediction endpoints.
- Internal doc mapping endpoints to Product Truth constraints.

## Phase 1 - Backend Decision Engine Alignment

### 1.1 Enforce Trigger Rules And Confidence Floors
- Add confidence computation for each decision moment.
- Gate output on `TRIGGER_RULES` confidence floors.
- If confidence < floor, return `silent=true` with explicit reason.

Deliverables
- Updated `evaluate_decision` to compute confidence per moment.
- `silent_reason` values aligned to the Product Truth (delta, cooldown, confidence).

### 1.2 Single-Action Semantics
- Define action templates for each decision moment and direction (Hold/Lean/Strong/Flip).
- Ensure the response contains only one action with one-line micro-why.

Deliverables
- New `ActionTemplate` mapping in `backend/decision_engine.py`.
- API response includes `action` string, not generic "Act now".

### 1.3 Counterfactual Simulator Hook
- Ensure counterfactual outputs are tied to the decision moment and horizon.
- Return a minimal counterfactual summary line (not full model output).

Deliverables
- `counterfactual_summary` field in decision response.

## Phase 2 - API Surface Cleanup

### 2.1 Deprecate Prediction Endpoints
- Mark `/predict/*` endpoints as deprecated or move behind a flag.
- Remove direct usage from UI for end users.

Deliverables
- 410 or feature-flag disabled responses for `/predict/*` in decision-assist mode.
- Updated API docs to highlight `/assist/decision` as primary.

### 2.2 NLP Query Alignment
- Replace prediction-leaning NLP intents with decision-moment intents.
- Return action summaries or "silent" for off-moment requests.

Deliverables
- Revised NLP parsing and response mapping.

## Phase 3 - Frontend Alignment

### 3.1 Live Match Page
- Present only decision output (direction + single action + micro-why + next window).
- Hide any raw prediction outputs.
- Emphasize "silence" as a normal state.

Deliverables
- Updated `frontend/src/pages/LiveMatchPage.tsx` UI.

### 3.2 Pre-Match Page
- Replace prediction buttons with pre-match decision prep (context only).
- If no action is warranted, show explicit silence.

Deliverables
- Updated `frontend/src/pages/PreMatchPage.tsx`.

### 3.3 Discovery Lanes
- Keep Soccer/NFL/NBA as placeholders only.
- Add clear "decision engine coming" copy.

Deliverables
- Updated `frontend/src/pages/HomePage.tsx` and placeholders.

## Phase 4 - Metrics And Instrumentation

### 4.1 Metrics Schema
- Define event types:
  - decision_shown
  - decision_acted
  - decision_silent
  - risk_mode_selected
  - decision_latency

Deliverables
- Metrics event schema in backend (CSV or logging table).

### 4.2 Capture Events
- Emit metrics on decision response and user actions.
- Track timing vs leverage windows.

Deliverables
- Minimal persistence (CSV or lightweight DB table).
- Documented analytics fields.

## Phase 5 - T20 World Cup Lane
- Implement decision-moment flows (can reuse IPL logic initially).
- Use a match context loader for T20WC schedule and live data.

Deliverables
- T20WC data loader.
- Decision engine enabled for T20WC lane.

## Validation Checklist
- Prediction endpoints are disabled or hidden in user flows.
- All decision responses use Hold/Lean/Strong/Flip with one action and one micro-why.
- Silence only when delta/cooldown/confidence floors are not met.
- UI shows only decision outputs; no score/winner predictions.
- Metrics logging captured for every decision response.

## Optional Enhancements (Post-MVP)
- Personalized risk profile per user.
- Context-aware micro-why templates tuned per decision moment.
- Expand to additional sports once decision engines exist.
