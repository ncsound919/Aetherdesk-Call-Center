import { useEffect, useState } from 'react';
import { api } from '../lib/api';

interface Subscription {
  plan_name: string;
  max_concurrent_calls: number;
  max_agents: number;
  active: boolean;
  stripe_customer_id?: string;
  stripe_subscription_id?: string;
  plan_ends_at?: string;
}

const PLANS = [
  { id: 'starter', name: 'Starter', price: 49, calls: 2, agents: 2, features: ['Basic scripts', 'CSV import', 'Email support'] },
  { id: 'pro', name: 'Pro', price: 149, calls: 10, agents: 10, features: ['Templates', 'A/B testing', 'Analytics', 'Priority support'] },
  { id: 'enterprise', name: 'Enterprise', price: 499, calls: 50, agents: 50, features: ['Custom scripts', 'API access', 'Dedicated support', 'SLA'] },
];

export default function BillingPage() {
  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionPlan, setActionPlan] = useState<string | null>(null);

  useEffect(() => {
    api.getSubscription()
      .then(setSub)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleUpgrade = async (planId: string) => {
    setActionPlan(planId);
    setError('');
    try {
      const result: any = await api.createCheckout(planId);
      if (result.checkout_url) window.location.href = result.checkout_url;
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionPlan(null);
    }
  };

  const handlePortal = async () => {
    setError('');
    try {
      const result: any = await api.createPortal();
      if (result.portal_url) window.location.href = result.portal_url;
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-white">Loading billing...</div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-5xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-white">Billing</h1>
          <p className="text-gray-400 mt-2">Manage your subscription and plan.</p>
        </header>

        {error && (
          <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300">{error}</div>
        )}

        {sub && (
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 p-6 mb-8">
            <div className="flex justify-between items-center">
              <div>
                <div className="text-sm text-gray-400">Current plan</div>
                <div className="text-2xl font-bold text-white capitalize">{sub.plan_name}</div>
                {sub.plan_ends_at && <div className="text-gray-500 text-sm mt-1">Renews {new Date(sub.plan_ends_at).toLocaleDateString()}</div>}
              </div>
              {sub.active && (
                <button onClick={handlePortal} className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm">
                  Manage in Stripe Portal
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4 mt-6">
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-sm text-gray-400">Concurrent calls</div>
                <div className="text-xl font-semibold text-white">{sub.max_concurrent_calls}</div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-sm text-gray-400">Max agents</div>
                <div className="text-xl font-semibold text-white">{sub.max_agents}</div>
              </div>
            </div>
          </div>
        )}

        <h2 className="text-xl font-semibold text-white mb-4">Available plans</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((p) => {
            const isCurrent = sub?.plan_name?.toLowerCase() === p.id;
            return (
              <div key={p.id} className={`bg-white/5 backdrop-blur-lg rounded-2xl border ${isCurrent ? 'border-purple-500' : 'border-white/10'} p-6`}>
                <h3 className="text-lg font-semibold text-white">{p.name}</h3>
                <div className="mt-2 mb-4">
                  <span className="text-3xl font-bold text-white">${p.price}</span>
                  <span className="text-gray-400 text-sm">/month</span>
                </div>
                <ul className="space-y-2 mb-6">
                  <li className="text-gray-300 text-sm">{p.calls} concurrent calls</li>
                  <li className="text-gray-300 text-sm">{p.agents} agents</li>
                  {p.features.map((f) => (
                    <li key={f} className="text-gray-400 text-sm flex items-center gap-2">
                      <span className="text-purple-400">✓</span> {f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => handleUpgrade(p.id)}
                  disabled={isCurrent || actionPlan === p.id}
                  className={`w-full py-2 rounded-lg font-semibold text-sm ${isCurrent ? 'bg-purple-600/30 text-purple-200 cursor-not-allowed' : 'bg-purple-600 hover:bg-purple-700 text-white'} disabled:opacity-50`}
                >
                  {isCurrent ? 'Current plan' : (actionPlan === p.id ? 'Loading...' : `Upgrade to ${p.name}`)}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}