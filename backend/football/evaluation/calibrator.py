"""Calibration evaluation: Dixon-Coles vs Elo baseline.

Trains both models on the training set (kickoff_utc <= cutoff),
evaluates on the held-out test set (kickoff_utc > cutoff), and
produces Brier scores, hit rates, a calibration plot, and a
PASS/FAIL verdict.

Usage::

    python -m backend.football.evaluation.calibrator
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend.
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backend.football.models.dixon_coles import (
    DixonColesModel,
    train as train_dc,
)
from backend.football.models.elo_baseline import (
    EloModel,
    train as train_elo,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
TRAINED_DIR = Path(__file__).resolve().parent.parent / "models" / "trained"
DATA_PATH = Path(__file__).resolve().parent.parent / "historical" / "data" / "matches.parquet"

CUTOFF = pd.Timestamp("2024-06-01", tz="UTC")
BRIER_GATE_PP = 3.0  # Dixon-Coles must beat Elo by >= 3 percentage points.

LEAGUE_NAMES = {
    1: "World Cup",
    4: "Euro Championship",
    29: "WC Qual Africa",
    30: "WC Qual Asia",
    31: "WC Qual CONCACAF",
    32: "WC Qual Europe",
    33: "WC Qual Oceania",
    34: "WC Qual South America",
    960: "Euro 2024 Qualifying",
}


# ── Brier score ────────────────────────────────────────────────────

def brier_score(
    p_home: float, p_draw: float, p_away: float,
    actual_home_goals: int, actual_away_goals: int,
) -> float:
    """Compute the 3-outcome Brier score for a single match."""
    if actual_home_goals > actual_away_goals:
        actual = np.array([1.0, 0.0, 0.0])
    elif actual_home_goals == actual_away_goals:
        actual = np.array([0.0, 1.0, 0.0])
    else:
        actual = np.array([0.0, 0.0, 1.0])
    predicted = np.array([p_home, p_draw, p_away])
    return float(np.sum((predicted - actual) ** 2))


# ── Evaluation ─────────────────────────────────────────────────────

def evaluate_model(
    model_name: str,
    predict_fn,
    test_df: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate a model on the test set.

    Returns a DataFrame with per-match predictions and Brier scores.
    """
    rows = []
    for _, match in test_df.iterrows():
        h_id = int(match["home_team_id"])
        a_id = int(match["away_team_id"])
        pred = predict_fn(h_id, a_id)

        p_h = pred["p_home_win"]
        p_d = pred["p_draw"]
        p_a = pred["p_away_win"]

        hg = int(match["home_goals"])
        ag = int(match["away_goals"])

        bs = brier_score(p_h, p_d, p_a, hg, ag)

        # Determine actual and predicted outcome.
        if hg > ag:
            actual = "home"
        elif hg == ag:
            actual = "draw"
        else:
            actual = "away"

        probs = {"home": p_h, "draw": p_d, "away": p_a}
        top_pick = max(probs, key=probs.get)

        rows.append({
            "model": model_name,
            "fixture_id": match["fixture_id"],
            "league_id": match["league_id"],
            "kickoff_utc": match["kickoff_utc"],
            "home_team": match["home_team_name"],
            "away_team": match["away_team_name"],
            "home_goals": hg,
            "away_goals": ag,
            "actual_outcome": actual,
            "p_home_win": p_h,
            "p_draw": p_d,
            "p_away_win": p_a,
            "top_pick": top_pick,
            "top_pick_correct": top_pick == actual,
            "brier_score": bs,
        })

    return pd.DataFrame(rows)


# ── Calibration plot ───────────────────────────────────────────────

def calibration_plot(
    dc_results: pd.DataFrame,
    elo_results: pd.DataFrame,
    output_path: Path,
) -> None:
    """Calibration plot: predicted vs observed home-win frequency."""
    fig, ax = plt.subplots(figsize=(8, 6))

    for results, label, color in [
        (dc_results, "Dixon-Coles", "#2563eb"),
        (elo_results, "Elo Baseline", "#dc2626"),
    ]:
        probs = results["p_home_win"].values
        actuals = (results["actual_outcome"] == "home").astype(float).values

        # Bucket into ~10 bins by predicted probability.
        bins = np.linspace(0, 1, 11)
        bin_indices = np.digitize(probs, bins) - 1
        bin_indices = np.clip(bin_indices, 0, len(bins) - 2)

        bin_means = []
        bin_observed = []
        bin_counts = []

        for i in range(len(bins) - 1):
            mask = bin_indices == i
            if mask.sum() > 0:
                bin_means.append(probs[mask].mean())
                bin_observed.append(actuals[mask].mean())
                bin_counts.append(mask.sum())

        ax.plot(bin_means, bin_observed, "o-", label=f"{label} (n per bin)", color=color)

    # Perfect calibration line.
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    ax.set_xlabel("Predicted P(home win)")
    ax.set_ylabel("Observed home-win frequency")
    ax.set_title("Calibration Plot: Home Win Outcome")
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Calibration plot saved to %s", output_path)


# ── Main ───────────────────────────────────────────────────────────

