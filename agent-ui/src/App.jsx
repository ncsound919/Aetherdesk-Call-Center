import React, { useState, Suspense, lazy } from 'react';
import { Routes, Route, Navigate, Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  PhoneCall,
  Settings,
  BarChart3,
  LogOut,
  Menu,
  Bell,
  Search,
  ShieldCheck,
  Zap,
  MessageSquare,
  HeadphonesIcon,
  Activity,
  Brain,
  Layers,
  UserCheck,
  Mic2,
  FileText,
  Target,
  BookOpen,
  Server,
  Globe,
  Database,
  Radio,
  Code2,
  Briefcase,
  ChevronDown,
  ChevronRight
} from 'lucide-react';
import { Toaster } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from './context/AuthContext';

// ─── Lazy-loaded pages ───────────────────────────────────────────────────────
const Dashboard               = lazy(() => import('./pages/Dashboard'));
const Agents                  = lazy(() => import('./pages/AgentManagement'));
const Calls                   = lazy(() => import('./pages/CallLogs'));
const Login                   = lazy(() => import('./pages/Login'));
const Analytics               = lazy(() => import('./pages/Analytics'));
const SecurityDashboard       = lazy(() => import('./pages/SecurityDashboard'));
const IntegrationsDashboard   = lazy(() => import('./pages/IntegrationsDashboard'));
const Settings                = lazy(() => import('./pages/Settings'));
const LeadsPage               = lazy(() => import('./pages/LeadsPage'));
const LeadImportPage          = lazy(() => import('./pages/LeadImportPage'));
const ScriptsPage             = lazy(() => import('./pages/ScriptsPage'));
const ScriptEditorPage        = lazy(() => import('./pages/ScriptEditorPage'));
const VoiceCloning            = lazy(() => import('./pages/VoiceCloning'));
const VoiceQualityDashboard   = lazy(() => import('./pages/VoiceQualityDashboard'));
const AIOpsDashboard          = lazy(() => import('./pages/AIOpsDashboard'));
const AIPlatformDashboard     = lazy(() => import('./pages/AIPlatformDashboard'));
const AIWorkspace             = lazy(() => import('./pages/AIWorkspace'));
const WFMDashboard            = lazy(() => import('./pages/WFMDashboard'));
const WFMMetricsDashboard     = lazy(() => import('./pages/WFMMetricsDashboard'));
const QADashboard             = lazy(() => import('./pages/QADashboard'));
const SupervisorWallboard     = lazy(() => import('./pages/SupervisorWallboard'));
const TrainingDashboard       = lazy(() => import('./pages/TrainingDashboard'));
const ChatDashboard           = lazy(() => import('./pages/ChatDashboard'));
const SMSDashboard            = lazy(() => import('./pages/SMSDashboard'));
const CXDashboard             = lazy(() => import('./pages/CXDashboard'));
const CustomerPortalPreview   = lazy(() => import('./pages/CustomerPortalPreview'));
const CDPDashboard            = lazy(() => import('./pages/CDPDashboard'));
const ConversationQualityDashboard = lazy(() => import('./pages/ConversationQualityDashboard'));
const ReliabilityDashboard    = lazy(() => import('./pages/ReliabilityDashboard'));
const BusinessContinuityDashboard = lazy(() => import('./pages/BusinessContinuityDashboard'));
const FailoverDashboard       = lazy(() => import('./pages/FailoverDashboard'));
const DataGovernanceDashboard = lazy(() => import('./pages/DataGovernanceDashboard'));
const APIVersionsDashboard    = lazy(() => import('./pages/APIVersionsDashboard'));
const DeveloperDashboard      = lazy(() => import('./pages/DeveloperDashboard'));
const VerticalsDashboard      = lazy(() => import('./pages/VerticalsDashboard'));
const WhiteLabelDashboard     = lazy(() => import('./pages/WhiteLabelDashboard'));
const SelfServeSetup          = lazy(() => import('./pages/SelfServeSetup'));
const BillingPage             = lazy(() => import('./pages/BillingPage'));
const SignupPage              = lazy(() => import('./pages/SignupPage'));
const ForgotPasswordPage      = lazy(() => import('./pages/ForgotPasswordPage'));
const ResetPasswordPage       = lazy(() => import('./pages/ResetPasswordPage'));
const VerifyEmailPage         = lazy(() => import('./pages/VerifyEmailPage'));

