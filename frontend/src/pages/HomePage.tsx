import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Menu,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
  IconButton,
  Typography,
  Divider,
} from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";

// Import images
import homeBg from "../non-home.png";
import soccerIcon from "../soccer.png";
import nflIcon from "../nfl.png";
import nbaIcon from "../nba.png";
import cricketIcon from "../cricket.png";

const sportsData = [
  { name: "Soccer", icon: soccerIcon },
  { name: "NFL", icon: nflIcon },
  { name: "NBA", icon: nbaIcon },
  { name: "Cricket", icon: cricketIcon },
];

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedSport, setSelectedSport] = useState("");

  const handleCardClick = (sport: string, event: React.MouseEvent) => {
    if (sport === "Cricket") {
      setAnchorEl(event.currentTarget as HTMLElement);
      navigate("/cricket/ipl");
    } else {
      setSelectedSport(sport);
      setDialogOpen(true);
    }
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
  };

  const handleSignInClick = () => {
    navigate("/auth");
  };

  return (
    <Box
      sx={{
        position: "relative",
        minHeight: "100vh",
        backgroundImage: `url(${homeBg})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        color: "white",
        overflow: "hidden",
      }}
    >
      {/* Top Right Sign In */}
      <Box sx={{ position: "absolute", top: 16, right: 16 }}>
        <IconButton onClick={handleSignInClick} sx={{ color: "white" }}>
          <LoginIcon />
        </IconButton>
      </Box>

      {/* Title and Subtitle */}
      <Box
        sx={{
          textAlign: "center",
          pt: { xs: 8, sm: 12 },
        }}
      >
        <Typography
          variant="h4"
          sx={{ fontWeight: "bold", mb: 1, fontFamily: "Orbitron, sans-serif" }}
        >
          Welcome to FantasyFuel.ai
        </Typography>
        <Typography variant="subtitle1">
          Fuel your fantasy sports predictions!
        </Typography>
      </Box>

      {/* Clickable Sports Cards */}
      <Box
        sx={{
          mt: { xs: 6, sm: 10 },
          display: "flex",
          flexDirection: { xs: "column", sm: "row" },
          justifyContent: "center",
          alignItems: "center",
          gap: { xs: 3, sm: 5 },
          px: { xs: 2, sm: 0 },
          mb: { xs: 10, sm: 0 },
        }}
      >
        {sportsData.map((sport) => (
          <Box
            key={sport.name}
            onClick={(e) => handleCardClick(sport.name, e)}
            sx={{
              backgroundColor: "rgba(0,0,0,0.7)",
              borderRadius: "12px",
              boxShadow: "0px 4px 10px rgba(0,0,0,0.5)",
              width: { xs: "120px", sm: "140px", md: "160px" },
              height: { xs: "140px", sm: "160px", md: "180px" },
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              transition: "transform 0.2s",
              "&:hover": {
                transform: "scale(1.05)",
              },
            }}
          >
            <img
  src={sport.icon}
  alt={sport.name}
  style={{ 
    width: "100%",   
    height: "100%", 
    objectFit: "contain"
  }}
/>

          </Box>
        ))}
      </Box>

      {/* Coming Soon Dialog */}
      <Dialog open={dialogOpen} onClose={handleDialogClose}>
        <DialogTitle>{selectedSport} - Coming Soon!</DialogTitle>
        <DialogContent>
          <DialogContentText>
            We’re working on {selectedSport} predictions. Stay tuned!
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDialogClose}>OK</Button>
        </DialogActions>
      </Dialog>

      {/* Disclaimer */}
      <Box
        sx={{
          position: "absolute",
          bottom: 0,
          width: "100%",
          textAlign: "center",
          p: { xs: 1, sm: 2 },
          backgroundColor: "rgba(0,0,0,0.6)",
        }}
      >
        <Divider />
        <Typography variant="body2" color="white" mt={1}>
          ⚠️ FantasyFuel.ai is intended for entertainment and informational
          purposes only. Predictions should not be used for betting or gambling.
        </Typography>
      </Box>
    </Box>
  );
};

export default HomePage;
