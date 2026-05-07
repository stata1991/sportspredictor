import React, { useState, useCallback } from 'react';
import { Box, Typography } from '@mui/material';
import IosShareIcon from '@mui/icons-material/IosShare';
import { Upset } from '../../types/prediction';
import { formatPercent } from '../../utils/probability';
import { colors } from '../../colors';
import { sectionLabelSx, proseFontSx } from './styles';

interface UpsetSectionProps {
  upset: Upset;
  favouriteProbability: number;
  favouriteTeam: string;
  underdogName: string;
}

const UpsetSection: React.FC<UpsetSectionProps> = ({
  upset,
  favouriteProbability,
  favouriteTeam,
  underdogName,
}) => {
  const [copied, setCopied] = useState(false);

  const handleShare = useCallback(async () => {
    const url = window.location.href;
    const title = `Three paths to a ${favouriteTeam} upset — FantasyFuel`;
    const text = `Can ${underdogName} pull off the upset? See three ways ${favouriteTeam} could lose.`;

    if (navigator.share) {
      try {
        await navigator.share({ title, url, text });
        return;
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          return;
        }
        // Non-AbortError: fall through to clipboard
      }
    }

    // Desktop fallback (or share-API error fallback): copy to clipboard
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [favouriteTeam, underdogName]);

  // Gate: only render when there's a clear favourite above 0.65 with paths
  if (favouriteProbability <= 0.65 || upset.upset_paths.length === 0) {
    return null;
  }

  const meterColor = upset.upset_index >= 0.4 ? colors.awayAccent : colors.neutral;

  return (
    <Box
      data-testid="upset-section"
      sx={{
        mt: 3,
        backgroundColor: 'rgba(0,0,0,0.25)',
        borderRadius: 3,
        p: 3,
      }}
    >
      {/* Header row: label + upset meter */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mb: 0.5 }}>
        <Typography variant="subtitle2" sx={{ ...sectionLabelSx, mb: 0 }}>
          What if we&apos;re wrong
        </Typography>
        <Typography
          data-testid="upset-meter"
          variant="caption"
          sx={{ color: meterColor, fontWeight: 600, fontSize: '0.75rem' }}
        >
          Upset risk: {formatPercent(upset.upset_index, 1)}
        </Typography>
      </Box>

      {/* Pull-quote heading */}
      <Typography
        data-testid="upset-heading"
        sx={{
          ...proseFontSx,
          fontSize: '1.25rem',
          fontWeight: 600,
          color: colors.textPrimary,
          mb: '1.5rem',
          lineHeight: 1.3,
        }}
      >
        Three paths to {favouriteTeam} losing this.
      </Typography>

      {/* Scenario cards */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {upset.upset_paths.map((path, i) => (
          <Box
            key={i}
            data-testid={`upset-path-${i}`}
            sx={{ display: 'flex', gap: 2 }}
          >
            <Typography
              sx={{
                fontSize: '3rem',
                fontWeight: 700,
                color: 'text.secondary',
                lineHeight: 1,
                minWidth: '2.5rem',
                userSelect: 'none',
              }}
            >
              {i + 1}
            </Typography>
            <Typography
              sx={{
                ...proseFontSx,
                fontWeight: 400,
                fontSize: '0.9rem',
                lineHeight: 1.6,
                color: colors.textSecondary,
                pt: 0.5,
              }}
            >
              {path}
            </Typography>
          </Box>
        ))}
      </Box>

      {/* Share button — raw <button> to bypass MuiButton global gradient */}
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
        <Box
          component="button"
          data-testid="share-button"
          onClick={handleShare}
          sx={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 0.5,
            border: '1px solid rgba(236, 64, 122, 0.4)',
            borderRadius: 2,
            background: 'transparent',
            color: colors.awayAccent,
            textTransform: 'none',
            fontSize: '0.8rem',
            padding: '4px 10px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            fontFamily: 'inherit',
            '&:hover': {
              borderColor: 'rgba(236, 64, 122, 0.6)',
              backgroundColor: 'rgba(236, 64, 122, 0.08)',
            },
            '&:focus-visible': {
              outline: `2px solid ${colors.awayAccent}`,
              outlineOffset: '2px',
            },
          }}
        >
          <IosShareIcon sx={{ fontSize: '1rem' }} />
          {copied ? 'Link copied' : 'Share'}
        </Box>
      </Box>
    </Box>
  );
};

export default UpsetSection;
