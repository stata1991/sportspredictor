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

  const handleCardClick = (sport: string, event: React.MouseEvent<HTMLElement>) => {
    if (sport === "Cricket") {
      setAnchorEl(event.currentTarget);
      return;
    }
    setSelectedSport(sport);
    setDialogOpen(true);
  };

  return (
    <Box
      sx={{
        position: "relative",
        minHeight: "100vh",
        backgroundImage: `linear-gradient(rgba(13,17,23,0.88), rgba(13,17,23,0.88)), url(${homeBg})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        color: "white",
        overflow: "hidden",
      }}
    >
      <Box sx={{ position: "absolute", top: 16, right: 16 }}>
        <IconButton onClick={() => navigate("/auth")} sx={{ color: "white" }}>
          <LoginIcon />
        </IconButton>
      </Box>

      <Box sx={{ textAlign: "center", pt: { xs: 8, sm: 12 }, px: 2 }}>
        <Typography
          variant="h4"
          sx={{ fontWeight: 700, mb: 1, fontFamily: "Orbitron, sans-serif" }}
        >
          FantasyFuel.ai
        </Typography>
        <Typography variant="subtitle1" sx={{ color: "#94a3b8" }}>
          Live fantasy predictions across match moments.
        </Typography>
      </Box>

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
              backgroundColor: "rgba(15,23,42,0.92)",
              borderRadius: "12px",
              border: "1px solid #334155",
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
                objectFit: "contain",
              }}
            />
          </Box>
        ))}
      </Box>

      <Menu
        anchorEl={anchorEl}
        open={Boolean(anchorEl)}
        onClose={() => setAnchorEl(null)}
      >
        <MenuItem
          onClick={() => {
            setAnchorEl(null);
            navigate("/cricket/ipl");
          }}
        >
          IPL
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchorEl(null);
            navigate("/cricket/t20-world-cup");
          }}
        >
          T20 World Cup
        </MenuItem>
      </Menu>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)}>
        <DialogTitle>{selectedSport} - Coming Soon</DialogTitle>
        <DialogContent>
          <DialogContentText>
            We are building {selectedSport} predictions next.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>OK</Button>
        </DialogActions>
      </Dialog>

      <Box
        sx={{
          position: "absolute",
          bottom: 0,
          width: "100%",
          textAlign: "center",
          p: { xs: 1, sm: 2 },
          backgroundColor: "rgba(2,6,23,0.92)",
          borderTop: "1px solid #334155",
        }}
      >
        <Divider />
        <Typography variant="body2" color="#94a3b8" mt={1}>
          Entertainment only. Do not use for betting or gambling.
        </Typography>
      </Box>
    </Box>
  );
};

export default HomePage;
