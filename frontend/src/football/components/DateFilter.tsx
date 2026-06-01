import React from 'react';
import { Box, Chip } from '@mui/material';
import { formatDateChip } from '../utils/roundGrouping';
import { colors } from '../colors';

interface DateFilterProps {
  dates: string[];
  selected: string; // 'all' or a YYYY-MM-DD key
  onChange: (dateKey: string) => void;
}

const DateFilter: React.FC<DateFilterProps> = ({ dates, selected, onChange }) => (
  <Box
    data-testid="date-filter"
    sx={{
      display: 'flex',
      flexWrap: 'nowrap',
      gap: 0.75,
      overflowX: 'auto',
      overflowY: 'hidden',
      pb: 1,
      mb: 2,
      touchAction: 'pan-x',
      WebkitOverflowScrolling: 'touch',
      scrollbarWidth: 'none',
      '&::-webkit-scrollbar': { display: 'none' },
    }}
  >
    <Chip
      label="All"
      data-testid="date-chip"
      size="small"
      onClick={() => onChange('all')}
      variant={selected === 'all' ? 'filled' : 'outlined'}
      sx={{
        flexShrink: 0,
        fontSize: '0.75rem',
        fontWeight: selected === 'all' ? 700 : 400,
        color: selected === 'all' ? '#fff' : colors.labelText,
        backgroundColor: selected === 'all' ? 'rgba(255,111,0,0.7)' : 'transparent',
        borderColor: selected === 'all' ? 'rgba(255,111,0,0.7)' : 'rgba(255,255,255,0.12)',
        '&:hover': {
          backgroundColor: selected === 'all'
            ? 'rgba(255,111,0,0.7)'
            : 'rgba(255,111,0,0.1)',
        },
      }}
    />
    {dates.map((dateKey) => {
      const isSelected = dateKey === selected;
      return (
        <Chip
          key={dateKey}
          label={formatDateChip(dateKey)}
          data-testid="date-chip"
          size="small"
          onClick={() => onChange(dateKey)}
          variant={isSelected ? 'filled' : 'outlined'}
          sx={{
            flexShrink: 0,
            fontSize: '0.75rem',
            fontWeight: isSelected ? 700 : 400,
            color: isSelected ? '#fff' : colors.labelText,
            backgroundColor: isSelected ? 'rgba(255,111,0,0.7)' : 'transparent',
            borderColor: isSelected ? 'rgba(255,111,0,0.7)' : 'rgba(255,255,255,0.12)',
            '&:hover': {
              backgroundColor: isSelected
                ? 'rgba(255,111,0,0.7)'
                : 'rgba(255,111,0,0.1)',
            },
          }}
        />
      );
    })}
  </Box>
);

export default DateFilter;
