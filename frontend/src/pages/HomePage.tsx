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
  Divider
} from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";
import homeBg from '../home.png'; // adjust if path is different

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedSport, setSelectedSport] = useState("");

  const handleCardClick = (sport: string, event: React.MouseEvent) => {
    if (sport === "Cricket") {
      setAnchorEl(event.currentTarget as HTMLElement);
    } else {
      setSelectedSport(sport);
      setDialogOpen(true);
    }
  };

  const handleCricketOptionClick = (option: string) => {
    if (option === "IPL") {
      navigate("/cricket/ipl");
    }
    setAnchorEl(null);
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
        overflowX: "hidden", // Added for responsive fix
      }}
    >
      {/* Top right Sign In */}
      <Box sx={{ position: "absolute", top: 16, right: 16 }}>
        <IconButton onClick={handleSignInClick} sx={{ color: "white" }}>
          <LoginIcon />
        </IconButton>
      </Box>

      {/* Clickable sport zones */}
      <Box
        sx={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -20%)",
          display: "flex",
          flexDirection: { xs: "column", sm: "row" },  // Responsive
          gap: { xs: "1rem", sm: "2rem" },              // Responsive
          alignItems: "center",
        }}
      >

        {/* Each Card — Responsive Fix */}
        {["Soccer", "NFL", "NBA", "Cricket"].map((sport) => (
          <Box
            key={sport}
            sx={{
              width: '100%',  // Full width of parent
              maxWidth: { xs: '70px', sm: '100px', md: '140px' }, // Responsive card size
              height: { xs: '90px', sm: '110px', md: '140px' },   // Responsive card height
              cursor: "pointer",
            }}
            onClick={(e) => handleCardClick(sport, e)}
          />
        ))}

      </Box>

      {/* Cricket dropdown */}
      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
      >
        <MenuItem onClick={() => handleCricketOptionClick("IPL")}>IPL</MenuItem>
      </Menu>

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
      <Box sx={{
        position: "absolute",
        bottom: 0,
        width: "100%",
        textAlign: "center",
        p: { xs: 1, sm: 2 },
        backgroundColor: "rgba(0,0,0,0.6)"
      }}>
        <Divider />
        <Typography variant="body2" color="white" mt={1}>
          ⚠️ FantasyFuel.ai is intended for entertainment and informational purposes only.
          Predictions should not be used for betting or gambling.
        </Typography>
      </Box>
    </Box>
  );
};

export default HomePage;
