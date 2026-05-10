import React from 'react';
import { AppBar, Tabs, Tab, Toolbar, Typography, Button, Box, IconButton, Menu, MenuItem } from '@mui/material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth, firebaseEnabled } from '../firebase';
import { signOut } from 'firebase/auth';
import LoginIcon from '@mui/icons-material/Login';
import LogoutIcon from '@mui/icons-material/Logout';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';

const AUTH_ENABLED = process.env.REACT_APP_AUTH_ENABLED === 'true';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { currentUser } = useAuth();
  const [footballAnchorEl, setFootballAnchorEl] = React.useState<null | HTMLElement>(null);

  const handleTabChange = (event: React.SyntheticEvent, newValue: string) => {
    if (newValue === '/football-menu') {
      setFootballAnchorEl(event.currentTarget as HTMLElement);
      return;
    }
    navigate(newValue);
  };

  const currentTab: string | false = location.pathname.startsWith('/football/')
    ? '/football-menu'
    : false;

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
        backgroundColor: 'rgba(13, 13, 13, 0.85)',
        backdropFilter: 'blur(8px)',
        borderBottom: '1px solid rgba(255, 152, 0, 0.3)',
        boxShadow: 'none',
        fontFamily: 'Orbitron, sans-serif',
      }}
    >
      <Toolbar
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: { xs: 1, sm: 0 },
          minHeight: { xs: 56, sm: 64 },
          py: 0,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Typography variant="h6" sx={{ color: 'white', mr: 2, fontFamily: 'Orbitron, sans-serif' }}>
            FantasyFuel
          </Typography>
          {showHomeButton && (
            <Button
              onClick={() => navigate('/')}
              sx={{
                textTransform: 'none',
                fontWeight: 600,
                color: '#b0bec5',
                fontFamily: 'Orbitron, sans-serif',
                fontSize: '0.8rem',
                minWidth: 'auto',
                px: 1,
                py: 0.5,
                background: 'none',
                boxShadow: 'none',
                borderRadius: 1,
                '&:hover': {
                  color: '#fff',
                  background: 'transparent',
                  boxShadow: 'none',
                  transform: 'none',
                },
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
                Football
                <ArrowDropDownIcon fontSize="small" />
              </Box>
            }
            value="/football-menu"
            sx={{ color: 'white' }}
          />
          {AUTH_ENABLED && (
            currentUser ? (
              <Tab label="Sign Out" onClick={handleSignOut} sx={{ color: 'white' }} />
            ) : (
              <Tab label="Sign In" value="/auth" sx={{ color: 'white' }} />
            )
          )}
        </Tabs>
        <Menu
          anchorEl={footballAnchorEl}
          open={Boolean(footballAnchorEl)}
          onClose={() => setFootballAnchorEl(null)}
        >
          <MenuItem
            onClick={() => {
              setFootballAnchorEl(null);
              navigate('/football/world-cup-2026');
            }}
          >
            World Cup 2026
          </MenuItem>
          <MenuItem
            onClick={() => {
              setFootballAnchorEl(null);
              navigate('/football/upsets');
            }}
          >
            Upsets
          </MenuItem>
        </Menu>

        <Box>
          {AUTH_ENABLED && (
            currentUser ? (
              <IconButton onClick={handleSignOut} sx={{ color: 'white' }}>
                <LogoutIcon />
              </IconButton>
            ) : (
              <IconButton onClick={() => navigate('/auth')} sx={{ color: 'white' }}>
                <LoginIcon />
              </IconButton>
            )
          )}
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
