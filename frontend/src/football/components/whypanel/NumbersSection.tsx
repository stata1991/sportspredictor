import React from 'react';
import {
  Box,
  Typography,
  Chip,
  Tooltip,
  LinearProgress,
  linearProgressClasses,
} from '@mui/material';
import { DeterministicPrediction, FixtureStage } from '../../types/prediction';
import { colors } from '../../colors';
import { formatPercent, topNScorelines } from '../../utils/probability';
import { sectionLabelSx } from './styles';
import ScorelineHeatmap from './ScorelineHeatmap';

// ── Props ───────────────────────────────────────────────────────────

interface NumbersSectionProps {
  prediction: DeterministicPrediction;
  stage: FixtureStage;
  homeTeam: string;
  awayTeam: string;
}

// ── Confidence label logic ──────────────────────────────────────────

/**
 * Map (confidence, stage) to a user-facing label + tooltip.
 *
 * No internal model jargon — the label communicates epistemic state
 * to someone who has never heard of Dixon-Coles.
 */
function getConfidenceLabel(confidence: string, stage: FixtureStage): {
  label: string;
  tooltip: string;
  color: string;
} {
  if (stage === 'pre_lineup' && confidence === 'low_data') {
    return {
      label: 'Early estimate',
      tooltip: 'Lineups not yet released and historical data is sparse for one or both teams. Probabilities will sharpen closer to kickoff.',
      color: colors.caution, // amber — treat with caution
    };
  }
  if (stage === 'pre_lineup') {
    return {
      label: 'Pre-match estimate',
      tooltip: 'Prediction based on historical form. Will refine when lineups are confirmed.',
      color: colors.neutral, // neutral grey — standard state
    };
  }
  if (stage === 'post_lineup' && confidence === 'low_data') {
    return {
      label: 'Limited data',
      tooltip: 'Lineups confirmed, but model has limited history for one or both teams.',
      color: colors.caution,
    };
  }
  if (stage === 'post_lineup') {
    return {
      label: 'Lineups confirmed',
      tooltip: 'Final prediction based on confirmed starting lineups.',
      color: colors.neutral,
    };
  }
  if (stage === 'live') {
    return {
      label: 'Live',
      tooltip: 'Probabilities update as the match progresses.',
      color: colors.homeAccent, // primary accent — active state
    };
  }
  if (stage === 'completed') {
    return {
      label: 'Final — pre-match prediction',
      tooltip: 'This match has finished. Showing what we predicted before kickoff.',
      color: '#78909c', // muted/desaturated
    };
  }
  return {
    label: 'Estimate',
    tooltip: 'Prediction based on available data.',
    color: colors.neutral,
  };
}

// ── Sub-components ──────────────────────────────────────────────────

/** Single contextual confidence chip with tooltip */
const ConfidenceHeader: React.FC<{
  confidence: string;
  stage: FixtureStage;
}> = ({ confidence, stage }) => {
  const { label, tooltip, color } = getConfidenceLabel(confidence, stage);

  return (
    <Box
      data-testid="confidence-header"
      sx={{ mb: 2 }}
    >
      <Tooltip title={tooltip} arrow placement="right">
        <Chip
          label={label}
          size="small"
          data-testid="confidence-chip"
          sx={{
            backgroundColor: color,
            color: colors.darkText,
            fontWeight: 700,
            fontSize: '0.7rem',
            cursor: 'default',
          }}
        />
      </Tooltip>
    </Box>
  );
};

