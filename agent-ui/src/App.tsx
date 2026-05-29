import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { LandingPage } from './components/LandingPage';
import { SaasDashboard } from './components/SaaSDashboard';

// Mock Auth wrapper
const PrivateRoute = ({ children }: { children: JSX.Element }) => {
  const isAuthenticated = localStorage.getItem('isLoggedIn') === 'true';
  return isAuthenticated ? children : <Navigate to="/login" />;
};

const LoginPage = () => {
  const handleLogin = () => {
    localStorage.setItem('isLoggedIn', 'true');
    window.location.href = '/dashboard';
  };

  return (
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#0a0a0c'}}>
      <div className="glass-card" style={{width: '400px', textAlign: 'center'}}>
        <h2 style={{marginBottom: '1.5rem'}}>Login to AetherDesk</h2>
        <input type="email" placeholder="Email address" defaultValue="founder@acme.com" />
        <input type="password" placeholder="Password" defaultValue="********" />
        <button className="btn-primary" style={{width: '100%', marginBottom: '1rem'}} onClick={handleLogin}>
          Sign In
        </button>
        <div style={{fontSize: '0.8rem', color: 'var(--text-secondary)'}}>
          Don't have an account? <span style={{color: 'var(--accent-primary)', cursor: 'pointer'}}>Create one</span>
        </div>
      </div>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<SaasDashboard />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
};

export default App;
