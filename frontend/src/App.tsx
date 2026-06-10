import React from 'react';
import './App.css';
import { ThemeProvider } from '@mui/material/styles';
import theme from './theme/theme';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Header from './components/Header';
import PreMatchPage from './pages/PreMatchPage';
import AuthPage from './pages/AuthPage';
import HomePage from './pages/HomePage'; // ✅ Ensure this path is correct
import T20WorldCupPage from './pages/T20WorldCupPage';
import WorldCup2026Layout from './pages/football/WorldCup2026Layout';
import SchedulePage from './pages/football/SchedulePage';
import LiveMatchPage from './pages/football/LiveMatchPage';
import TrackRecordPage from './pages/football/TrackRecordPage';
import StandingsPage from './pages/football/StandingsPage';
import KnockoutsPage from './pages/football/KnockoutsPage';
import MatchPage from './pages/football/MatchPage';
import UpsetsPage from './pages/football/UpsetsPage';
import NotFoundPage from './pages/NotFoundPage';
import PrivacyPage from './pages/PrivacyPage';
import AboutPage from './pages/AboutPage';
import Footer from './components/Footer';
import { AuthProvider } from './context/AuthContext';

const AppContent: React.FC = () => {
  const location = useLocation();
  const isHome = location.pathname === '/';

  return (
    <div
      style={{
        minHeight: '100vh',
      }}
    >
      {!isHome && <Header />}
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/cricket/ipl" element={<PreMatchPage />} />
        <Route path="/cricket/t20-world-cup" element={<T20WorldCupPage />} />
        <Route path="/football/world-cup-2026" element={<WorldCup2026Layout />}>
          <Route index element={<SchedulePage />} />
          <Route path="live" element={<LiveMatchPage />} />
          <Route path="track-record" element={<TrackRecordPage />} />
          <Route path="standings" element={<StandingsPage />} />
          <Route path="knockouts" element={<KnockoutsPage />} />
        </Route>
        <Route path="/football/match/:fixtureId" element={<MatchPage />} />
        <Route path="/football/upsets" element={<UpsetsPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <Footer />
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
