import React, { useState } from 'react';
import { Box, Typography } from '@mui/material';
import { colors } from '../../colors';
import { formatPercent } from '../../utils/probability';
import { sectionLabelSx } from './styles';

// ── Props ───────────────────────────────────────────────────────────

interface ScorelineHeatmapProps {
  matrix: number[][];   // 8×8 from prediction.winner.scoreline_matrix
  homeTeam: string;
  awayTeam: string;
}

// ── Constants ───────────────────────────────────────────────────────

/** Display grid covers goals 0–5 each side (6×6).
 *  Rows 6–7 of the 8×8 Dixon-Coles matrix are discarded — they hold
 *  <0.1% of total probability mass and would add 33% more cells for
 *  data that rounds to 0% everywhere. */
const DISPLAY_SIZE = 6;

const AXIS_NUMBERS = Array.from({ length: DISPLAY_SIZE }, (_, i) => i);

// ── Helpers ─────────────────────────────────────────────────────────

function findMaxCell(grid: number[][]): { row: number; col: number; value: number } {
  let maxRow = 0;
  let maxCol = 0;
  let maxVal = -1;
  for (let r = 0; r < grid.length; r++) {
    for (let c = 0; c < grid[r].length; c++) {
      if (grid[r][c] > maxVal) {
        maxVal = grid[r][c];
        maxRow = r;
        maxCol = c;
      }
    }
  }
  return { row: maxRow, col: maxCol, value: maxVal };
}

const axisLabelSx = {
  color: colors.labelText,
  fontSize: '0.65rem',
  fontWeight: 600,
};

// ── Component ───────────────────────────────────────────────────────

const ScorelineHeatmap: React.FC<ScorelineHeatmapProps> = ({
  matrix,
  homeTeam,
  awayTeam,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const sliced = matrix.slice(0, DISPLAY_SIZE).map((row) => row.slice(0, DISPLAY_SIZE));
  const max = findMaxCell(sliced);

  const cellBg = (value: number): string =>
    value > 0
      ? `rgba(236, 64, 122, ${(value / max.value) * 0.85})`
      : 'transparent';

  return (
    <Box data-testid="scoreline-heatmap">
      {/* Toggle button */}
      <Box
        component="button"
        data-testid="heatmap-toggle"
        aria-expanded={isExpanded}
        aria-controls="heatmap-content"
        onClick={() => setIsExpanded((v) => !v)}
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.5,
          border: 'none',
          background: 'transparent',
          color: colors.labelText,
          textTransform: 'none',
          fontSize: '0.75rem',
          fontWeight: 600,
          padding: '4px 0',
          cursor: 'pointer',
          fontFamily: 'inherit',
          '&:hover': { color: colors.awayAccent },
          '&:focus': { outline: 'none' },
          '&:focus-visible': {
            outline: `2px solid ${colors.awayAccent}`,
            outlineOffset: '2px',
          },
        }}
      >
        {isExpanded ? '▾' : '▸'} Full-time scorelines
      </Box>

      {/* Collapsible heatmap content */}
      {isExpanded && (
        <Box id="heatmap-content" sx={{ mt: 1.5 }}>
          <Typography variant="subtitle2" sx={sectionLabelSx}>
            FT Scoreline Map
          </Typography>

          {/* Away team label — mirrored grid so it aligns with column 0 */}
          <Box sx={{ display: 'grid', gridTemplateColumns: 'auto 1fr', mb: 0.25 }}>
            <Box sx={{ width: 28 }} />
            <Typography
              sx={{
                color: colors.labelText,
                fontSize: '0.7rem',
                fontWeight: 600,
              }}
            >
              {awayTeam} →
            </Typography>
          </Box>

          {/* Grid + right-side home label */}
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {/* Grid */}
            <Box
              data-testid="heatmap-grid"
              sx={{
                display: 'grid',
                gridTemplateColumns: 'auto repeat(6, minmax(40px, 56px))',
                gap: '1px',
                flex: 1,
              }}
            >
              {/* Column header row: empty corner + 0–5 */}
              <Box />
              {AXIS_NUMBERS.map((n) => (
                <Box
                  key={`col-${n}`}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: 20,
                  }}
                >
                  <Typography sx={axisLabelSx}>
                    {n}
                  </Typography>
                </Box>
              ))}

              {/* Data rows */}
              {sliced.map((row, r) => (
                <React.Fragment key={`row-${r}`}>
                  {/* Row label */}
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 28,
                    }}
                  >
                    <Typography sx={axisLabelSx}>
                      {r}
                    </Typography>
                  </Box>

                  {/* Data cells */}
                  {row.map((value, c) => {
                    const isMax = r === max.row && c === max.col;
                    return (
                      <Box
                        key={`cell-${r}-${c}`}
                        data-testid={`heatmap-cell-${r}-${c}`}
                        data-cell="true"
                        {...(isMax && { 'data-max': 'true' })}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          minHeight: 32,
                          borderRadius: 0.5,
                          backgroundColor: cellBg(value),
                          boxSizing: 'border-box',
                          ...(isMax && {
                            border: `2px solid ${colors.homeAccent}`,
                          }),
                        }}
                      >
                        {value >= 0.01 && (
                          <Typography
                            sx={{
                              color: colors.textPrimary,
                              fontSize: '0.65rem',
                              fontWeight: isMax ? 800 : 600,
                              lineHeight: 1,
                            }}
                          >
                            {formatPercent(value)}
                          </Typography>
                        )}
                      </Box>
                    );
                  })}
                </React.Fragment>
              ))}
            </Box>

            {/* Home team label along right edge */}
            <Typography
              sx={{
                color: colors.labelText,
                fontSize: '0.7rem',
                fontWeight: 600,
                writingMode: 'vertical-rl',
                textOrientation: 'mixed',
                ml: 0.75,
                whiteSpace: 'nowrap',
              }}
            >
              ↑ {homeTeam} ↓
            </Typography>
          </Box>

          {/* Legend */}
          <Typography
            data-testid="heatmap-legend"
            sx={{
              color: colors.labelText,
              fontSize: '0.65rem',
              mt: 1,
            }}
          >
            — = &lt;1%{'   '}
            <Box
              component="span"
              sx={{ color: colors.homeAccent, fontWeight: 700 }}
            >
              ■
            </Box>
            {' '}most likely ({max.row}–{max.col}, {formatPercent(max.value)})
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default ScorelineHeatmap;