// ─── Nav structure ───────────────────────────────────────────────────────────
const NAV_GROUPS = [
  {
    label: 'Core Platform',
    items: [
      { name: 'Overview',           icon: LayoutDashboard, path: '/' },
      { name: 'AI Agents',          icon: Users,            path: '/agents' },
      { name: 'Call History',       icon: PhoneCall,        path: '/calls' },
      { name: 'Analytics',          icon: BarChart3,        path: '/analytics' },
      { name: 'Leads',              icon: Target,           path: '/leads' },
      { name: 'Scripts',            icon: FileText,         path: '/scripts' },
    ],
  },
  {
    label: 'AI & Voice',
    items: [
      { name: 'AI Platform',        icon: Brain,            path: '/ai-platform' },
      { name: 'AI Ops',             icon: Activity,         path: '/ai-ops' },
      { name: 'AI Workspace',       icon: Layers,           path: '/ai-workspace' },
      { name: 'Voice Quality',      icon: Radio,            path: '/voice-quality' },
      { name: 'Voice Cloning',      icon: Mic2,             path: '/voice-cloning' },
    ],
  },
  {
    label: 'Omnichannel',
    items: [
      { name: 'Live Chat',          icon: MessageSquare,    path: '/chat' },
      { name: 'SMS',                icon: PhoneCall,        path: '/sms' },
      { name: 'CX Dashboard',       icon: HeadphonesIcon,   path: '/cx' },
      { name: 'Customer Portal',    icon: UserCheck,        path: '/customer-portal' },
      { name: 'CDP',                icon: Database,         path: '/cdp' },
    ],
  },
  {
    label: 'Workforce',
    items: [
      { name: 'WFM',                icon: BookOpen,         path: '/wfm' },
      { name: 'WFM Metrics',        icon: BarChart3,        path: '/wfm-metrics' },
      { name: 'QA Reviews',         icon: ShieldCheck,      path: '/qa' },
      { name: 'Supervisor Board',   icon: LayoutDashboard,  path: '/wallboard' },
      { name: 'Training',           icon: BookOpen,         path: '/training' },
      { name: 'Conv. Quality',      icon: Activity,         path: '/conv-quality' },
    ],
  },
  {
    label: 'Operations',
    items: [
      { name: 'Security',           icon: ShieldCheck,      path: '/security' },
      { name: 'Reliability',        icon: Server,           path: '/reliability' },
      { name: 'Business Continuity',icon: Briefcase,        path: '/biz-continuity' },
      { name: 'Failover',           icon: Activity,         path: '/failover' },
      { name: 'Data Governance',    icon: Database,         path: '/data-governance' },
    ],
  },
  {
    label: 'Management',
    items: [
      { name: 'Integrations',       icon: Zap,              path: '/integrations' },
      { name: 'API Versions',       icon: Code2,            path: '/api-versions' },
      { name: 'Developer',          icon: Code2,            path: '/developer' },
      { name: 'Verticals',          icon: Globe,            path: '/verticals' },
      { name: 'White Label',        icon: Layers,           path: '/white-label' },
      { name: 'Billing',            icon: Briefcase,        path: '/billing' },
      { name: 'Settings',           icon: Settings,         path: '/settings' },
    ],
  },
];

// ─── Sidebar ─────────────────────────────────────────────────────────────────
function NavGroup({ group, openGroups, toggleGroup, onLinkClick }) {
  const location = useLocation();
  const isOpen = openGroups[group.label] !== false; // default open

  return (
    <div>
      <button
        onClick={() => toggleGroup(group.label)}
        className="flex items-center justify-between w-full px-4 py-1 text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 hover:text-slate-600 transition-colors"
      >
        <span>{group.label}</span>
        {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </button>
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.nav
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-0.5 overflow-hidden"
          >
            {group.items.map((item) => {
              const active = location.pathname === item.path;
              return (
                <Link
                  key={item.name}
                  to={item.path}
                  onClick={onLinkClick}
                  className={`
                    flex items-center gap-3 px-4 py-2 rounded-xl text-[12px] font-semibold transition-all duration-150
                    ${active
                      ? 'bg-slate-900 text-white shadow-xl shadow-slate-900/10'
                      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'}
                  `}
                >
                  <item.icon className={`h-3.5 w-3.5 flex-shrink-0 ${active ? 'text-white' : 'text-slate-400'}`} />
                  <span className="truncate">{item.name}</span>
                </Link>
              );
            })}
          </motion.nav>
        )}
      </AnimatePresence>
    </div>
  );
}

