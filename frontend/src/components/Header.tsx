import React from 'react';
import { AppBar, Tabs, Tab, Toolbar, Typography, Button, Box, IconButton, Menu, MenuItem } from '@mui/material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth, firebaseEnabled } from '../firebase';
import { signOut } from 'firebase/auth';
import LoginIcon from '@mui/icons-material/Login';
import LogoutIcon from '@mui/icons-material/Logout';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser } = useAuth();
  const [cricketAnchorEl, setCricketAnchorEl] = React.useState<null | HTMLElement>(null);

  const handleTabChange = (event: React.SyntheticEvent, newValue: string) => {
    if (newValue === '/cricket-menu') {
      setCricketAnchorEl(event.currentTarget as HTMLElement);
      return;
    }
    navigate(newValue);
  };

  const currentTab = location.pathname.startsWith('/live')
    ? '/live'
    : location.pathname.startsWith('/cricket/')
    ? '/cricket-menu'
    : '/';

  const handleSignOut = async () => {
    try {
      if (!firebaseEnabled || !auth) {
        navigate('/');
        return;
      }
      await signOut(auth);
      navigate('/');
    } catch (error) {
      console.error('Error signing out:', error);
    }
  };

  const showHomeButton = location.pathname !== '/';

  return (
    <AppBar
      position="static"
      sx={{
        backgroundColor: 'rgba(0,0,0,0.7)',
        boxShadow: 'none',
        fontFamily: 'Orbitron, sans-serif',
      }}
    >
      <Toolbar
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',  // Added for responsive fix
          gap: { xs: 1, sm: 0 }, // Responsive spacing
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Typography variant="h6" sx={{ color: 'white', mr: 2, fontFamily: 'Orbitron, sans-serif' }}>
            Fantasy Prediction Hub
          </Typography>
          {showHomeButton && (
            <Button
              onClick={() => navigate('/')}
              sx={{
                textTransform: 'none',
                fontWeight: 'bold',
                color: 'white',
                fontFamily: 'Orbitron, sans-serif',
              }}
            >
              Home
            </Button>
          )}
        </Box>

        <Tabs
          value={currentTab}
          onChange={handleTabChange}
          textColor="inherit"
          indicatorColor="secondary"
          sx={{
            color: 'white',
            overflowX: 'auto', // Added for responsive fix
            maxWidth: '100%',  // Added for responsive fix
          }}
        >
          <Tab
            label={
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                Cricket
                <ArrowDropDownIcon fontSize="small" />
              </Box>
            }
            value="/cricket-menu"
            sx={{ color: 'white' }}
          />
          <Tab label="Live Predictions" value="/live" sx={{ color: 'white' }} />
          {currentUser ? (
            <Tab label="Sign Out" onClick={handleSignOut} sx={{ color: 'white' }} />
          ) : (
            <Tab label="Sign In" value="/auth" sx={{ color: 'white' }} />
          )}
        </Tabs>
        <Menu
          anchorEl={cricketAnchorEl}
          open={Boolean(cricketAnchorEl)}
          onClose={() => setCricketAnchorEl(null)}
        >
          <MenuItem
            onClick={() => {
              setCricketAnchorEl(null);
              navigate('/cricket/ipl');
            }}
          >
            IPL
          </MenuItem>
          <MenuItem
            onClick={() => {
              setCricketAnchorEl(null);
              navigate('/cricket/t20-world-cup');
            }}
          >
            T20 World Cup
          </MenuItem>
        </Menu>

        <Box>
          {currentUser ? (
            <IconButton onClick={handleSignOut} sx={{ color: 'white' }}>
              <LogoutIcon />
            </IconButton>
          ) : (
            <IconButton onClick={() => navigate('/auth')} sx={{ color: 'white' }}>
              <LoginIcon />
            </IconButton>
          )}
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
