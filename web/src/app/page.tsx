'use client';

import React, { useEffect, useState } from 'react';

// API Configuration
const API_BASE = process.env.NEXT_PUBLIC_HIVEMIND_CONTROL_PLANE || 'http://localhost:8000';

// Types
interface Machine {
  id: string;
  hostname: string;
  arch: string;
  os_version?: string;
  status: 'online' | 'offline' | 'busy';
  chip?: string;
  cpu_cores?: number;
  ram_gb?: number;
  cpu_percent?: number;
  memory_percent?: number;
  tags?: string[];
  last_seen_at?: number;
}

interface Job {
  id: string;
  command: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
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
  const [isExecuting, setIsExecuting] = useState(false);

  const fetchData = async () => {
    try {
      const [mRes, jRes, tRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/api/machines`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/jobs`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/tokens`).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/sandboxes`).then((r) => (r.ok ? r.json() : [])),
      ]);
      setMachines(mRes);
      setJobs(jRes);
      setTokens(tRes);
      setSandboxes(sRes);
    } catch (err) {
      console.error('Failed to fetch dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleQuickRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickRunCmd || isExecuting) return;
    setIsExecuting(true);
    try {
      await fetch(`${API_BASE}/api/exec`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: quickRunCmd }),
      });
      setQuickRunCmd('');
      fetchData();
      setTimeout(fetchData, 600);
    } catch (err) {
      console.error('Quick run failed', err);
    } finally {
      setIsExecuting(false);
    }
  };

  // Fleet aggregations
  const onlineMachines = machines.filter((m) => m.status === 'online');
  const totalCores = onlineMachines.reduce((acc, m) => acc + (m.cpu_cores || 0), 0);
  const totalRamGb = onlineMachines.reduce((acc, m) => acc + (m.ram_gb || 0), 0);

  const validCpuMachines = onlineMachines.filter((m) => typeof m.cpu_percent === 'number');
  const avgCpu = validCpuMachines.length > 0
    ? validCpuMachines.reduce((acc, m) => acc + (m.cpu_percent || 0), 0) / validCpuMachines.length
    : 0;

  const validMemMachines = onlineMachines.filter((m) => typeof m.memory_percent === 'number');
  const avgMem = validMemMachines.length > 0
    ? validMemMachines.reduce((acc, m) => acc + (m.memory_percent || 0), 0) / validMemMachines.length
    : 0;

  const usedRamGb = (totalRamGb * avgMem) / 100;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 font-sans selection:bg-emerald-500 selection:text-black">
      {/* Top Navbar */}
      <nav className="border-b border-neutral-800/80 bg-neutral-900/60 p-4 sticky top-0 z-50 backdrop-blur-md">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center font-bold text-white shadow-lg shadow-emerald-900/40">
                H
              </div>
              <span className="text-xl font-semibold tracking-tight text-white">Hivemind</span>
            </div>
            <div className="hidden sm:flex items-center gap-1 text-sm">
              <span className="px-3 py-1 rounded-md bg-neutral-800 text-white font-medium">Dashboard</span>
              <a href="/tokens" className="px-3 py-1 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-800/50 transition-colors">API Tokens</a>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 px-3 py-1.5 rounded-full">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
              </span>
              <span className="text-xs font-medium text-neutral-300">
                {onlineMachines.length} {onlineMachines.length === 1 ? 'Mac' : 'Macs'} Online
              </span>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto p-4 md:p-8 space-y-8">
        
        {/* Hero Section */}
        <section className="flex flex-col md:flex-row md:items-end justify-between gap-4 pt-2">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium mb-3">
              <span>●</span> Apple Silicon Fleet Runtime
            </div>
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
              Your Macs, programmable.
            </h1>
            <p className="text-neutral-400 text-sm sm:text-base mt-1.5 max-w-2xl">
              Cluster orchestration, sandboxed execution, and live hardware telemetry across distributed Apple Silicon hardware.
            </p>
          </div>
        </section>

        {/* Fleet Metrics & Resource Gauges Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Total Online Macs */}
          <div className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-5 flex flex-col justify-between hover:border-neutral-700 transition-colors">
            <div className="flex items-center justify-between text-neutral-400 text-xs font-medium">
              <span>ACTIVE FLEET</span>
              <span className="text-emerald-400 font-mono text-[11px]">RUNNING</span>
            </div>
            <div className="mt-3">
              <div className="text-3xl font-bold text-white tracking-tight">
                {onlineMachines.length}
                <span className="text-sm font-normal text-neutral-500 ml-1">/ {machines.length}</span>
              </div>
              <div className="text-xs text-neutral-400 mt-1">
                {onlineMachines.length === 1 ? '1 machine available' : `${onlineMachines.length} machines available`}
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-neutral-800/60 flex items-center justify-between text-xs text-neutral-400">
              <span>Capacity</span>
              <span className="text-neutral-200 font-medium">
                {machines.length > 0 ? `${Math.round((onlineMachines.length / machines.length) * 100)}% online` : '0%'}
              </span>
            </div>
          </div>

          {/* Aggregate Compute Cores */}
          <div className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-5 flex flex-col justify-between hover:border-neutral-700 transition-colors">
            <div className="flex items-center justify-between text-neutral-400 text-xs font-medium">
              <span>TOTAL CORES</span>
              <span className="text-blue-400 font-mono text-[11px]">ARM64</span>
            </div>
            <div className="mt-3">
              <div className="text-3xl font-bold text-white tracking-tight">
                {totalCores}
                <span className="text-sm font-normal text-neutral-500 ml-1">Cores</span>
              </div>
              <div className="text-xs text-neutral-400 mt-1">
                High-performance Apple Silicon execution units
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-neutral-800/60 flex items-center justify-between text-xs text-neutral-400">
              <span>Architecture</span>
              <span className="text-neutral-200 font-medium">Apple Silicon</span>
            </div>
          </div>

          {/* Average CPU Gauge Card */}
          <div className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-5 flex flex-col justify-between hover:border-neutral-700 transition-colors">
            <div className="flex items-center justify-between text-neutral-400 text-xs font-medium">
              <span>FLEET CPU USAGE</span>
              <span className="font-mono text-emerald-400 text-[11px]">{Math.round(avgCpu)}% AVG</span>
            </div>
            <div className="mt-2 flex items-center justify-center">
              <SemiCircleGauge percent={avgCpu} label="CPU Load" />
            </div>
            <div className="mt-2 pt-3 border-t border-neutral-800/60 flex items-center justify-between text-xs text-neutral-400">
              <span>Load Status</span>
              <span className="text-emerald-400 font-medium">
                {avgCpu < 50 ? 'Optimal' : avgCpu < 80 ? 'Moderate' : 'Heavy'}
              </span>
            </div>
          </div>

          {/* Aggregate Unified Memory Card */}
          <div className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-5 flex flex-col justify-between hover:border-neutral-700 transition-colors">
            <div className="flex items-center justify-between text-neutral-400 text-xs font-medium">
              <span>UNIFIED MEMORY</span>
              <span className="font-mono text-cyan-400 text-[11px]">{Math.round(avgMem)}% USED</span>
            </div>
            <div className="mt-3">
              <div className="text-3xl font-bold text-white tracking-tight">
                {totalRamGb}
                <span className="text-sm font-normal text-neutral-500 ml-1">GB Pool</span>
              </div>
              <div className="text-xs text-neutral-400 mt-1 font-mono">
                {usedRamGb.toFixed(1)} GB used · {(totalRamGb - usedRamGb).toFixed(1)} GB free
              </div>
            </div>
            <div className="mt-3">
              <div className="w-full bg-neutral-800 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-emerald-500 to-cyan-500 h-2 rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, avgMem))}%` }}
                />
              </div>
            </div>
            <div className="mt-3 pt-2 border-t border-neutral-800/60 flex items-center justify-between text-xs text-neutral-400">
              <span>Memory Pressure</span>
              <span className="text-neutral-200 font-medium">
                {avgMem < 70 ? 'Normal (Low Pressure)' : 'Elevated'}
              </span>
            </div>
          </div>
        </div>

        {/* Quick Run Box */}
        <section className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-medium text-white">Quick Run</h2>
              <span className="text-xs text-neutral-400">Execute command across the idlest node</span>
            </div>
            <span className="text-xs font-mono text-neutral-500">Seatbelt isolated</span>
          </div>
          <form onSubmit={handleQuickRun} className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <span className="absolute left-3.5 top-2.5 text-neutral-500 font-mono text-sm">$</span>
              <input
                type="text"
                placeholder='echo "Hello from $(hostname)"'
                value={quickRunCmd}
                onChange={(e) => setQuickRunCmd(e.target.value)}
                className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-8 pr-4 py-2.5 text-sm font-mono text-neutral-200 placeholder-neutral-600 focus:outline-none focus:border-emerald-500 transition-colors"
              />
            </div>
            <button
              type="submit"
              disabled={isExecuting || !quickRunCmd}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-2.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap shadow-sm shadow-emerald-900/30"
            >
              {isExecuting ? 'Running...' : 'Run Command'}
            </button>
          </form>
        </section>

        {/* Machines Fleet Section (Darwin / Modal-for-Mac style) */}
        <section className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-6">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h2 className="text-lg font-semibold text-white tracking-tight">Machine Fleet</h2>
              <p className="text-xs text-neutral-400 mt-0.5">Hardware specifications and live telemetry per node</p>
            </div>
            <span className="text-xs font-mono bg-neutral-800/80 border border-neutral-700/50 px-2.5 py-1 rounded-full text-neutral-300">
              {onlineMachines.length} online
            </span>
          </div>

          {loading ? (
            <Skeleton count={2} />
          ) : machines.length === 0 ? (
            <EmptyState text="No machines connected yet. Connect a Mac with `hivemind child start`." />
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {machines.map((m) => {
                const isOnline = m.status === 'online';
                const chipName = m.chip || 'Apple Silicon';
                const ramString = m.ram_gb ? `${m.ram_gb} GB Unified RAM` : (m.arch || 'arm64');
                const coresString = m.cpu_cores ? `${m.cpu_cores} Cores` : '';

                return (
                  <div
                    key={m.id}
                    className="p-5 bg-neutral-950/80 rounded-xl border border-neutral-800/80 hover:border-neutral-700 transition-all flex flex-col justify-between"
                  >
                    <div>
                      {/* Top row: Hostname & status */}
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white text-base truncate">
                              {m.hostname || m.id}
                            </span>
                          </div>
                          {/* Hardware subtitle */}
                          <div className="flex items-center gap-2 mt-1 text-xs text-neutral-400">
                            <span className="text-neutral-300 font-medium">{chipName}</span>
                            <span>·</span>
                            <span>{ramString}</span>
                            {coresString && (
                              <>
                                <span>·</span>
                                <span>{coresString}</span>
                              </>
                            )}
                          </div>
                        </div>
                        <Badge status={isOnline ? 'success' : 'error'}>
                          <span className="flex items-center gap-1.5">
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'
                              }`}
                            />
                            {m.status}
                          </span>
                        </Badge>
                      </div>

                      {/* Telemetry Progress Bars */}
                      <div className="space-y-3 mt-5 pt-4 border-t border-neutral-800/60">
                        <div>
                          <div className="flex justify-between text-xs text-neutral-400 mb-1.5">
                            <span className="flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-sm bg-emerald-500" />
                              CPU Utilization
                            </span>
                            <span className="font-mono text-neutral-200">
                              {typeof m.cpu_percent === 'number' ? `${Math.round(m.cpu_percent)}%` : '—'}
                            </span>
                          </div>
                          <div className="w-full bg-neutral-800/70 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(0, m.cpu_percent || 0))}%` }}
                            />
                          </div>
                        </div>

                        <div>
                          <div className="flex justify-between text-xs text-neutral-400 mb-1.5">
                            <span className="flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-sm bg-blue-500" />
                              Memory Pressure
                            </span>
                            <span className="font-mono text-neutral-200">
                              {typeof m.memory_percent === 'number' ? `${Math.round(m.memory_percent)}%` : '—'}
                            </span>
                          </div>
                          <div className="w-full bg-neutral-800/70 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(100, Math.max(0, m.memory_percent || 0))}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Footer Info: Machine ID & Tags */}
                    <div className="mt-5 pt-3 border-t border-neutral-800/60 flex items-center justify-between text-[11px] text-neutral-500">
                      <span className="font-mono">{m.id}</span>
                      <div className="flex gap-1.5">
                        {m.tags && m.tags.length > 0 ? (
                          m.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 bg-neutral-800 rounded text-neutral-400">
                              {t}
                            </span>
                          ))
                        ) : (
                          <span>{m.os_version ? `macOS ${m.os_version}` : 'darwin'}</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Jobs, Tokens, Sandboxes Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* Jobs */}
          <section className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-base font-semibold text-white">Recent Jobs</h2>
              <span className="text-xs text-neutral-500 font-mono">{jobs.length} total</span>
            </div>
            {loading ? (
              <Skeleton count={3} />
            ) : (
              <ul className="space-y-2.5">
                {jobs.slice(0, 6).map((j) => (
                  <li key={j.id} className="p-3 bg-neutral-950/80 rounded-lg border border-neutral-800/60">
                    <div className="flex justify-between items-start gap-2 mb-1">
                      <div className="text-xs font-mono text-neutral-200 truncate flex-1">
                        {j.command}
                      </div>
                      <Badge
                        status={
                          j.status === 'running'
                            ? 'success'
                            : j.status === 'failed'
                            ? 'error'
                            : 'neutral'
                        }
                      >
                        {j.status}
                      </Badge>
                    </div>
                    <div className="text-[11px] text-neutral-500 font-mono">
                      {j.duration_ms ? `${j.duration_ms}ms` : 'pending'}
                    </div>
                  </li>
                ))}
                {jobs.length === 0 && <EmptyState text="No recent jobs" />}
              </ul>
            )}
          </section>

          {/* Tokens */}
          <section className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-base font-semibold text-white">API Tokens</h2>
              <a href="/tokens" className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors">
                Manage &rarr;
              </a>
            </div>
            {loading ? (
              <Skeleton count={3} />
            ) : (
              <ul className="space-y-2.5">
                {tokens.slice(0, 4).map((t) => (
                  <li
                    key={t.id}
                    className="flex justify-between items-center p-3 bg-neutral-950/80 rounded-lg border border-neutral-800/60"
                  >
                    <div>
                      <div className="text-xs font-medium text-neutral-200">{t.name}</div>
                      <div className="text-[11px] text-neutral-500 font-mono mt-0.5">{t.scopes.join(', ')}</div>
                    </div>
                    <Badge status={t.status === 'active' ? 'success' : 'error'}>{t.status}</Badge>
                  </li>
                ))}
                {tokens.length === 0 && <EmptyState text="No tokens found" />}
              </ul>
            )}
          </section>

          {/* Sandboxes */}
          <section className="bg-neutral-900/90 border border-neutral-800/80 rounded-xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-base font-semibold text-white">Sandboxes</h2>
              <span className="text-xs text-neutral-500 font-mono">{sandboxes.length} active</span>
            </div>
            {loading ? (
              <Skeleton count={3} />
            ) : (
              <ul className="space-y-2.5">
                {sandboxes.slice(0, 4).map((s) => (
                  <li
                    key={s.id}
                    className="flex justify-between items-center p-3 bg-neutral-950/80 rounded-lg border border-neutral-800/60"
                  >
                    <div>
                      <div className="text-xs font-mono text-neutral-200">{s.id.substring(0, 12)}</div>
                      <div className="text-[11px] text-neutral-500 font-mono mt-0.5">Machine: {s.machine_id}</div>
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

// Semi-circle SVG Gauge Component
function SemiCircleGauge({ percent, label }: { percent: number; label: string }) {
  const clamped = Math.min(100, Math.max(0, percent));
  // Semi-circle arc length for radius 56 = pi * 56 ≈ 175.93
  const radius = 56;
  const circumference = Math.PI * radius;
  const strokeDashoffset = circumference * (1 - clamped / 100);

  return (
    <div className="relative flex flex-col items-center justify-center my-1">
      <svg width="150" height="90" viewBox="0 0 150 90" className="overflow-visible">
        {/* Background Track */}
        <path
          d="M 19 80 A 56 56 0 0 1 131 80"
          fill="none"
          stroke="#262626"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Active Arc */}
        <path
          d="M 19 80 A 56 56 0 0 1 131 80"
          fill="none"
          stroke="url(#cpuGaugeGradient)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className="transition-all duration-700 ease-out"
        />
        <defs>
          <linearGradient id="cpuGaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="70%" stopColor="#22c55e" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute top-10 flex flex-col items-center">
        <span className="text-2xl font-bold font-mono text-white tracking-tight">
          {Math.round(clamped)}%
        </span>
        <span className="text-[10px] text-neutral-400 uppercase tracking-wider -mt-0.5">{label}</span>
      </div>
    </div>
  );
}

// Sub-components
function Badge({
  children,
  status,
}: {
  children: React.ReactNode;
  status: 'success' | 'error' | 'neutral';
}) {
  const colors = {
    success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    error: 'bg-red-500/10 text-red-400 border-red-500/20',
    neutral: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/20',
  };
  return (
    <span
      className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full border ${colors[status]}`}
    >
      {children}
    </span>
  );
}

function Skeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="animate-pulse space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="h-16 bg-neutral-950/80 rounded-xl border border-neutral-800/50"></div>
      ))}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="p-6 text-center text-xs text-neutral-500 bg-neutral-950/40 rounded-xl border border-neutral-800/60 border-dashed">
      {text}
    </div>
  );
}
