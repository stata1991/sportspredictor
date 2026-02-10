import React from "react";
import { Box, Typography, Divider } from "@mui/material";
import homeBg from "../non-home.png";

const T20WorldCupPage: React.FC = () => {
  return (
    <Box
      sx={{
        minHeight: "100vh",
        backgroundImage: `linear-gradient(rgba(13,17,23,0.92), rgba(13,17,23,0.92)), url(${homeBg})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        color: "white",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        px: 2,
        textAlign: "center",
      }}
    >
      <Typography variant="h3" sx={{ fontFamily: "Orbitron, sans-serif", fontWeight: 700, mb: 1 }}>
        T20 World Cup
      </Typography>
      <Typography sx={{ color: "#94a3b8", maxWidth: 580 }}>
        This lane is now added under Cricket. Decision flows for this league are coming next.
      </Typography>
      <Box sx={{ mt: 4, width: "100%", maxWidth: 640 }}>
        <Divider sx={{ borderColor: "#334155" }} />
      </Box>
    </Box>
  );
};

export default T20WorldCupPage;
