# Product Truth Alignment

## Identity
- Product type: Real-time fantasy decision assistant.
- Not a prediction app.
- Discovery scope: Multi-sport entry path (Soccer, NFL, NBA, Cricket).
- Active execution scope: Cricket lanes only.
- League status:
  - IPL: active
  - T20 World Cup: lane added, decision flows pending
- Primary user persona: Active fantasy cricket user making in-match lineup and captaincy decisions.
- Single job statement: Reduce regret at decision moments.

## Scope Freeze
- Keep only flows that improve timing, clarity, and calm at decision moments.
- Cut any feature that does not directly support a single-action recommendation.
- Keep non-cricket sports as discovery placeholders until dedicated decision engines are implemented.

## Decision Moments Engine
- Defined leverage moments:
1. Opening powerplay entry
2. Early wicket shock
3. Powerplay exit
4. Overs 7-10 rebuild
5. Middle overs acceleration
6. Set batter vulnerability
7. Spin lock pressure
8. Death overs entry
9. Death overs collapse risk
10. Chase required-rate spike
11. Chase stability window
12. Final 24-ball flip zone
13. Final 12-ball closer
14. Super-over edge
15. Hold window

## Core IP Components
- Latent state layer:
  - Momentum
  - Collapse risk
  - Acceleration window
  - Stability index
- Counterfactual simulator:
  - "If X happens in next Y balls, does outcome control flip?"
- Noise suppression:
  - Minimum confidence delta
  - Cooldown window

## Product Surface Rules
- Directional outputs only: Hold, Lean, Strong, Flip.
- Risk modes: Conservative, Balanced, Aggressive.
- Single action per decision moment.
- One-line micro-why only.
- Silence is explicit when no meaningful change qualifies.

## UI Principles
- Calm, high-contrast, low-noise visual language.
- Decision-first layout.
- Time-to-next-window visibility.
- Motion only on meaning change.
- Zero clutter rule.

## Metrics
- Decisions acted on per match.
- Action timing vs optimal window.
- Hold rate after losses.
- Decision latency reduction.
- Risk mode distribution.

## Investor Narrative
- Category is not "another predictor."
- Defensible moat: state abstraction + counterfactual logic + update restraint.
- Expansion path:
  - Near term: strengthen IPL and ship T20 World Cup decision flows.
  - Later: extend same engine to additional sports.
