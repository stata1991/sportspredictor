import React from 'react';
import { Box, Tooltip } from '@mui/material';

type Props = {
  confidence: number;
  components?: Record<string, number>;
};

const ConfidenceBadge: React.FC<Props> = ({ confidence, components }) => {
  const label =
    confidence >= 0.7 ? 'High confidence' :
    confidence >= 0.55 ? 'Moderate confidence' :
    'Early estimate';
  const color =
    confidence >= 0.7 ? '#22c55e' :
    confidence >= 0.55 ? '#f59e0b' :
    '#94a3b8';

  const tooltipContent = components ? (
    <Box sx={{ fontSize: 11 }}>
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{Math.round(confidence * 100)}% confidence</div>
      {Object.entries(components).map(([key, val]) => (
        <div key={key}>{key}: {typeof val === 'number' ? val.toFixed(2) : String(val)}</div>
      ))}
    </Box>
  ) : `${Math.round(confidence * 100)}%`;

  return (
    <Tooltip title={tooltipContent} arrow placement="right">
      <Box
        component="span"
        sx={{
          display: 'inline-block',
          px: 1,
          py: 0.25,
          borderRadius: 1,
          backgroundColor: `${color}22`,
          border: `1px solid ${color}`,
          color,
          fontSize: 11,
          fontWeight: 700,
          cursor: 'help',
        }}
      >
        {label}
      </Box>
    </Tooltip>
  );
};

export default ConfidenceBadge;
