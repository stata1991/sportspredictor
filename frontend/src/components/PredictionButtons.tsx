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
          sx={{ minWidth: '150px' }}
        >
          Predict Winner
        </Button>
        <Button
          variant="contained"
          color="secondary"
          startIcon={<FlashOnIcon />}
          onClick={onPowerplayClick}
          sx={{ minWidth: '150px' }}
        >
          Powerplay
        </Button>
        <Button
          variant="contained"
          color="success"
          startIcon={<ScoreboardIcon />}
          onClick={onScoreClick}
          sx={{ minWidth: '150px' }}
        >
          Total Score
        </Button>
        <Button
          variant="contained"
          color="warning"
          startIcon={<WbSunnyIcon />}
          onClick={onWicketsClick}
          sx={{ minWidth: '150px' }}
        >
          Wickets
        </Button>
      </Stack>
    </div>
  );
};

export default PredictionButtons;