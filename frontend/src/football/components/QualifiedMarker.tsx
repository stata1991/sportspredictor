import React from 'react';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { colors } from '../colors';

/**
 * Orange check marker for a qualified team row in the frozen (post-group-
 * stage) standings. Uses the locked home accent — deliberately NOT green —
 * and stays compact so it remains legible at 320px.
 */
const QualifiedMarker: React.FC = () => (
  <CheckCircleIcon
    data-testid="qualified-marker"
    aria-label="Qualified"
    sx={{
      fontSize: '0.85rem',
      color: colors.homeAccent,
      verticalAlign: 'middle',
      ml: 0.5,
    }}
  />
);

export default QualifiedMarker;
