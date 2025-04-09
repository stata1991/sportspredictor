import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#ff6f00', // Fantasy orange
    },
    secondary: {
      main: '#ec407a', // Vibrant pink
    },
    background: {
      default: 'linear-gradient(to bottom right, #0d0d0d, #1a1a1a)', // Sleek dark base
      paper: 'rgba(40, 40, 40, 0.95)', // Depth with subtle transparency
    },
    text: {
      primary: '#ffffff',
      secondary: '#b0bec5',
    },
    success: { main: '#4caf50' },
    warning: { main: '#ff9800' },
  },
  typography: {
    fontFamily: `'Orbitron', 'Roboto', sans-serif`, // Sporty + modern
    h4: {
      fontWeight: 800,
      color: '#ffe082',
      textShadow: '0 2px 5px rgba(255, 255, 255, 0.15)',
      letterSpacing: '1px',
    },
    h5: {
      fontWeight: 700,
      color: '#ffffff',
      letterSpacing: '0.5px',
    },
    button: {
      textTransform: 'uppercase',
      fontWeight: 800,
      letterSpacing: '1.5px',
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 30,
          padding: '12px 24px',
          fontSize: '1rem',
          background: 'linear-gradient(to right, #ff6f00, #ec407a)',
          color: '#fff',
          boxShadow: '0 0 12px rgba(255, 111, 0, 0.4)',
          transition: 'all 0.3s ease',
          '&:hover': {
            transform: 'scale(1.05)',
            boxShadow: '0 0 20px rgba(255, 111, 0, 0.6)',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 20,
          padding: '20px',
          background: 'linear-gradient(145deg, #1c1c1c, #292929)',
          boxShadow: '0 4px 20px rgba(255, 111, 0, 0.3)',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'linear-gradient(90deg, #ff6f00, #ec407a)',
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          transition: 'transform 0.3s ease, box-shadow 0.3s ease',
          '&:hover': {
            transform: 'scale(1.03)',
            boxShadow: '0 6px 20px rgba(255, 152, 0, 0.4)',
          },
        },
      },
    },
  },
});

export default theme;