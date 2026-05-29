import React, { useState } from 'react';
import { Helmet } from 'react-helmet-async';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Typography, Button, CircularProgress } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useMatchPrediction } from '../../football/hooks/useMatchPrediction';
import { useHeadToHead } from '../../football/hooks/useHeadToHead';
import { isCompleted } from '../../football/utils/fixtureStatus';
import WhyPanel from '../../football/components/whypanel/WhyPanel';
import HeadToHeadSection from '../../football/components/HeadToHeadSection';
import LiveMatchSection from '../../football/components/LiveMatchSection';
import LiveBadge from '../../football/components/LiveBadge';
import MatchUnavailableSection from '../../football/components/MatchUnavailableSection';

// ── Error state UIs ─────────────────────────────────────────────────

const NotFoundState: React.FC<{ fixtureId: string }> = ({ fixtureId }) => (
  <Box data-testid="error-not-found" sx={{ textAlign: 'center', mt: 6 }}>
    <Typography variant="h5" sx={{ mb: 1 }}>
      Fixture Not Found
    </Typography>
    <Typography variant="body2" sx={{ color: 'text.secondary' }}>
      Fixture {fixtureId} does not exist or has been removed.
    </Typography>
  </Box>
);

const NetworkErrorState: React.FC<{ onRetry: () => void }> = ({ onRetry }) => (
  <Box data-testid="error-network" sx={{ textAlign: 'center', mt: 6 }}>
    <Typography variant="h5" sx={{ mb: 1 }}>
      Connection Error
    </Typography>
    <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
      Could not reach the prediction server. Please try again.
    </Typography>
    <Button variant="contained" onClick={onRetry}>
      Retry
    </Button>
  </Box>
);

const UnknownErrorState: React.FC<{ message: string; onRetry: () => void }> = ({
  message,
  onRetry,
}) => (
  <Box data-testid="error-unknown" sx={{ textAlign: 'center', mt: 6 }}>
    <Typography variant="h5" sx={{ mb: 1 }}>
      Something went wrong
    </Typography>
    <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
      {message}
    </Typography>
    <Button variant="contained" onClick={onRetry}>
      Retry
    </Button>
  </Box>
);

// ── Main MatchPage ──────────────────────────────────────────────────

const MatchPage: React.FC = () => {
  const { fixtureId } = useParams<{ fixtureId: string }>();
  const navigate = useNavigate();
  const [retryKey, setRetryKey] = useState(0);

  return (
    <Box sx={{ maxWidth: 700, mx: 'auto', px: 2, py: 3 }}>
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate('/football/world-cup-2026')}
        sx={{
          mb: 2,
          color: '#b0bec5',
          textTransform: 'none',
          background: 'transparent',
          boxShadow: 'none',
          '&:hover': {
            background: 'rgba(255,255,255,0.05)',
            transform: 'none',
            boxShadow: 'none',
          },
        }}
      >
        Back to Fixtures
      </Button>

      <MatchContent
        key={retryKey}
        fixtureId={fixtureId}
        onRetry={() => setRetryKey((k) => k + 1)}
      />
    </Box>
  );
};

// Inner component that remounts on retry
const MatchContent: React.FC<{
  fixtureId: string | undefined;
  onRetry: () => void;
}> = ({ fixtureId, onRetry }) => {
  const result = useMatchPrediction(fixtureId);
  const h2h = useHeadToHead(result.homeTeamId, result.awayTeamId);

  if (result.loading) {
    return (
      <Box sx={{ textAlign: 'center', mt: 6 }}>
        <CircularProgress size={48} sx={{ color: '#ff6f00' }} />
        <Typography variant="body2" sx={{ mt: 2, color: 'text.secondary' }}>
          Loading prediction…
        </Typography>
      </Box>
    );
  }

  if (result.error) {
    switch (result.errorKind) {
      case 'not_found':
        return <NotFoundState fixtureId={fixtureId || ''} />;
      case 'live':
        return (
          <LiveMatchSection
            fixtureId={Number(fixtureId)}
            initialStatus="1H"
            homeTeam="Home"
            awayTeam="Away"
          />
        );
      case 'not_predictable':
        return (
          <MatchUnavailableSection
            status={result.fixtureStatus ?? undefined}
          />
        );
      case 'network':
        return <NetworkErrorState onRetry={onRetry} />;
      default:
        return <UnknownErrorState message={result.error.message} onRetry={onRetry} />;
    }
  }

  if (!result.prediction || !result.stage) {
    return null;
  }

  const completed = isCompleted(result.fixtureStatus ?? '');
  const title = result.homeTeam && result.awayTeam
    ? `${result.homeTeam} vs ${result.awayTeam} Prediction | FantasyFuel`
    : 'Match Prediction | FantasyFuel';

  return (
    <>
      <Helmet>
        <title>{title}</title>
        <meta property="og:title" content={title} />
        {result.homeTeam && result.awayTeam && (
          <meta property="og:description" content={`Win probability prediction for ${result.homeTeam} vs ${result.awayTeam} — FIFA World Cup 2026.`} />
        )}
      </Helmet>
      {completed && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
          <LiveBadge status={result.fixtureStatus!} />
        </Box>
      )}
      <WhyPanel
        prediction={result.prediction}
        reasoning={result.reasoning}
        upset={result.upset}
        stage={result.stage}
        partialAgent={result.partialAgent}
        homeTeam={result.homeTeam || 'Home'}
        awayTeam={result.awayTeam || 'Away'}
      />
      <HeadToHeadSection
        fixtures={h2h.fixtures}
        summary={h2h.summary}
        loading={h2h.loading}
        error={h2h.error}
        homeTeam={result.homeTeam || 'Home'}
        awayTeam={result.awayTeam || 'Away'}
      />
    </>
  );
};

export default MatchPage;
