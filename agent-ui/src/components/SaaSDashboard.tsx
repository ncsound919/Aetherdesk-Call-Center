import React, { useState, useEffect } from 'react';
import { CallDetail } from './CallDetail';
import { 
  LayoutDashboard, 
  Activity, 
  Settings, 
  Users, 
  BookOpen, 
  ShieldCheck, 
  ShoppingBag, 
  Share2,
  ChevronRight,
  Phone,
  AlertTriangle
} from 'lucide-react';

interface Rental { id: string; profile_id: string; duration_type: string; end_time: string; status: string; }
interface Profile { id: string; name: string; prompt: string; parameters: string; }
interface Approval { id: string; session_id: string; agent_id: string; action: string; params: string; status: string; }
interface Recording { id: string; session_id: string; transcript: string; qa_score: number; qa_feedback: string; created_at: string; }
interface MarketplaceItem { id: string; name: string; industry: string; description: string; usage_count: number; prompt: string; avg_qa_score: number; }

export const SaasDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState("dashboard"); // dashboard, command, flows, settings, affiliate, marketplace, academy
  const [data, setData] = useState<{ rentals: Rental[]; profiles: Profile[]; tenant?: any }>({ rentals: [], profiles: [] });
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceItem[]>([
    {
      id: "mkt-1",
      name: "Solar Sales Closer",
      industry: "renewable energy",
      description: "High-ticket solar panel closer with urgency triggers and financing objection handling.",
      usage_count: 1247,
      prompt: "You are a high-performing solar sales closer. Build rapport quickly, identify pain points around electricity costs, and use urgency to close. Handle common objections: cost, roof suitability, and timing. Always pivot to a free consultation booking.",
      avg_qa_score: 96
    },
    {
      id: "mkt-2",
      name: "SaaS Trial Converter",
      industry: "technology",
      description: "Converts free trial users to paid plans with value-driven conversations.",
      usage_count: 893,
      prompt: "You are a SaaS sales agent converting free trial users to paid plans. Focus on the value they've already received, quantify their potential savings, and create urgency around expiring trial periods. Be helpful, not pushy.",
      avg_qa_score: 92
    },
    {
      id: "mkt-3",
      name: "Insurance Claims Triage",
      industry: "insurance",
      description: "First-response claims handler that collects details and routes to the right adjuster.",
      usage_count: 567,
      prompt: "You are an insurance claims triage specialist. Collect the policy number, date of incident, and type of claim. Show empathy for the situation. Route to the appropriate adjuster based on claim type and severity.",
      avg_qa_score: 88
    },
    {
      id: "mkt-4",
      name: "Medical Appointment Scheduler",
      industry: "healthcare",
      description: "HIPAA-compliant scheduler that finds open slots and confirms appointments.",
      usage_count: 421,
      prompt: "You are a HIPAA-compliant medical scheduling assistant. Collect patient name, date of birth, preferred provider, and reason for visit. Check available slots, confirm the appointment, and provide preparation instructions.",
      avg_qa_score: 94
    },
  ]);
  const [settings, setSettings] = useState({ 
    api_feeds: "{}", 
    auto_mode_enabled: false,
    redact_pii: true,
    require_consent: true,
    sync_dnc: false,
    mcp_servers: "{}"
  });
  const [loading, setLoading] = useState(true);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [campaignStats, setCampaignStats] = useState<any>({});
  const [leads, setLeads] = useState<any[]>([]);
  const [campaignCalls, setCampaignCalls] = useState<any[]>([]);
  const [escalations, setEscalations] = useState<any[]>([]);
  const [newLeadPhone, setNewLeadPhone] = useState('');
  const [newLeadCompany, setNewLeadCompany] = useState('');
  const [newLeadContact, setNewLeadContact] = useState('');
  const [newLeadIndustry, setNewLeadIndustry] = useState('');

  // Form states
  const [profileName, setProfileName] = useState("");
  const [profilePrompt, setProfilePrompt] = useState("");
  const [scriptGoal, setScriptGoal] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("general");
  const [isGenerating, setIsGenerating] = useState(false);

  const TEMPLATES: Record<string, string> = {
    general: "General purpose assistant.",
    sales: "Outbound sales closer focusing on pain points and urgency.",
    support: "Helpful technical support assistant with a focus on patience.",
    medical: "HIPAA-compliant medical assistant for appointment scheduling."
  };

  const handleApprove = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/saas/approvals/${id}?status=approved`, {
        method: 'POST',
        headers: { 'X-API-Key': 'dev-api-key' }
      });
      if (res.ok) {
        setApprovals(prev => prev.filter(a => a.id !== id));
        fetchData();
      }
    } catch (e) { console.error("Approval failed", e); }
  };

  const handleReject = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/saas/approvals/${id}?status=rejected`, {
        method: 'POST',
        headers: { 'X-API-Key': 'dev-api-key' }
      });
      if (res.ok) {
        setApprovals(prev => prev.filter(a => a.id !== id));
        fetchData();
      }
    } catch (e) { console.error("Rejection failed", e); }
  };

  const handleTakeover = (callSid: string) => {
    // This would typically send a WS message to the server
    console.log("Taking over call:", callSid);
    alert(`Initiating takeover for call ${callSid}...`);
    // Example: ws.send(JSON.stringify({type: 'takeover_call', call_sid: callSid}));
  };

  const fetchData = async () => {
    try {
      const dRes = await fetch("http://localhost:8000/api/v1/saas/dashboard");
      const dJson = await dRes.json();
      setData(dJson);
      if (dJson.rentals.length === 0) setShowOnboarding(true);

      const aRes = await fetch("http://localhost:8000/api/v1/saas/approvals");
      setApprovals(await aRes.json());

      const rRes = await fetch("http://localhost:8000/api/v1/saas/recordings");
      setRecordings(await rRes.json());

      const sRes = await fetch("http://localhost:8000/api/v1/saas/settings");
      setSettings(await sRes.json());

      // Campaign data
      try {
        const csRes = await fetch("http://localhost:8000/api/v1/campaign/stats", {headers: {'X-API-Key': 'dev-api-key'}});
        setCampaignStats(await csRes.json());
        const lRes = await fetch("http://localhost:8000/api/v1/campaign/leads", {headers: {'X-API-Key': 'dev-api-key'}});
        setLeads(await lRes.json());
        const ccRes = await fetch("http://localhost:8000/api/v1/campaign/calls", {headers: {'X-API-Key': 'dev-api-key'}});
        setCampaignCalls(await ccRes.json());
      } catch(e) { console.warn('Campaign data fetch skipped', e); }
    } catch (e) {
      console.error("Fetch failed", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    await fetch(`http://localhost:8000/api/v1/saas/profile?name=${profileName}&prompt=${profilePrompt}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tools: ["lookup_invoice", "search_knowledge_base"] })
    });
    setProfileName(""); setProfilePrompt("");
    fetchData();
  };

  const handleGenerateScript = async () => {
    setIsGenerating(true);
    try {
      const promptGoal = `Objective: ${scriptGoal}. Tone/Template: ${selectedTemplate}.`;
      const res = await fetch("http://localhost:8000/api/v1/saas/generate-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective: promptGoal })
      });
      const json = await res.json();
      setProfilePrompt(json.script);
    } catch (e) {
      alert("Failed to generate script.");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleUpdateSettings = async () => {
    await fetch("http://localhost:8000/api/v1/saas/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings)
    });
    alert("Settings Saved");
  };

  if (loading) return <div className="loading">Loading AetherDesk Engine...</div>;

  return (
    <div className="grid">
      <aside className="sidebar">
        <div className="brand" style={{padding: '1.5rem', fontWeight: 800, fontSize: '1.4rem', color: 'var(--accent-primary)', borderBottom: '1px solid var(--border-color)', marginBottom: '1rem'}}>
          AETHERDESK
        </div>
        <div className={`sidebar-item ${activeTab === "dashboard" ? "active" : ""}`} onClick={() => setActiveTab("dashboard")}>
          <LayoutDashboard size={18}/> Fleet Stats
        </div>
        <div className={`sidebar-item ${activeTab === "command" ? "active" : ""}`} onClick={() => setActiveTab("command")}>
          <Activity size={18}/> Command Center
        </div>
        <div className={`sidebar-item ${activeTab === "flows" ? "active" : ""}`} onClick={() => setActiveTab("flows")}>
          <Share2 size={18}/> Flow Designer
        </div>
        <div className={`sidebar-item ${activeTab === "marketplace" ? "active" : ""}`} onClick={() => setActiveTab("marketplace")}>
          <ShoppingBag size={18}/> Marketplace
        </div>
        <div className={`sidebar-item ${activeTab === "approvals" ? "active" : ""}`} onClick={() => setActiveTab("approvals")}>
          <ShieldCheck size={18}/> Supervision {approvals.length > 0 && <span className="badge badge-active">{approvals.length}</span>}
        </div>
        <div className={`sidebar-item ${activeTab === "campaign" ? "active" : ""}`} onClick={() => setActiveTab("campaign")}>
          <Phone size={18}/> Outreach
          {escalations.length > 0 && <span className="badge" style={{background: 'rgba(239,68,68,0.2)', color: '#ef4444'}}>{escalations.length}</span>}
        </div>
        <div className="sidebar-divider" style={{height: '1px', background: 'var(--border-color)', margin: '1rem 1.5rem'}}></div>
        <div className={`sidebar-item ${activeTab === "academy" ? "active" : ""}`} onClick={() => setActiveTab("academy")}>
          <BookOpen size={18}/> Academy
        </div>
        <div className={`sidebar-item ${activeTab === "settings" ? "active" : ""}`} onClick={async () => {
          setActiveTab("settings");
          try {
            const sRes = await fetch("http://localhost:8000/api/v1/saas/settings");
            setSettings(await sRes.json());
          } catch {}
        }}>
          <Settings size={18}/> Integrations
        </div>
        <div className={`sidebar-item ${activeTab === "affiliate" ? "active" : ""}`} onClick={() => setActiveTab("affiliate")}>
          <Users size={18}/> Affiliate
        </div>
      </aside>

      <main className="view-content">
        {showOnboarding && (
          <div className="glass-card fade-in" style={{marginBottom: '2rem', border: '2px solid var(--accent-primary)'}}>
             <h2 style={{color: 'var(--accent-primary)'}}>Welcome to AetherDesk, {data.tenant?.name || 'New Founder'}!</h2>
             <p style={{margin: '1rem 0'}}>We noticed you haven't deployed your first agent fleet yet. To get you started, our AI has analyzed your profile and suggests starting with a <strong>{selectedTemplate.toUpperCase()}</strong> agent.</p>
             <div style={{display: 'flex', gap: '1rem'}}>
                <button className="btn-primary" onClick={() => { setActiveTab("flows"); setShowOnboarding(false); }}>Launch First Agent</button>
                <button className="btn-outline" onClick={() => setShowOnboarding(false)}>Dismiss</button>
             </div>
          </div>
        )}

        {activeTab === "dashboard" && (
          <div className="fade-in">
            <h2 style={{marginBottom: '1.5rem'}}>Operational Fleet Overview</h2>
            <div className="stat-grid" style={{marginBottom: '2rem'}}>
                <div className="glass-card">
                  <p style={{color: 'var(--text-secondary)', fontSize: '0.875rem'}}>Platform Tier</p>
                  <h3 style={{fontSize: '1.5rem', color: 'var(--accent-primary)'}}>{data.tenant?.tier?.toUpperCase() || 'ENTERPRISE'}</h3>
                </div>
                <div className="glass-card">
                  <p style={{color: 'var(--text-secondary)', fontSize: '0.875rem'}}>Active Capacity</p>
                  <h3 style={{fontSize: '2rem'}}>{data.rentals.length} / {data.tenant?.max_seats || 25}</h3>
                </div>
                <div className="glass-card">
                  <p style={{color: 'var(--text-secondary)', fontSize: '0.875rem'}}>Marketplace Contributions</p>
                  <h3 style={{fontSize: '2rem'}}>{marketplace.length} Templates</h3>
                </div>
            </div>

            <h3 style={{marginBottom: '1rem'}}>Active Rentals</h3>
            <div className="glass-card" style={{padding: 0, overflow: 'hidden'}}>
              <table style={{width: '100%', borderCollapse: 'collapse'}}>
                <thead style={{background: 'rgba(255,255,255,0.05)'}}>
                  <tr>
                    <th style={{padding: '1rem', textAlign: 'left'}}>Agent ID</th>
                    <th style={{padding: '1rem', textAlign: 'left'}}>Tier</th>
                    <th style={{padding: '1rem', textAlign: 'left'}}>Expires</th>
                    <th style={{padding: '1rem', textAlign: 'left'}}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rentals.map(r => (
                    <tr key={r.id} style={{borderTop: '1px solid var(--border-color)'}}>
                      <td style={{padding: '1rem'}}>{r.id}</td>
                      <td style={{padding: '1rem'}}>{r.duration_type}</td>
                      <td style={{padding: '1rem'}}>{r.end_time}</td>
                      <td style={{padding: '1rem'}}><span className="badge badge-active">{r.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.profiles.length > 0 && (
              <>
                <h3 style={{margin: '2rem 0 1rem 0'}}>Available Agent Profiles ({data.profiles.length})</h3>
                <div className="glass-card" style={{padding: 0, overflow: 'hidden'}}>
                  <table style={{width: '100%', borderCollapse: 'collapse'}}>
                    <thead style={{background: 'rgba(255,255,255,0.05)'}}>
                      <tr>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Profile ID</th>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Name</th>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Tone</th>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.profiles.map(p => {
                        let params: any = {};
                        try { params = JSON.parse(p.parameters); } catch {}
                        return (
                          <tr key={p.id} style={{borderTop: '1px solid var(--border-color)'}}>
                            <td style={{padding: '1rem'}}>{p.id}</td>
                            <td style={{padding: '1rem'}}>{p.name}</td>
                            <td style={{padding: '1rem'}}>{params.tone || '—'}</td>
                            <td style={{padding: '1rem'}}>
                              <button className="btn-outline" style={{fontSize: '0.75rem', padding: '0.25rem 0.75rem'}}
                                onClick={() => { setProfilePrompt(p.prompt); setProfileName(p.name); setActiveTab("flows"); }}>
                                Edit in Flow Designer
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "marketplace" && (
          <div className="fade-in">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem'}}>
              <h2>Community-Led Template Marketplace</h2>
              <button className="btn-secondary">Publish Your Script</button>
            </div>
            <p style={{marginBottom: '2rem', color: 'var(--text-secondary)'}}>Clone high-performing conversational flows from our community of world-class sales and support leads.</p>
            
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1.5rem'}}>
              {marketplace.length > 0 ? marketplace.map(item => (
                <div key={item.id} className="glass-card" style={{display: 'flex', flexDirection: 'column', justifyContent: 'space-between'}}>
                  <div>
                    <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem'}}>
                      <span className="badge badge-active" style={{fontSize: '0.6rem'}}>{item.industry.toUpperCase()}</span>
                      <span style={{fontSize: '0.8rem', color: 'gold'}}>★ {item.avg_qa_score}</span>
                    </div>
                    <h3 style={{marginBottom: '0.5rem'}}>{item.name}</h3>
                    <p style={{fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem'}}>{item.description}</p>
                  </div>
                  <div>
                    <div style={{fontSize: '0.75rem', marginBottom: '1rem', color: 'var(--text-secondary)'}}>{item.usage_count} Deployments</div>
                    <button className="btn-primary" style={{width: '100%'}} onClick={() => { setProfilePrompt(item.prompt); setActiveTab("flows"); }}>Clone & Customize</button>
                  </div>
                </div>
              )) : (
                <p style={{color: 'var(--text-secondary)'}}>No templates available yet. Publish your first script to the community.</p>
              )}
            </div>
          </div>
        )}

        {activeTab === "academy" && (
          <div className="fade-in">
            <h2 style={{marginBottom: '1.5rem'}}>AetherDesk Academy: Educational Insights</h2>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem'}}>
               <div className="glass-card">
                  <h3 style={{marginBottom: '1rem', color: 'var(--accent-secondary)'}}>Mastering Objection Handling</h3>
                  <p style={{fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1rem'}}>
                    In B2B voice agents, the "Feel-Felt-Found" method reduces hang-up rates by 42%. Use our Solar Template to see this in action...
                  </p>
                  <button className="btn-primary" onClick={() => { setProfilePrompt(TEMPLATES.sales); setActiveTab("flows"); }}>
                    Open Sales Template in Flow Designer
                  </button>
               </div>
               <div className="glass-card">
                  <h3 style={{marginBottom: '1rem', color: 'var(--accent-secondary)'}}>Reducing LLM Latency</h3>
                  <p style={{fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '1rem'}}>
                    Learn how our RAG Query Caching saves you 30% on token costs while keeping agent responses under 600ms...
                  </p>
                  <div style={{display: 'flex', gap: '0.5rem'}}>
                    <button className="btn-outline" onClick={() => alert('Tip: Set OLLAMA_MODEL to a smaller quantized model and add num_predict: 50 to limit output tokens.')}>
                      Show Pro Tip
                    </button>
                    <button className="btn-outline" onClick={() => setActiveTab("flows")}>
                      Try in Flow Designer
                    </button>
                  </div>
               </div>
            </div>
            <div style={{marginTop: '2rem'}} className="glass-card">
              <h3 style={{marginBottom: '1rem'}}>Quick Knowledge Check</h3>
              <p style={{marginBottom: '1rem', color: 'var(--text-secondary)'}}>
                What is the primary purpose of a Flow Designer template?
              </p>
              <div style={{display: 'flex', gap: '0.5rem', flexWrap: 'wrap'}}>
                <button className="btn-outline" onClick={() => alert('Correct! Templates give your AI agent a pre-built personality and call script, saving hours of prompt engineering.')}>
                  Pre-built agent personality & call script
                </button>
                <button className="btn-outline" onClick={() => alert('Not quite. Templates define the agent behavior, not user accounts.')}>
                  Create user accounts
                </button>
                <button className="btn-outline" onClick={() => alert('Close, but templates are about agent behavior configuration.')}>
                  Configure billing settings
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === "flows" && (
          <div className="fade-in">
            <h2 style={{marginBottom: '1.5rem'}}>Flow Designer & Scripts</h2>
            <div className="glass-card" style={{marginBottom: '1.5rem'}}>
              <h3 style={{marginBottom: '1rem'}}>Industry Quick-Start Templates</h3>
              <div style={{display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem'}}>
                {Object.keys(TEMPLATES).map(t => (
                  <button 
                    key={t}
                    className={selectedTemplate === t ? "btn-secondary" : "btn-outline"} 
                    onClick={() => {
                      setSelectedTemplate(t);
                      setProfilePrompt(TEMPLATES[t]);
                    }}
                    style={{fontSize: '0.75rem', padding: '0.25rem 0.75rem'}}
                  >
                    {t.toUpperCase()}
                  </button>
                ))}
              </div>

              <h3 style={{marginBottom: '1rem'}}>Auto-Generate Script</h3>
              <div style={{display: 'flex', gap: '1rem'}}>
                <input 
                  style={{flex: 1}} 
                  placeholder="e.g. Sell solar panels to homeowners in California" 
                  value={scriptGoal} 
                  onChange={e => setScriptGoal(e.target.value)} 
                />
                <button className="btn-secondary" onClick={handleGenerateScript} disabled={isGenerating}>
                  {isGenerating ? "Generating..." : "Generate AI Script"}
                </button>
              </div>
            </div>

            <div className="glass-card">
              <h3 style={{marginBottom: '1rem'}}>Script Variables & Profile</h3>
              <form onSubmit={handleCreateProfile}>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem'}}>
                  <input placeholder="Agent Name (e.g. Sarah)" value={profileName} onChange={e => setProfileName(e.target.value)} required />
                </div>
                <textarea 
                  placeholder="Full System Prompt / Guidelines" 
                  style={{height: '200px', marginBottom: '1rem'}} 
                  value={profilePrompt} 
                  onChange={e => setProfilePrompt(e.target.value)}
                  required
                />
                <button type="submit" className="btn-primary">Deploy Agent Profile</button>
              </form>
            </div>
          </div>
        )}

        {activeTab === "command" && (
          <div className="fade-in">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem'}}>
              <h2>Mission Control: Live Command Center</h2>
              <div style={{display: 'flex', gap: '0.5rem', alignItems: 'center'}}>
                <div className="pulse-dot"></div>
                <span style={{fontSize: '0.8rem', color: 'var(--success)', fontWeight: 600}}>SYSTEMS NOMINAL</span>
              </div>
            </div>
            
            <div style={{display: 'grid', gridTemplateColumns: '1fr 350px', gap: '2rem'}}>
              <div className="glass-card" style={{minHeight: '400px'}}>
                <h3 style={{marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                  <Activity size={18} color="var(--accent-primary)" /> Active Voice Streams
                </h3>
                <div style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                  {campaignCalls.filter(c => c.status === 'in_progress' || c.status === 'ringing').length > 0 ? (
                    campaignCalls.filter(c => c.status === 'in_progress' || c.status === 'ringing').map(c => (
                      <div key={c.id} className="glass-card" style={{padding: '1rem', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                         <div>
                            <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                              <span style={{fontWeight: 700, fontSize: '1rem'}}>{c.company_name}</span>
                              <span className="badge" style={{fontSize: '0.6rem', background: 'rgba(99,102,241,0.1)', color: 'var(--accent-primary)'}}>{c.profile_id}</span>
                            </div>
                            <div style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem'}}>
                              ID: {c.call_sid} | Duration: {Math.floor((Date.now() - new Date(c.started_at).getTime()) / 1000)}s
                            </div>
                            {c.sentiment && (
                              <div style={{fontSize: '0.75rem', marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.3rem'}}>
                                <span style={{color: 'var(--text-secondary)'}}>Sentiment:</span>
                                <span style={{color: c.sentiment === 'positive' ? 'var(--success)' : c.sentiment === 'negative' ? '#ef4444' : 'var(--text-secondary)'}}>{c.sentiment.toUpperCase()}</span>
                              </div>
                            )}
                         </div>
                         <div style={{display: 'flex', gap: '0.5rem'}}>
                           <button className="btn-outline" style={{fontSize: '0.75rem', padding: '0.4rem 0.8rem'}} onClick={() => handleTakeover(c.call_sid)}>Take Over</button>
                           <button className="btn-secondary" style={{fontSize: '0.75rem', padding: '0.4rem 0.8rem'}}>Listen</button>
                         </div>
                      </div>
                    ))
                  ) : (
                    <div style={{textAlign: 'center', padding: '4rem 0', color: 'var(--text-secondary)'}}>
                      <div style={{fontSize: '3rem', marginBottom: '1rem', opacity: 0.2}}>📡</div>
                      <p>Scanning for active telemetry...</p>
                      <button className="btn-outline" style={{marginTop: '1.5rem'}} onClick={() => setActiveTab("campaign")}>Start Outreach Campaign</button>
                    </div>
                  )}
                </div>
              </div>
              
              <div style={{display: 'flex', flexDirection: 'column', gap: '1.5rem'}}>
                <div className="glass-card">
                  <h3 style={{marginBottom: '1rem', fontSize: '1rem'}}>Fleet Resource Telemetry</h3>
                  <div style={{marginBottom: '1.25rem'}}>
                     <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.5rem'}}>
                        <span>Compute Density (Ollama)</span>
                        <span>12%</span>
                     </div>
                     <div style={{height: '6px', background: 'var(--border-color)', borderRadius: '3px'}}>
                        <div style={{width: '12%', height: '100%', background: 'var(--success)', borderRadius: '3px'}}></div>
                     </div>
                  </div>
                  <div style={{marginBottom: '1.25rem'}}>
                     <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.5rem'}}>
                        <span>Vector Store Latency</span>
                        <span>42ms</span>
                     </div>
                     <div style={{height: '6px', background: 'var(--border-color)', borderRadius: '3px'}}>
                        <div style={{width: '5%', height: '100%', background: 'var(--accent-primary)', borderRadius: '3px'}}></div>
                     </div>
                  </div>
                  <div>
                     <div style={{display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.5rem'}}>
                        <span>PSTN Gateway Load</span>
                        <span>{campaignCalls.filter(c => c.status === 'in_progress').length} / 50</span>
                     </div>
                     <div style={{height: '6px', background: 'var(--border-color)', borderRadius: '3px'}}>
                        <div style={{width: `${(campaignCalls.filter(c => c.status === 'in_progress').length / 50) * 100}%`, height: '100%', background: 'var(--accent-secondary)', borderRadius: '3px'}}></div>
                     </div>
                  </div>
                </div>

                <div className="glass-card" style={{background: 'linear-gradient(135deg, rgba(99,102,241,0.05) 0%, rgba(168,85,247,0.05) 100%)'}}>
                  <h3 style={{marginBottom: '1rem', fontSize: '1rem', color: 'var(--accent-primary)'}}>Agent Intelligence Stats</h3>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem'}}>
                    <div>
                      <div style={{fontSize: '0.7rem', color: 'var(--text-secondary)'}}>AVG CSAT</div>
                      <div style={{fontSize: '1.5rem', fontWeight: 700}}>{campaignStats.avg_csat || '--'}</div>
                    </div>
                    <div>
                      <div style={{fontSize: '0.7rem', color: 'var(--text-secondary)'}}>AVG LATENCY</div>
                      <div style={{fontSize: '1.5rem', fontWeight: 700}}>{campaignStats.avg_latency || '--'}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "approvals" && (
          <div className="fade-in">
            <h2 style={{marginBottom: '1.5rem'}}>Action Supervision Queue</h2>
            <div className="glass-card" style={{padding: 0, overflow: 'hidden'}}>
               {approvals.length > 0 ? (
                 <table style={{width: '100%', borderCollapse: 'collapse'}}>
                    <thead style={{background: 'rgba(255,255,255,0.05)'}}>
                      <tr>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Agent</th>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Requested Action</th>
                        <th style={{padding: '1rem', textAlign: 'left'}}>Params</th>
                        <th style={{padding: '1rem', textAlign: 'right'}}>Decision</th>
                      </tr>
                    </thead>
                    <tbody>
                      {approvals.map(a => (
                        <tr key={a.id} style={{borderTop: '1px solid var(--border-color)'}}>
                           <td style={{padding: '1rem'}}>{a.agent_id}</td>
                           <td style={{padding: '1rem'}}><span className="badge badge-active">{a.action}</span></td>
                           <td style={{padding: '1rem'}}>{a.params}</td>
                           <td style={{padding: '1rem', textAlign: 'right'}}>
                              <button className="btn-primary" style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem', marginRight: '0.5rem'}}>Approve</button>
                              <button className="btn-outline" style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem'}}>Reject</button>
                           </td>
                        </tr>
                      ))}
                    </tbody>
                 </table>
               ) : (
                 <div style={{padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)'}}>
                    No actions requiring supervision at this time.
                 </div>
               )}
            </div>
          </div>
        )}

        {activeTab === "settings" && (
          <div className="fade-in">
             <h2 style={{marginBottom: '1.5rem'}}>Integrations & Safety Guardrails</h2>
             <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem'}}>
                <div className="glass-card">
                   <h3>Connectivity</h3>
                   <div style={{marginTop: '1.5rem'}}>
                      <label style={{fontSize: '0.8rem', color: 'var(--text-secondary)'}}>Twilio Webhook URL</label>
                      <input defaultValue="https://aetherdesk.io/api/v1/voice/incoming" readOnly />
                      
                      <label style={{fontSize: '0.8rem', color: 'var(--text-secondary)'}}>CRM API Endpoint</label>
                      <input placeholder="https://api.hubspot.com/v1/..." />
                   </div>
                </div>
                <div className="glass-card">
                   <h3>Compliance Guardrails</h3>
                   <div style={{marginTop: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                         <span>PII Redaction (Presidio)</span>
                         <input type="checkbox" checked={settings.redact_pii} onChange={e => setSettings({...settings, redact_pii: e.target.checked})} style={{width: 'auto'}} />
                      </div>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                         <span>Sync with DNC Registry</span>
                         <input type="checkbox" checked={settings.sync_dnc} onChange={e => setSettings({...settings, sync_dnc: e.target.checked})} style={{width: 'auto'}} />
                      </div>
                      <button className="btn-primary" onClick={handleUpdateSettings}>Save Safety Configuration</button>
                   </div>
                </div>
             </div>
          </div>
        )}

        {activeTab === "campaign" && (
          <div className="fade-in">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem'}}>
              <h2>B2B Outreach Campaign</h2>
              <button className="btn-primary" onClick={async () => {
                const res = await fetch("http://localhost:8000/api/v1/campaign/launch", {
                  method: "POST", headers: {'Content-Type': 'application/json', 'X-API-Key': 'dev-api-key'},
                  body: JSON.stringify({profile_id: "PROF-META-SALES", max_concurrent: 3, delay_between_calls: 5})
                });
                const d = await res.json();
                alert(`Campaign ${d.status}: ${d.leads_queued || 0} leads queued`);
                fetchData();
              }}>🚀 Launch Campaign</button>
            </div>

            {/* Stats Row */}
            <div className="stat-grid" style={{marginBottom: '2rem'}}>
              <div className="glass-card">
                <p style={{color: 'var(--text-secondary)', fontSize: '0.8rem'}}>Total Leads</p>
                <h3 style={{fontSize: '2rem'}}>{campaignStats.total_leads || 0}</h3>
              </div>
              <div className="glass-card">
                <p style={{color: 'var(--text-secondary)', fontSize: '0.8rem'}}>Calls Made</p>
                <h3 style={{fontSize: '2rem'}}>{campaignStats.total_calls_made || 0}</h3>
              </div>
              <div className="glass-card">
                <p style={{color: 'var(--text-secondary)', fontSize: '0.8rem'}}>Interested</p>
                <h3 style={{fontSize: '2rem', color: 'var(--success)'}}>{campaignStats.interested || 0}</h3>
              </div>
              <div className="glass-card">
                <p style={{color: 'var(--text-secondary)', fontSize: '0.8rem'}}>Needs Human</p>
                <h3 style={{fontSize: '2rem', color: '#ef4444'}}>{campaignStats.needs_human_follow_up || 0}</h3>
              </div>
            </div>

            {/* Add Lead Form */}
            <div className="glass-card" style={{marginBottom: '1.5rem'}}>
              <h3 style={{marginBottom: '1rem'}}>Add Lead</h3>
              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: '0.75rem', alignItems: 'end'}}>
                <div>
                  <label style={{fontSize: '0.75rem', color: 'var(--text-secondary)'}}>Company</label>
                  <input placeholder="Acme Corp" value={newLeadCompany} onChange={e => setNewLeadCompany(e.target.value)} style={{marginBottom: 0}} />
                </div>
                <div>
                  <label style={{fontSize: '0.75rem', color: 'var(--text-secondary)'}}>Contact</label>
                  <input placeholder="John Smith" value={newLeadContact} onChange={e => setNewLeadContact(e.target.value)} style={{marginBottom: 0}} />
                </div>
                <div>
                  <label style={{fontSize: '0.75rem', color: 'var(--text-secondary)'}}>Phone</label>
                  <input placeholder="+15551234567" value={newLeadPhone} onChange={e => setNewLeadPhone(e.target.value)} style={{marginBottom: 0}} />
                </div>
                <div>
                  <label style={{fontSize: '0.75rem', color: 'var(--text-secondary)'}}>Industry</label>
                  <input placeholder="SaaS" value={newLeadIndustry} onChange={e => setNewLeadIndustry(e.target.value)} style={{marginBottom: 0}} />
                </div>
                <button className="btn-primary" style={{height: '42px'}} onClick={async () => {
                  if (!newLeadCompany || !newLeadPhone) return alert('Company and Phone required');
                  await fetch("http://localhost:8000/api/v1/campaign/leads", {
                    method: "POST", headers: {'Content-Type': 'application/json', 'X-API-Key': 'dev-api-key'},
                    body: JSON.stringify({company_name: newLeadCompany, contact_name: newLeadContact, phone: newLeadPhone, industry: newLeadIndustry})
                  });
                  setNewLeadCompany(''); setNewLeadContact(''); setNewLeadPhone(''); setNewLeadIndustry('');
                  fetchData();
                }}>Add</button>
              </div>
            </div>

            {/* Leads Table */}
            <div className="glass-card" style={{padding: 0, overflow: 'hidden', marginBottom: '1.5rem'}}>
              <div style={{padding: '1rem 1.5rem', borderBottom: '1px solid var(--border-color)'}}>
                <h3>Lead Pipeline ({leads.length})</h3>
              </div>
              <table style={{width: '100%', borderCollapse: 'collapse'}}>
                <thead style={{background: 'rgba(255,255,255,0.03)'}}>
                  <tr>
                    <th style={{padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem'}}>Company</th>
                    <th style={{padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem'}}>Contact</th>
                    <th style={{padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem'}}>Phone</th>
                    <th style={{padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem'}}>Industry</th>
                    <th style={{padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.8rem'}}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((l: any) => (
                    <tr key={l.id} style={{borderTop: '1px solid var(--border-color)'}}>
                      <td style={{padding: '0.75rem 1rem', fontWeight: 600}}>{l.company_name}</td>
                      <td style={{padding: '0.75rem 1rem'}}>{l.contact_name || '—'}</td>
                      <td style={{padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: '0.85rem'}}>{l.phone}</td>
                      <td style={{padding: '0.75rem 1rem'}}>{l.industry || '—'}</td>
                      <td style={{padding: '0.75rem 1rem'}}>
                        <span className="badge" style={{
                          background: l.status === 'new' ? 'rgba(99,102,241,0.15)' : l.status === 'interested' ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)',
                          color: l.status === 'new' ? '#6366f1' : l.status === 'interested' ? '#10b981' : 'var(--text-secondary)'
                        }}>{l.status}</span>
                      </td>
                    </tr>
                  ))}
                  {leads.length === 0 && (
                    <tr><td colSpan={5} style={{padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)'}}>No leads yet. Add your first lead above.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "affiliate" && (
          <div className="fade-in">
             <h2 style={{marginBottom: '1.5rem'}}>Partner Revenue Dashboard</h2>
             <div className="stat-grid" style={{marginBottom: '2rem'}}>
                <div className="glass-card">
                   <p style={{color: 'var(--text-secondary)', fontSize: '0.8rem'}}>Referral Count</p>
                   <h3 style={{fontSize: '2rem'}}>12</h3>
                </div>
                <div className="glass-card">
                   <p style={{color: 'var(--text-secondary)', fontSize: '0.8rem'}}>Total Earnings</p>
                   <h3 style={{fontSize: '2rem', color: 'var(--success)'}}>$1,240.50</h3>
                </div>
             </div>
             <div className="glass-card">
                <h3>Share Your Link</h3>
                <div style={{display: 'flex', gap: '1rem', marginTop: '1rem'}}>
                   <input value="https://aetherdesk.io/signup?ref=TENANT_001" readOnly />
                   <button className="btn-secondary">Copy Link</button>
                </div>
             </div>
          </div>
        )}
      </main>
    </div>
  );
};
