import React, { useState } from 'react';
import {
  Box,
  Button,
  TextField,
  Typography,
  Divider,
  Paper,
  Container,
  Stack
} from '@mui/material';
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider
} from 'firebase/auth';
import { auth } from '../firebase';
import { useNavigate } from 'react-router-dom';

const AuthPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const navigate = useNavigate();

  const handleEmailAuth = async () => {
    setError('');
    try {
      if (isSignUp) {
        await createUserWithEmailAndPassword(auth, email, password);
      } else {
        await signInWithEmailAndPassword(auth, email, password);
      }
      navigate('/live');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleGoogleSignIn = async () => {
    setError('');
    try {
      const provider = new GoogleAuthProvider();
      await signInWithPopup(auth, provider);
      navigate('/live');
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <Container maxWidth="sm" sx={{ mt: 8, px: { xs: 1, sm: 2 } }}> {/* Added responsive padding */}
      <Paper
        elevation={10}
        sx={{
          p: { xs: 2, sm: 4 },  // Added for responsive padding
          borderRadius: 4,
          background: 'linear-gradient(145deg, #0f2027, #203a43, #2c5364)',
          color: 'white',
          boxShadow: '0 0 20px #FFD70088',
          fontFamily: 'Orbitron, sans-serif',
        }}
      >
        <Typography
          variant="h4"
          align="center"
          gutterBottom
          sx={{
            fontWeight: 'bold',
            fontSize: { xs: '1.8rem', sm: '2.5rem', md: '3rem' }, // Added responsive font size
            color: '#FFD700',
            fontFamily: 'Orbitron, sans-serif',
          }}
        >
          {isSignUp ? 'Create Your Account' : 'Welcome Back'}
        </Typography>

        <Stack spacing={2} mt={3}>
          <TextField
            label="Email"
            type="email"
            variant="outlined"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            fullWidth
          />
          <TextField
            label="Password"
            type="password"
            variant="outlined"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            fullWidth
          />
        </Stack>

        {error && (
          <Typography color="error" sx={{ mt: 2 }} align="center">
            {error}
          </Typography>
        )}

        <Stack spacing={2} mt={4}>
          <Button
            variant="contained"
            color="primary"
            onClick={handleEmailAuth}
            fullWidth
            sx={{
              minWidth: { xs: '120px', sm: '150px' },  // Added for responsive button size
              fontSize: { xs: '0.8rem', sm: '1rem' },  // Added for responsive font size
              borderRadius: '30px',
              px: 4,
              py: 2,
              fontFamily: 'Orbitron, sans-serif',
              fontWeight: 'bold',
              background: 'linear-gradient(90deg, #FF6F61 0%, #FF3CAC 100%)',
              '&:hover': {
                background: 'linear-gradient(90deg, #FF3CAC 0%, #FF6F61 100%)',
              },
            }}
          >
            {isSignUp ? 'Sign Up with Email' : 'Sign In with Email'}
          </Button>
          <Button
            variant="contained"
            color="secondary"
            onClick={handleGoogleSignIn}
            fullWidth
            sx={{
              minWidth: { xs: '120px', sm: '150px' },  // Added for responsive button size
              fontSize: { xs: '0.8rem', sm: '1rem' },  // Added for responsive font size
              borderRadius: '30px',
              px: 4,
              py: 2,
              fontFamily: 'Orbitron, sans-serif',
              fontWeight: 'bold',
              background: 'linear-gradient(90deg, #FF6F61 0%, #FF3CAC 100%)',
              '&:hover': {
                background: 'linear-gradient(90deg, #FF3CAC 0%, #FF6F61 100%)',
              },
            }}
          >
            Sign In with Google
          </Button>
        </Stack>

        <Divider sx={{ my: 3 }} />

        <Button variant="text" onClick={() => setIsSignUp(!isSignUp)} fullWidth>
          {isSignUp
            ? 'Already have an account? Sign In'
            : "Don't have an account? Sign Up"}
        </Button>
      </Paper>
    </Container>
  );
};

export default AuthPage;