/** Horizontal probability bars for 1X2 outcome */
const WinnerBars: React.FC<{
  pHome: number;
  pDraw: number;
  pAway: number;
  homeTeam: string;
  awayTeam: string;
}> = ({ pHome, pDraw, pAway, homeTeam, awayTeam }) => {
  const bars = [
    { label: homeTeam, value: pHome, color: colors.homeAccent },
    { label: 'Draw', value: pDraw, color: colors.labelText },
    { label: awayTeam, value: pAway, color: colors.awayAccent },
  ];

  return (
    <Box data-testid="winner-bars" sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={sectionLabelSx}>
        Match Result
      </Typography>
      {bars.map((bar) => (
        <Box key={bar.label} sx={{ mb: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
            <Typography variant="caption" sx={{ color: colors.textPrimary, fontWeight: 600 }}>
              {bar.label}
            </Typography>
            <Typography variant="caption" sx={{ color: bar.color, fontWeight: 700 }}>
              {formatPercent(bar.value)}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={bar.value * 100}
            sx={{
              height: 8,
              borderRadius: 4,
              backgroundColor: 'rgba(255,255,255,0.08)',
              [`& .${linearProgressClasses.bar}`]: {
                borderRadius: 4,
                backgroundColor: bar.color,
              },
            }}
          />
        </Box>
      ))}
    </Box>
  );
};

/** Over/Under total goals — stacked bar for 2.5 line, inline text for 1.5 */
const TotalGoalsSection: React.FC<{
  expectedTotal: number;
  over2_5: number;
  under2_5: number;
  over1_5: number;
  under1_5: number;
}> = ({ expectedTotal, over2_5, under2_5, over1_5, under1_5 }) => {
  return (
    <Box data-testid="total-goals" sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={sectionLabelSx}>
        Total Goals
      </Typography>
      <Typography variant="caption" sx={{ color: colors.labelText, display: 'block', mb: 1 }}>
        Expected: {expectedTotal.toFixed(1)}
      </Typography>

      {/* Primary: Over/Under 2.5 stacked bar */}
      <Box sx={{ mb: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
          <Typography variant="caption" sx={{ color: colors.textPrimary, fontWeight: 600 }}>
            Over 2.5
          </Typography>
          <Typography variant="caption" sx={{ color: colors.textPrimary, fontWeight: 600 }}>
            Under 2.5
          </Typography>
        </Box>
        <Box
          sx={{
            display: 'flex',
            height: 8,
            borderRadius: 4,
            overflow: 'hidden',
            backgroundColor: 'rgba(255,255,255,0.08)',
          }}
        >
          <Box
            sx={{
              width: `${over2_5 * 100}%`,
              backgroundColor: colors.homeAccent,
            }}
          />
          <Box
            sx={{
              width: `${under2_5 * 100}%`,
              backgroundColor: colors.awayAccent,
            }}
          />
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.25 }}>
          <Typography variant="caption" sx={{ color: colors.homeAccent, fontWeight: 700 }}>
            {formatPercent(over2_5)}
          </Typography>
          <Typography variant="caption" sx={{ color: colors.awayAccent, fontWeight: 700 }}>
            {formatPercent(under2_5)}
          </Typography>
        </Box>
      </Box>

      {/* Secondary: 1.5 line — inline, muted */}
      <Typography variant="caption" sx={{ color: colors.labelText, fontSize: '0.75rem' }}>
        Over 1.5: {formatPercent(over1_5)} · Under 1.5: {formatPercent(under1_5)}
      </Typography>
    </Box>
  );
};

/** Top-N most likely half-time scorelines as pills */
const HTScorelinePills: React.FC<{
  matrix: number[][];
}> = ({ matrix }) => {
  const top = topNScorelines(matrix, 5);

  return (
    <Box data-testid="ht-scoreline-pills" sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={sectionLabelSx}>
        HT Scorelines
      </Typography>
      <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
        {top.map((entry) => (
          <Chip
            key={`${entry.home}-${entry.away}`}
            label={`${entry.home}–${entry.away}  ${formatPercent(entry.probability)}`}
            size="small"
            sx={{
              backgroundColor: 'rgba(255,255,255,0.08)',
              color: colors.textPrimary,
              fontWeight: 600,
              fontSize: '0.7rem',
            }}
          />
        ))}
      </Box>
    </Box>
  );
};

/** First to score probabilities */
const FirstToScore: React.FC<{
  pHomeFirst: number;
  pAwayFirst: number;
  pNoGoals: number;
  homeTeam: string;
  awayTeam: string;
}> = ({ pHomeFirst, pAwayFirst, pNoGoals, homeTeam, awayTeam }) => {
  const items = [
    { label: homeTeam, value: pHomeFirst, color: colors.homeAccent },
    { label: awayTeam, value: pAwayFirst, color: colors.awayAccent },
    { label: 'No Goals', value: pNoGoals, color: colors.labelText },
  ];

  return (
    <Box data-testid="first-to-score">
      <Typography variant="subtitle2" sx={sectionLabelSx}>
        First to Score
      </Typography>
      <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
        {items.map((item) => (
          <Box key={item.label} sx={{ textAlign: 'center' }}>
            <Typography
              variant="h6"
              sx={{ color: item.color, fontWeight: 800, lineHeight: 1 }}
            >
              {formatPercent(item.value)}
            </Typography>
            <Typography variant="caption" sx={{ color: colors.labelText, fontSize: '0.65rem' }}>
              {item.label}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

// ── Main Component ──────────────────────────────────────────────────

const NumbersSection: React.FC<NumbersSectionProps> = ({
  prediction,
  stage,
  homeTeam,
  awayTeam,
}) => {
  const { winner, total_goals, ht_score, first_to_score } = prediction;

  return (
    <Box data-testid="numbers-section">
      <ConfidenceHeader confidence={winner.confidence} stage={stage} />

      <WinnerBars
        pHome={winner.p_home_win}
        pDraw={winner.p_draw}
        pAway={winner.p_away_win}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />

      <TotalGoalsSection
        expectedTotal={total_goals.expected_total}
        over2_5={total_goals.over_2_5}
        under2_5={total_goals.under_2_5}
        over1_5={total_goals.over_1_5}
        under1_5={total_goals.under_1_5}
      />

      <HTScorelinePills matrix={ht_score.ht_scoreline_matrix} />

      {winner.scoreline_matrix && (
        <Box sx={{ mt: 3, mb: 2 }}>
          <ScorelineHeatmap
            matrix={winner.scoreline_matrix}
            homeTeam={homeTeam}
            awayTeam={awayTeam}
          />
        </Box>
      )}

      <FirstToScore
        pHomeFirst={first_to_score.p_home_first}
        pAwayFirst={first_to_score.p_away_first}
        pNoGoals={first_to_score.p_no_goals}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />
    </Box>
  );
};

export default NumbersSection;
