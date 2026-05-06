import React from 'react';
import { Box, Paper, Typography } from '@mui/material';
import { DeterministicPrediction, FixtureStage, Reasoning, Upset } from '../../types/prediction';
import { colors } from '../../colors';
import NumbersSection from './NumbersSection';
import ContextSection from './ContextSection';
import UpsetSection from './UpsetSection';

interface WhyPanelProps {
  prediction: DeterministicPrediction | null;
  reasoning: Reasoning | null;
  upset: Upset | null;
  stage: FixtureStage | null;
  partialAgent: boolean;
  homeTeam: string;
  awayTeam: string;
}

const WhyPanel: React.FC<WhyPanelProps> = ({
  prediction,
  reasoning,
  upset,
  stage,
  partialAgent,
  homeTeam,
  awayTeam,
}) => {
  if (!prediction || !stage) {
    return null;
  }

  // Derive favourite info for UpsetSection gating.
  // If draw is the highest probability, there is no "favourite" to upset.
  const { p_home_win, p_draw, p_away_win } = prediction.winner;
  const maxProb = Math.max(p_home_win, p_draw, p_away_win);
  const drawIsFavourite = p_draw === maxProb;
  const favouriteProbability = drawIsFavourite ? 0 : Math.max(p_home_win, p_away_win);
  const favouriteTeam = p_home_win >= p_away_win ? homeTeam : awayTeam;
  const underdogName = p_home_win >= p_away_win ? awayTeam : homeTeam;

  return (
    <Paper data-testid="why-panel" sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2, fontWeight: 700 }}>
        Why this prediction?
      </Typography>

      <NumbersSection
        prediction={prediction}
        stage={stage}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />

      {reasoning ? (
        <ContextSection reasoning={reasoning} />
      ) : (
        partialAgent && (
          <Box
            data-testid="partial-agent-notice"
            sx={{
              mt: 2,
              p: 1.5,
              borderRadius: 2,
              backgroundColor: 'rgba(255, 152, 0, 0.1)',
              border: '1px solid rgba(255, 152, 0, 0.3)',
            }}
          >
            <Typography variant="caption" sx={{ color: colors.caution }}>
              Agent reasoning is not available for this prediction.
            </Typography>
          </Box>
        )
      )}

      {upset && (
        <UpsetSection
          upset={upset}
          favouriteProbability={favouriteProbability}
          favouriteTeam={favouriteTeam}
          underdogName={underdogName}
        />
      )}
    </Paper>
  );
};

export default WhyPanel;
