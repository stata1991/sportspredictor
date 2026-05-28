import React from 'react';
import { Box, Chip } from '@mui/material';
import { colors } from '../colors';

interface RoundSelectorProps {
  rounds: string[];
  selected: string;
  onChange: (round: string) => void;
}

const RoundSelector: React.FC<RoundSelectorProps> = ({ rounds, selected, onChange }) => (
  <Box
    data-testid="round-selector"
    sx={{
      display: 'flex',
      gap: 1,
      overflowX: 'auto',
      pb: 1,
      mb: 1.5,
      scrollbarWidth: 'thin',
      '&::-webkit-scrollbar': { height: 4 },
      '&::-webkit-scrollbar-thumb': {
        backgroundColor: 'rgba(255,255,255,0.15)',
        borderRadius: 2,
      },
    }}
  >
    {rounds.map((round) => {
      const isSelected = round === selected;
      return (
        <Chip
          key={round}
          label={round}
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