/* eslint-disable no-unused-vars */
function Sidebar({ open, setOpen, logout }) {
/* eslint-enable no-unused-vars */
  const [openGroups, setOpenGroups] = useState({});

  const toggleGroup = (label) =>
    setOpenGroups((prev) => ({ ...prev, [label]: prev[label] === false ? true : false }));

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-md z-40 lg:hidden"
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>

      <aside className={`
        fixed inset-y-0 left-0 z-50 w-72 bg-white/90 backdrop-blur-xl border-r border-slate-200
        transform transition-transform duration-500 ease-in-out lg:translate-x-0 lg:static
        ${open ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="h-16 flex items-center px-6 border-b border-slate-100 flex-shrink-0">
            <Link to="/" className="flex items-center gap-3">
              <div className="h-9 w-9 bg-slate-900 rounded-2xl flex items-center justify-center shadow-xl shadow-blue-500/20">
                <PhoneCall className="h-4 w-4 text-white" />
              </div>
              <span className="text-lg font-black text-slate-900 tracking-tighter uppercase italic">Aether</span>
            </Link>
          </div>

          {/* Nav */}
          <div className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
            {NAV_GROUPS.map((group) => (
              <NavGroup
                key={group.label}
                group={group}
                openGroups={openGroups}
                toggleGroup={toggleGroup}
                onLinkClick={() => setOpen(false)}
              />
            ))}
          </div>

          {/* User footer */}
          <div className="p-3 border-t border-slate-100 flex-shrink-0">
            <div className="bg-slate-50 rounded-2xl p-3 border border-slate-100">
              <div className="flex items-center gap-3 mb-2">
                <div className="h-8 w-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold flex-shrink-0">A</div>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-slate-900 truncate">Admin</p>
                  <p className="text-[10px] text-slate-400">Professional Plan</p>
                </div>
              </div>
              <button
                onClick={() => logout()}
                className="flex items-center gap-2 w-full px-3 py-1.5 rounded-xl text-[11px] font-bold text-rose-600 hover:bg-rose-50 transition-all"
              >
                <LogOut className="h-3.5 w-3.5" />
                Logout Session
              </button>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

// ─── Header ──────────────────────────────────────────────────────────────────
/* eslint-disable no-unused-vars */
function Header({ setSidebarOpen }) {
/* eslint-enable no-unused-vars */
  return (
    <header className="h-16 bg-white/50 backdrop-blur-md flex items-center justify-between px-6 sticky top-0 z-30 border-b border-slate-100 flex-shrink-0">
      <div className="flex items-center gap-4 lg:hidden">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2 -ml-2 text-slate-600 hover:bg-slate-50 rounded-lg"
        >
          <Menu className="h-6 w-6" />
        </button>
      </div>

      <div className="hidden md:flex items-center bg-white border border-slate-200 rounded-2xl px-4 py-2 w-full max-w-md focus-within:ring-4 focus-within:ring-blue-500/5 focus-within:border-blue-400 transition-all duration-300 shadow-sm">
        <Search className="h-4 w-4 text-slate-400" />
        <input
          type="text"
          placeholder="Command search..."
          className="bg-transparent border-none focus:ring-0 text-sm ml-2 w-full text-slate-900 placeholder:text-slate-400"
        />
        <div className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-slate-200 bg-slate-50 text-[10px] font-bold text-slate-400">
          <span>⌘</span>
          <span>K</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button className="p-2.5 text-slate-500 hover:bg-white hover:text-slate-900 rounded-xl border border-transparent hover:border-slate-200 transition-all relative group">
          <Bell className="h-5 w-5" />
          <span className="absolute top-2.5 right-2.5 h-2 w-2 bg-blue-600 rounded-full border-2 border-white ring-2 ring-blue-100 group-hover:scale-125 transition-transform" />
        </button>
        <div className="h-9 w-9 bg-slate-900 rounded-2xl flex items-center justify-center text-white font-black text-xs shadow-lg shadow-slate-900/20 cursor-pointer hover:scale-105 transition-transform">
          A
        </div>
      </div>
    </header>
  );
}

// ─── Page loader fallback ─────────────────────────────────────────────────────
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="h-8 w-8 rounded-full border-4 border-slate-200 border-t-slate-900 animate-spin" />
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { isAuthenticated, logout } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return (
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login"          element={<Login />} />
          <Route path="/signup"         element={<SignupPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email"   element={<VerifyEmailPage />} />
          <Route path="*"               element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-inter bg-grid">
      <Sidebar open={sidebarOpen} setOpen={setSidebarOpen} logout={logout} />

      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        <Header setSidebarOpen={setSidebarOpen} />

        <main className="flex-1 overflow-y-auto">
          <div className="max-w-screen-2xl mx-auto p-4 lg:p-8">
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              >
                <Suspense fallback={<PageLoader />}>
                  <Routes>
                    {/* Core */}
                    <Route path="/"               element={<Dashboard />} />
                    <Route path="/agents"          element={<Agents />} />
                    <Route path="/calls"           element={<Calls />} />
                    <Route path="/analytics"       element={<Analytics />} />
                    <Route path="/leads"           element={<LeadsPage />} />
                    <Route path="/leads/import"    element={<LeadImportPage />} />
                    <Route path="/scripts"         element={<ScriptsPage />} />
                    <Route path="/scripts/:id"     element={<ScriptEditorPage />} />

                    {/* AI & Voice */}
                    <Route path="/ai-platform"    element={<AIPlatformDashboard />} />
                    <Route path="/ai-ops"         element={<AIOpsDashboard />} />
                    <Route path="/ai-workspace"   element={<AIWorkspace />} />
                    <Route path="/voice-quality"  element={<VoiceQualityDashboard />} />
                    <Route path="/voice-cloning"  element={<VoiceCloning />} />

                    {/* Omnichannel */}
                    <Route path="/chat"            element={<ChatDashboard />} />
                    <Route path="/sms"             element={<SMSDashboard />} />
                    <Route path="/cx"              element={<CXDashboard />} />
                    <Route path="/customer-portal" element={<CustomerPortalPreview />} />
                    <Route path="/cdp"             element={<CDPDashboard />} />

                    {/* Workforce */}
                    <Route path="/wfm"             element={<WFMDashboard />} />
                    <Route path="/wfm-metrics"     element={<WFMMetricsDashboard />} />
                    <Route path="/qa"              element={<QADashboard />} />
                    <Route path="/wallboard"        element={<SupervisorWallboard />} />
                    <Route path="/training"        element={<TrainingDashboard />} />
                    <Route path="/conv-quality"    element={<ConversationQualityDashboard />} />

                    {/* Operations */}
                    <Route path="/security"        element={<SecurityDashboard />} />
                    <Route path="/reliability"     element={<ReliabilityDashboard />} />
                    <Route path="/biz-continuity"  element={<BusinessContinuityDashboard />} />
                    <Route path="/failover"        element={<FailoverDashboard />} />
                    <Route path="/data-governance" element={<DataGovernanceDashboard />} />

                    {/* Management */}
                    <Route path="/integrations"    element={<IntegrationsDashboard />} />
                    <Route path="/api-versions"    element={<APIVersionsDashboard />} />
                    <Route path="/developer"       element={<DeveloperDashboard />} />
                    <Route path="/verticals"       element={<VerticalsDashboard />} />
                    <Route path="/white-label"     element={<WhiteLabelDashboard />} />
                    <Route path="/billing"         element={<BillingPage />} />
                    <Route path="/settings"        element={<Settings />} />
                    <Route path="/onboarding"      element={<SelfServeSetup />} />

                    {/* Fallback */}
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Suspense>
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>

      <Toaster position="top-right" richColors closeButton />
    </div>
  );
}