def run_evaluation() -> dict:
    """Run the full evaluation pipeline. Returns the results dict."""
    # Load data.
    df = pd.read_parquet(DATA_PATH)
    train_df = df[df["kickoff_utc"] <= CUTOFF].copy()
    test_df = df[df["kickoff_utc"] > CUTOFF].copy()

    logger.info(
        "Train: %d matches (%s → %s)",
        len(train_df), train_df["kickoff_utc"].min().date(), train_df["kickoff_utc"].max().date(),
    )
    logger.info(
        "Test: %d matches (%s → %s)",
        len(test_df), test_df["kickoff_utc"].min().date(), test_df["kickoff_utc"].max().date(),
    )

    # Train both models on training set.
    logger.info("Training Dixon-Coles...")
    dc_model = train_dc(train_df)
    logger.info("Training Elo baseline...")
    elo_model = train_elo(train_df)

    # Save trained models.
    TRAINED_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    dc_path = TRAINED_DIR / f"dixon_coles_{today}.json"
    elo_path = TRAINED_DIR / f"elo_baseline_{today}.json"
    dc_model.save(dc_path)
    elo_model.save(elo_path)

    # Evaluate on test set.
    logger.info("Evaluating Dixon-Coles on %d test matches...", len(test_df))
    dc_results = evaluate_model("dixon_coles", dc_model.predict_match, test_df)
    logger.info("Evaluating Elo on %d test matches...", len(test_df))
    elo_results = evaluate_model("elo_baseline", elo_model.predict_match, test_df)

    # Aggregate metrics.
    dc_brier = dc_results["brier_score"].mean()
    elo_brier = elo_results["brier_score"].mean()
    brier_diff_pp = (elo_brier - dc_brier) * 100  # positive = DC is better

    dc_hit = dc_results["top_pick_correct"].mean()
    elo_hit = elo_results["top_pick_correct"].mean()

    verdict = "PASS" if brier_diff_pp >= BRIER_GATE_PP else "FAIL"

    # Console output.
    print("\n" + "=" * 65)
    print("CALIBRATION GATE — Dixon-Coles vs Elo Baseline")
    print("=" * 65)
    print(f"  Test matches:          {len(test_df)}")
    print(f"  Training matches:      {len(train_df)}")
    print(f"  Cutoff:                {CUTOFF.date()}")
    print("-" * 65)
    print(f"  {'Metric':<30} {'Dixon-Coles':>12} {'Elo':>12} {'Delta':>12}")
    print("-" * 65)
    print(f"  {'Brier score (lower=better)':<30} {dc_brier:>12.4f} {elo_brier:>12.4f} {brier_diff_pp:>+11.2f}pp")
    print(f"  {'Top-pick hit rate':<30} {dc_hit:>11.1%} {elo_hit:>11.1%} {(dc_hit - elo_hit)*100:>+11.2f}pp")
    print("-" * 65)
    print(f"  Gate threshold: DC must beat Elo by >= {BRIER_GATE_PP:.0f}pp on Brier")
    print(f"  Brier improvement:     {brier_diff_pp:+.2f}pp")
    print(f"  VERDICT:               {verdict}")
    print("=" * 65)

    # Build results dict.
    results = {
        "evaluation_date": today,
        "cutoff": str(CUTOFF.date()),
        "train_matches": len(train_df),
        "test_matches": len(test_df),
        "dixon_coles": {
            "brier_score": round(dc_brier, 6),
            "top_pick_hit_rate": round(dc_hit, 4),
            "model_path": str(dc_path),
        },
        "elo_baseline": {
            "brier_score": round(elo_brier, 6),
            "top_pick_hit_rate": round(elo_hit, 4),
            "model_path": str(elo_path),
        },
        "brier_improvement_pp": round(brier_diff_pp, 2),
        "hit_rate_improvement_pp": round((dc_hit - elo_hit) * 100, 2),
        "gate_threshold_pp": BRIER_GATE_PP,
        "verdict": verdict,
    }

    # Write results JSON.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUTPUT_DIR / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Results written to %s", results_path)

    # Calibration plot.
    plot_path = OUTPUT_DIR / "calibration.png"
    calibration_plot(dc_results, elo_results, plot_path)

    # Per-league breakdown (for diagnostics if FAIL).
    print("\n  Per-league Brier scores (test set):")
    print(f"  {'League':<35} {'N':>5} {'DC':>8} {'Elo':>8} {'Delta':>8}")
    print("  " + "-" * 64)
    for lid in sorted(test_df["league_id"].unique()):
        mask_dc = dc_results["league_id"] == lid
        mask_elo = elo_results["league_id"] == lid
        n = mask_dc.sum()
        dc_b = dc_results.loc[mask_dc, "brier_score"].mean()
        elo_b = elo_results.loc[mask_elo, "brier_score"].mean()
        name = LEAGUE_NAMES.get(lid, f"League {lid}")
        print(f"  {name:<35} {n:>5} {dc_b:>8.4f} {elo_b:>8.4f} {(elo_b - dc_b)*100:>+7.2f}pp")

    return results


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_evaluation()


if __name__ == "__main__":
    main()
