import React from 'react';
import { Box, Chip } from '@mui/material';
import { colors } from '../colors';

interface RoundSelectorProps {
  rounds: string[];
  selected: string;
  onChange: (round: string) => void;
  /** Optional display transform for chip labels (e.g. round → short label).
   *  Selection/keys stay in the raw `rounds` space. Defaults to identity. */
  renderLabel?: (round: string) => string;
}

const RoundSelector: React.FC<RoundSelectorProps> = ({
  rounds,
  selected,
  onChange,
  renderLabel,
}) => (
  <Box
    data-testid="round-selector"
    sx={{
      display: 'flex',
      flexWrap: 'nowrap',
      gap: 1,
      overflowX: 'auto',
      overflowY: 'hidden',
      pb: 1,
      mb: 1.5,
      touchAction: 'pan-x',
      WebkitOverflowScrolling: 'touch',
      scrollbarWidth: 'none',
      '&::-webkit-scrollbar': { display: 'none' },
    }}
  >
    {rounds.map((round) => {
      const isSelected = round === selected;
      return (
        <Chip
          key={round}
          label={renderLabel ? renderLabel(round) : round}
          data-testid="round-chip"
          onClick={() => onChange(round)}
          variant={isSelected ? 'filled' : 'outlined'}
          sx={{
            flexShrink: 0,
            fontWeight: isSelected ? 700 : 400,
            fontSize: '0.8rem',
            color: isSelected ? '#fff' : colors.labelText,
            backgroundColor: isSelected ? colors.homeAccent : 'transparent',
            borderColor: isSelected ? colors.homeAccent : 'rgba(255,255,255,0.15)',
            '&:hover': {
              backgroundColor: isSelected
                ? colors.homeAccent
                : 'rgba(255,111,0,0.12)',
            },
          }}
        />
      );
    })}
  </Box>
);

export default RoundSelector;
