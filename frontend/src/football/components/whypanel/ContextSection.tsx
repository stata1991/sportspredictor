import React from 'react';
import { Box, Typography, Chip } from '@mui/material';
import { Reasoning } from '../../types/prediction';
import { colors } from '../../colors';
import { sectionLabelSx, formatSource, proseFontSx } from './styles';

interface ContextSectionProps {
  reasoning: Reasoning;
}

const ContextSection: React.FC<ContextSectionProps> = ({ reasoning }) => {
  const { paragraphs, claims, validation_status } = reasoning;

  // De-dupe sources from the claims pool
  const uniqueSources = Array.from(
    new Set(claims.map((c) => c.source)),
  );

  return (
    <Box data-testid="context-section" sx={{ mt: 3 }}>
      <Typography variant="subtitle2" sx={sectionLabelSx}>
        Why
      </Typography>

      {/* Reasoning paragraphs — prose, not Orbitron */}
      <Box data-testid="reasoning-paragraphs">
        {paragraphs.map((text, i) => (
          <Typography
            key={i}
            data-testid={`paragraph-${i}`}
            sx={{
              ...proseFontSx,
              fontWeight: 400,
              fontSize: '0.9rem',
              lineHeight: 1.7,
              color: colors.textSecondary,
              mb: i < paragraphs.length - 1 ? '1.5rem' : 0,
            }}
          >
            {text}
          </Typography>
        ))}
      </Box>

      {/* Citation chips — de-duped, non-interactive */}
      {uniqueSources.length > 0 && (
        <Box
          data-testid="citation-chips"
          sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 2 }}
        >
          {uniqueSources.map((source) => (
            <Chip
              key={source}
              label={formatSource(source)}
              size="small"
              sx={{
                backgroundColor: 'rgba(255,255,255,0.06)',
                color: colors.neutral,
                fontWeight: 500,
                fontSize: '0.7rem',
                cursor: 'default',
                '&:hover': {
                  backgroundColor: 'rgba(255,255,255,0.06)',
                },
              }}
            />
          ))}
        </Box>
      )}

      {/* Validation disclosure */}
      {validation_status !== 'valid' && (
        <Typography
          data-testid="validation-disclosure"
          variant="caption"
          sx={{
            display: 'block',
            mt: 1.5,
            color: colors.neutral,
            fontSize: '0.7rem',
          }}
        >
          Some claims could not be verified.
        </Typography>
      )}
    </Box>
  );
};

export default ContextSection;
