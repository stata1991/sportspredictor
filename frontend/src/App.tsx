import React from 'react';
import './App.css';
import { ThemeProvider } from '@mui/material/styles';
import theme from './theme/theme';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Header from './components/Header';
import PreMatchPage from './pages/PreMatchPage';
import LiveMatchPage from './pages/LiveMatchPage';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage'; // ✅ Ensure this path is correct
import { AuthProvider } from './context/AuthContext';

const AppContent: React.FC = () => {
  const location = useLocation();
  const isHome = location.pathname === '/';

  return (
    <div
      style={{
        backgroundImage: `url(${isHome ? '/home.png' : '/stadium-bg.jpg'})`,
        backgroundSize: 'cover',
        backgroundRepeat: 'no-repeat',
        backgroundAttachment: 'fixed',
        backgroundPosition: 'center',
        minHeight: '100vh',
      }}
    >
      {!isHome && <Header />}
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/cricket/ipl" element={<PreMatchPage />} />
        <Route path="/live" element={<LiveMatchPage />} />
        <Route path="/auth" element={<AuthPage />} />
      </Routes>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <ThemeProvider theme={theme}>
        <Router>
          <AppContent />
        </Router>
      </ThemeProvider>
    </AuthProvider>
  );
}

export default App;