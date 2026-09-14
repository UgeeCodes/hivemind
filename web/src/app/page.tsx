'use client';

import React, { useEffect, useState } from 'react';

// API Configuration
const API_BASE = process.env.NEXT_PUBLIC_HIVEMIND_CONTROL_PLANE || 'http://localhost:8000';

// Types
interface Machine {
  id: string;
  hostname: string;
  arch: string;
  status: 'online' | 'offline';
}

interface Job {
  id: string;
  command: string;
  status: 'running' | 'completed' | 'failed';
  duration_ms: number;
}

interface ApiToken {
  id: string;
  name: string;
  scopes: string[];
  status: 'active' | 'revoked';
}

interface Sandbox {
  id: string;
  machine_id: string;
  status: 'active' | 'destroying';
}

export default function Dashboard() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [quickRunCmd, setQuickRunCmd] = useState('');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [mRes, jRes, tRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/api/machines`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/jobs`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/tokens`).then(r => r.ok ? r.json() : []),
        fetch(`${API_BASE}/api/sandboxes`).then(r => r.ok ? r.json() : [])
      ]);
      setMachines(mRes);
      setJobs(jRes);
      setTokens(tRes);
      setSandboxes(sRes);
    } catch (err) {
      console.error('Failed to fetch dashboard data', err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleQuickRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickRunCmd) return;
    try {
      await fetch(`${API_BASE}/api/exec`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: quickRunCmd })
      });
      setQuickRunCmd('');
      fetchData();
    } catch (err) {
      console.error('Quick run failed', err);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 font-sans">
      {/* Navbar */}
      <nav className="border-b border-neutral-800 bg-neutral-900/50 p-4 sticky top-0 backdrop-blur">
        <div className="max-w-6xl mx-auto flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-hivemind-600 flex items-center justify-center font-bold text-white">H</div>
            <h1 className="text-xl font-semibold tracking-tight text-white">Hivemind</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-hivemind-500 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-hivemind-500"></span>
            </span>
            <span className="text-sm text-neutral-400">System Online</span>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto p-4 md:p-8 space-y-8">
        
        {/* Quick Run */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
          <h2 className="text-lg font-medium text-white mb-4">Quick Run</h2>
          <form onSubmit={handleQuickRun} className="flex gap-2">
            <input 
              type="text" 
              placeholder="e.g. echo 'Hello World'"
              value={quickRunCmd}
              onChange={(e) => setQuickRunCmd(e.target.value)}
              className="flex-1 bg-neutral-950 border border-neutral-800 rounded px-4 py-2 text-sm focus:outline-none focus:border-hivemind-600"
            />
            <button type="submit" className="bg-hivemind-600 hover:bg-hivemind-700 text-white px-6 py-2 rounded text-sm font-medium transition-colors">
              Execute
            </button>
          </form>
        </section>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          {/* Machines */}
          <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-medium text-white">Machines</h2>
              <span className="text-xs font-mono bg-neutral-800 px-2 py-1 rounded text-neutral-400">
                {machines.filter(m => m.status === 'online').length} online
              </span>
            </div>
            {loading ? <Skeleton /> : (
              <ul className="space-y-3">
                {machines.map(m => (
                  <li key={m.id} className="flex justify-between items-center p-3 bg-neutral-950 rounded border border-neutral-800/50">
                    <div>
                      <div className="text-sm font-medium text-neutral-200">{m.hostname}</div>
                      <div className="text-xs text-neutral-500">{m.arch}</div>
                    </div>
                    <Badge status={m.status === 'online' ? 'success' : 'error'}>{m.status}</Badge>
                  </li>
                ))}
                {machines.length === 0 && <EmptyState text="No machines registered" />}
              </ul>
            )}
          </section>

          {/* Jobs */}
          <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
            <h2 className="text-lg font-medium text-white mb-4">Recent Jobs</h2>
            {loading ? <Skeleton /> : (
              <ul className="space-y-3">
                {jobs.map(j => (
                  <li key={j.id} className="p-3 bg-neutral-950 rounded border border-neutral-800/50">
                    <div className="flex justify-between mb-1">
                      <div className="text-sm font-mono text-neutral-300 truncate max-w-[200px]">{j.command}</div>
                      <Badge status={j.status === 'running' ? 'success' : j.status === 'failed' ? 'error' : 'neutral'}>{j.status}</Badge>
                    </div>
                    <div className="text-xs text-neutral-500">{j.duration_ms}ms</div>
                  </li>
                ))}
                {jobs.length === 0 && <EmptyState text="No recent jobs" />}
              </ul>
            )}
          </section>

          {/* Tokens */}
          <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-medium text-white">API Tokens</h2>
              <a href="/tokens" className="text-xs text-hivemind-500 hover:text-hivemind-400">Manage &rarr;</a>
            </div>
            {loading ? <Skeleton /> : (
              <ul className="space-y-3">
                {tokens.slice(0,3).map(t => (
                  <li key={t.id} className="flex justify-between items-center p-3 bg-neutral-950 rounded border border-neutral-800/50">
                    <div>
                      <div className="text-sm text-neutral-200">{t.name}</div>
                      <div className="text-xs text-neutral-500">{t.scopes.join(', ')}</div>
                    </div>
                    <Badge status={t.status === 'active' ? 'success' : 'error'}>{t.status}</Badge>
                  </li>
                ))}
                {tokens.length === 0 && <EmptyState text="No tokens found" />}
              </ul>
            )}
          </section>

          {/* Sandboxes */}
          <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
            <h2 className="text-lg font-medium text-white mb-4">Sandboxes</h2>
            {loading ? <Skeleton /> : (
              <ul className="space-y-3">
                {sandboxes.map(s => (
                  <li key={s.id} className="flex justify-between items-center p-3 bg-neutral-950 rounded border border-neutral-800/50">
                    <div>
                      <div className="text-sm font-mono text-neutral-300">{s.id.substring(0, 8)}</div>
                      <div className="text-xs text-neutral-500">Machine: {s.machine_id}</div>
                    </div>
                    <Badge status={s.status === 'active' ? 'success' : 'neutral'}>{s.status}</Badge>
                  </li>
                ))}
                {sandboxes.length === 0 && <EmptyState text="No active sandboxes" />}
              </ul>
            )}
          </section>

        </div>
      </main>
    </div>
  );
}

// Sub-components
function Badge({ children, status }: { children: React.ReactNode, status: 'success' | 'error' | 'neutral' }) {
  const colors = {
    success: 'bg-green-500/10 text-green-500 border-green-500/20',
    error: 'bg-red-500/10 text-red-500 border-red-500/20',
    neutral: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/20'
  };
  return (
    <span className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded border ${colors[status]}`}>
      {children}
    </span>
  );
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-3">
      {[1, 2, 3].map(i => (
        <div key={i} className="h-16 bg-neutral-950 rounded border border-neutral-800/50"></div>
      ))}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="p-4 text-center text-sm text-neutral-500 bg-neutral-950/50 rounded border border-neutral-800/50 border-dashed">
      {text}
    </div>
  );
}
