import React from "react";
import { Button, Stack, Typography } from "@mui/material";
import SportsCricketIcon from '@mui/icons-material/SportsCricket';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import ScoreboardIcon from '@mui/icons-material/Scoreboard';
import WbSunnyIcon from '@mui/icons-material/WbSunny';

type PredictionButtonsProps = {
  title: string;
  onWinnerClick: () => void;
  onPowerplayClick: () => void;
  onScoreClick: () => void;
  onWicketsClick: () => void;
};

const PredictionButtons: React.FC<PredictionButtonsProps> = ({
  title,
  onWinnerClick,
  onPowerplayClick,
  onScoreClick,
  onWicketsClick,
}) => {
  return (
    <div>
      <Typography variant="h5" gutterBottom sx={{ textTransform: 'uppercase', letterSpacing: '2px' }}>
        {title}
      </Typography>

      <Stack spacing={2} direction="row" sx={{ flexWrap: "wrap", justifyContent: "center" }}>
        <Button
          variant="contained"
          color="primary"
          startIcon={<SportsCricketIcon />}
          onClick={onWinnerClick}
          sx={{
            minWidth: { xs: '120px', sm: '150px' },  // Responsive fix
            fontSize: { xs: '0.75rem', sm: '1rem' }, // Responsive fix
            px: 2,  // Responsive padding
            py: 1.5, // Responsive padding
          }}
        >
          Predict Winner
        </Button>

        <Button
          variant="contained"
          color="secondary"
          startIcon={<FlashOnIcon />}
          onClick={onPowerplayClick}
          sx={{
            minWidth: { xs: '120px', sm: '150px' },
            fontSize: { xs: '0.75rem', sm: '1rem' },
            px: 2,
            py: 1.5,
          }}
        >
          Powerplay
        </Button>

        <Button
          variant="contained"
          color="success"
          startIcon={<ScoreboardIcon />}
          onClick={onScoreClick}
          sx={{
            minWidth: { xs: '120px', sm: '150px' },
            fontSize: { xs: '0.75rem', sm: '1rem' },
            px: 2,
            py: 1.5,
          }}
        >
          Total Score
        </Button>

        <Button
          variant="contained"
          color="warning"
          startIcon={<WbSunnyIcon />}
          onClick={onWicketsClick}
          sx={{
            minWidth: { xs: '120px', sm: '150px' },
            fontSize: { xs: '0.75rem', sm: '1rem' },
            px: 2,
            py: 1.5,
          }}
        >
          Wickets
        </Button>
      </Stack>
    </div>
  );
};

export default PredictionButtons;
