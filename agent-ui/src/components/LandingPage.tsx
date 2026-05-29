import React from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Zap, Shield, Users, ArrowRight, BarChart3, Cloud } from 'lucide-react';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="fade-in hero-gradient">
      {/* Navbar */}
      <nav style={{display: 'flex', justifyContent: 'space-between', padding: '1.5rem 5rem', alignItems: 'center'}}>
        <div className="brand" style={{fontSize: '1.5rem', fontWeight: 800, color: 'var(--accent-primary)'}}>AETHERDESK</div>
        <div style={{display: 'flex', gap: '2rem', color: 'var(--text-secondary)'}}>
          <span className="nav-link">Features</span>
          <span className="nav-link">Pricing</span>
          <span className="nav-link">Enterprise</span>
        </div>
        <button className="btn-outline" onClick={() => navigate('/login')}>Login</button>
      </nav>

      {/* Hero Section */}
      <header style={{textAlign: 'center', padding: '8rem 2rem 5rem'}}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <span className="badge badge-active" style={{padding: '0.5rem 1rem', fontSize: '0.8rem', marginBottom: '2rem', display: 'inline-block'}}>
            V0.3: Sovereign Autonomous Engine
          </span>
          <h1 style={{fontSize: '4.5rem', fontWeight: 800, marginBottom: '1.5rem', letterSpacing: '-0.02em'}}>
            Rent Your Own <br/> 
            <span style={{background: 'linear-gradient(135deg, #6366f1, #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'}}>
              Agentic Call Center
            </span>
          </h1>
          <p style={{color: 'var(--text-secondary)', fontSize: '1.25rem', maxWidth: '600px', margin: '0 auto 2.5rem'}}>
            Deploy an elite fleet of AI voice agents in minutes. Rent by the hour, scale with the market, and supervise in real-time.
          </p>
          <div style={{display: 'flex', gap: '1rem', justifyContent: 'center'}}>
            <button className="btn-primary" style={{display: 'flex', alignItems: 'center', gap: '10px'}} onClick={() => navigate('/dashboard')}>
              Get Started Free <ArrowRight size={18}/>
            </button>
            <button className="btn-outline">View Enterprise Tiers</button>
          </div>
        </motion.div>
      </header>

      {/* Features Grid */}
      <section style={{padding: '5rem', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem'}}>
        <div className="glass-card">
          <Zap className="icon" color="var(--accent-primary)" style={{marginBottom: '1rem'}}/>
          <h3>Ultra-Low Latency</h3>
          <p style={{color: 'var(--text-secondary)', marginTop: '0.5rem'}}>Conversational audio pipeline under 600ms for human-like response times.</p>
        </div>
        <div className="glass-card">
          <Shield className="icon" color="var(--accent-primary)" style={{marginBottom: '1rem'}}/>
          <h3>Enterprise-Grade Safety</h3>
          <p style={{color: 'var(--text-secondary)', marginTop: '0.5rem'}}>Built-in PII redaction and prompt injection guards via Microsoft Presidio.</p>
        </div>
        <div className="glass-card">
          <BarChart3 className="icon" color="var(--accent-primary)" style={{marginBottom: '1rem'}}/>
          <h3>Real-Time Supervision</h3>
          <p style={{color: 'var(--text-secondary)', marginTop: '0.5rem'}}>Monitor sentiment live and take over calls with a single click.</p>
        </div>
      </section>

      {/* Pricing Teaser */}
      <section style={{padding: '5rem', textAlign: 'center'}}>
        <h2 style={{fontSize: '2.5rem', marginBottom: '1rem'}}>Flexible Rental Blocks</h2>
        <p style={{color: 'var(--text-secondary)', marginBottom: '3rem'}}>No long-term contracts. Just raw agentic horsepower.</p>
        
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', maxWidth: '1000px', margin: '0 auto'}}>
          <div className="glass-card" style={{border: '1px solid var(--border-color)'}}>
            <h3>Startup</h3>
            <p style={{fontSize: '2rem', margin: '1rem 0'}}>$1 <span style={{fontSize: '1rem', color: 'var(--text-secondary)'}}>/agent-hour</span></p>
            <ul style={{textAlign: 'left', listStyle: 'none', marginBottom: '1.5rem', color: 'var(--text-secondary)'}}>
              <li style={{marginBottom: '0.5rem'}}>✓ 5 Concurrent Seats</li>
              <li style={{marginBottom: '0.5rem'}}>✓ Standard ASR/TTS</li>
              <li style={{marginBottom: '0.5rem'}}>✓ 30-Day Logs</li>
            </ul>
            <button className="btn-outline" style={{width: '100%'}}>Choose Startup</button>
          </div>
          <div className="glass-card" style={{borderColor: 'var(--accent-primary)', position: 'relative', overflow: 'hidden'}}>
             <div style={{position: 'absolute', top: '10px', right: '-30px', background: 'var(--accent-primary)', color: 'white', padding: '0.2rem 3rem', transform: 'rotate(45deg)', fontSize: '0.7rem'}}>POPULAR</div>
            <h3>Business</h3>
            <p style={{fontSize: '2rem', margin: '1rem 0'}}>$0.75 <span style={{fontSize: '1rem', color: 'var(--text-secondary)'}}>/agent-hour</span></p>
            <ul style={{textAlign: 'left', listStyle: 'none', marginBottom: '1.5rem', color: 'var(--text-secondary)'}}>
              <li style={{marginBottom: '0.5rem'}}>✓ 25 Concurrent Seats</li>
              <li style={{marginBottom: '0.5rem'}}>✓ Premium Neural Voices</li>
              <li style={{marginBottom: '0.5rem'}}>✓ Real-time Command Center</li>
            </ul>
            <button className="btn-primary" style={{width: '100%'}}>Choose Business</button>
          </div>
          <div className="glass-card">
            <h3>Enterprise</h3>
            <p style={{fontSize: '2rem', margin: '1rem 0'}}>Custom</p>
            <ul style={{textAlign: 'left', listStyle: 'none', marginBottom: '1.5rem', color: 'var(--text-secondary)'}}>
              <li style={{marginBottom: '0.5rem'}}>✓ Unlimited Seats</li>
              <li style={{marginBottom: '0.5rem'}}>✓ Dedicated Infrastructure</li>
              <li style={{marginBottom: '0.5rem'}}>✓ 24/7 Priority Handoff</li>
            </ul>
            <button className="btn-outline" style={{width: '100%'}}>Contact Sales</button>
          </div>
        </div>
      </section>

      <footer style={{padding: '5rem', borderTop: '1px solid var(--border-color)', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem'}}>
        &copy; 2026 AetherDesk Inc. All rights reserved.
      </footer>
    </div>
  );
};
