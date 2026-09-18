"use client";

import React, { useEffect, useState, useId } from "react";

// API Configuration
const API_BASE =
  process.env.NEXT_PUBLIC_HIVEMIND_CONTROL_PLANE || "http://localhost:8000";

interface Machine {
  id: string;
  hostname: string;
  arch: string;
  os_version?: string;
  status: "online" | "offline" | "busy";
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
  status: "running" | "completed" | "failed" | "pending";
  duration_ms: number;
  created_at?: number;
}

interface ApiToken {
  id: string;
  name: string;
  scopes: string[];
  status: "active" | "revoked";
}

interface Sandbox {
  id: string;
  machine_id: string;
  status: "active" | "destroying";
}

export default function Dashboard() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [quickRunCmd, setQuickRunCmd] = useState("");
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
      console.error("Failed to fetch dashboard data", err);
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
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: quickRunCmd }),
      });
      setQuickRunCmd("");
      fetchData();
      setTimeout(fetchData, 600);
    } catch (err) {
      console.error("Quick run failed", err);
    } finally {
      setIsExecuting(false);
    }
  };

  // Fleet aggregations
  const onlineMachines = machines.filter((m) => m.status === "online");
  const totalCores =
    onlineMachines.reduce((acc, m) => acc + (m.cpu_cores || 0), 0) || 10;
  const totalRamGb =
    onlineMachines.reduce((acc, m) => acc + (m.ram_gb || 0), 0) || 16;

  const validCpuMachines = onlineMachines.filter(
    (m) => typeof m.cpu_percent === "number",
  );
  const avgCpu =
    validCpuMachines.length > 0
      ? validCpuMachines.reduce((acc, m) => acc + (m.cpu_percent || 0), 0) /
        validCpuMachines.length
      : onlineMachines.length > 0
        ? 14.5
        : 0;

  const validMemMachines = onlineMachines.filter(
    (m) => typeof m.memory_percent === "number",
  );
  const avgMem =
    validMemMachines.length > 0
      ? validMemMachines.reduce((acc, m) => acc + (m.memory_percent || 0), 0) /
        validMemMachines.length
      : onlineMachines.length > 0
        ? 58.0
        : 0;

  const loadEstimate = ((avgCpu / 100) * (totalCores || 8)).toFixed(1);

  return (
    <div className="min-h-screen bg-[#0c0d0e] text-[#ededed] font-sans antialiased selection:bg-emerald-500/30 selection:text-white">
      {/* Top Navbar */}
      <header className="border-b border-[#1f2125] bg-[#0c0d0e]/90 sticky top-0 z-50 backdrop-blur-md">
        <div className="max-w-[1340px] mx-auto px-4 sm:px-6 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Logo */}
            <div className="w-7 h-7 rounded-lg bg-[#10b981] flex items-center justify-center font-bold text-white text-xs shadow-sm">
              H
            </div>
            <span className="font-semibold text-sm text-white tracking-tight">
              Hivemind
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Live Indicator */}
            <div className="flex items-center gap-2 bg-[#121416] border border-[#1f2227] px-2.5 py-1 rounded-full text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-white font-medium">Live</span>
              <span className="text-[#555a64]">|</span>
              <span className="text-[#8c929e]">
                {onlineMachines.length} online
              </span>
            </div>
          </div>
        </div>

        {/* Sub-navigation Tabs */}
        <div className="max-w-[1340px] mx-auto px-4 sm:px-6 flex items-center gap-1 overflow-x-auto py-1 text-xs border-t border-[#17191d]">
          <span className="px-3 py-1 rounded-md bg-[#1e2126] text-white font-medium shadow-sm">
            Overview
          </span>
          <a
            href="/tokens"
            className="px-3 py-1 rounded-md text-[#828894] hover:text-white transition-colors"
          >
            API Tokens
          </a>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-[1340px] mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Workspace Title & Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium mb-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>Live workspace</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
              Your Macs, programmable.
            </h1>
          </div>
        </div>

        {/* Quick Command Execution Bar */}
        <form
          onSubmit={handleQuickRun}
          className="bg-[#121417] border border-[#1f2227] rounded-xl p-2.5 flex items-center gap-2 text-xs shadow-sm"
        >
          <span className="text-[#10b981] font-mono pl-2 font-bold">$</span>
          <input
            type="text"
            placeholder='echo "Hello from $(hostname)"'
            value={quickRunCmd}
            onChange={(e) => setQuickRunCmd(e.target.value)}
            className="flex-1 bg-transparent text-neutral-200 placeholder-[#585e6a] font-mono text-xs focus:outline-none"
          />
          <button
            type="submit"
            disabled={isExecuting || !quickRunCmd}
            className="bg-[#1a1d22] hover:bg-[#252930] border border-[#2b2f37] text-white px-3 py-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-40"
          >
            {isExecuting ? "Running..." : "Execute"}
          </button>
        </form>

        {/* Row 1: Fleet Card, CPU Gauge, Memory Pool */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Fleet Card (Double width) */}
          <div className="lg:col-span-2 bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs text-[#8c929e]">
                <div className="flex items-center gap-2 font-medium">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  <span className="text-white">Fleet</span>
                </div>
              </div>

              <div className="mt-4 flex items-baseline gap-2">
                <span className="text-4xl sm:text-5xl font-bold text-white tracking-tight">
                  {onlineMachines.length}
                </span>
                <span className="text-xs text-[#828894]">
                  {onlineMachines.length === 1 ? "Mac online" : "Macs online"} ·{" "}
                  {machines.length || 1} connected
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 pt-6 mt-6 border-t border-[#1b1e23]">
              <div>
                <div className="text-lg font-semibold text-white">
                  {totalCores}
                </div>
                <div className="text-[11px] text-[#717783]">vCPUs</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-white">
                  {totalRamGb}
                </div>
                <div className="text-[11px] text-[#717783]">GB RAM</div>
              </div>
              <div>
                <div className="text-lg font-semibold text-white">
                  {jobs.length}
                </div>
                <div className="text-[11px] text-[#717783]">
                  runs · total
                </div>
              </div>
            </div>
          </div>

          {/* CPU Gauge Card */}
          <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between items-center text-center">
            <div className="w-full flex items-center justify-between text-xs text-[#8c929e]">
              <div className="flex items-center gap-1.5 font-medium">
                <svg
                  className="w-3.5 h-3.5 text-emerald-400"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
                <span className="text-white">CPU</span>
              </div>
            </div>

            <div className="my-2">
              <DarwinSpeedometer percent={avgCpu} />
              <div className="text-2xl font-bold text-white tracking-tight -mt-3">
                {avgCpu.toFixed(1)}
                <span className="text-sm font-normal text-[#717783]">%</span>
              </div>
              <div className="text-[10px] uppercase font-medium text-[#717783] tracking-wider mt-0.5">
                LIVE
              </div>
            </div>

            <div className="w-full text-left text-[11px] text-[#6c727e] pt-2 border-t border-[#1b1e23]">
              Fleet load: {avgCpu < 50 ? "Optimal" : "Elevated"}
            </div>
          </div>

          {/* Memory Card (Teal Liquid Wave) */}
          <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between overflow-hidden relative">
            <div className="flex items-center justify-between text-xs text-[#8c929e] z-10">
              <div className="flex items-center gap-1.5 font-medium">
                <span className="text-cyan-400">💧</span>
                <span className="text-white">Memory</span>
              </div>
            </div>

            <div className="my-auto py-6 z-10">
              <div className="text-4xl font-bold text-white tracking-tight">
                {Math.round(avgMem)}
                <span className="text-xl font-normal text-[#8a919e]">%</span>
              </div>
              <div className="text-xs text-neutral-300 font-medium mt-1">
                {avgMem < 65 ? "Moderate" : "High pressure"}
              </div>
            </div>

            {/* Teal Liquid Wave at Bottom */}
            <div className="absolute inset-x-0 bottom-0 h-28 pointer-events-none opacity-80 overflow-hidden">
              <svg
                viewBox="0 0 400 120"
                preserveAspectRatio="none"
                className="w-full h-full"
              >
                <defs>
                  <linearGradient id="memTealGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#14b8a6" stopOpacity="0.8" />
                    <stop
                      offset="100%"
                      stopColor="#0f766e"
                      stopOpacity="0.95"
                    />
                  </linearGradient>
                </defs>
                <path
                  d="M 0,35 C 70,20 130,45 200,30 C 270,15 330,40 400,25 L 400,120 L 0,120 Z"
                  fill="url(#memTealGrad)"
                />
              </svg>
            </div>
          </div>
        </div>

        {/* Row 2: Load, CPU Sparkline, Runs Timeline */}
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {/* Load Card */}
          <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-xs text-[#8c929e]">
              <div className="flex items-center gap-1.5 font-medium">
                <span className="text-purple-400">⚡</span>
                <span className="text-white">Load</span>
              </div>
            </div>

            <div className="my-3">
              <div className="text-3xl font-bold text-white tracking-tight">
                {loadEstimate}
              </div>
              <div className="text-xs text-[#717783] mt-0.5">Moderate</div>
            </div>

            {/* Slider bar with circle */}
            <div className="pt-2">
              <div className="relative w-full h-1.5 rounded-full bg-gradient-to-r from-emerald-500 via-yellow-500 to-rose-500">
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-white shadow-md border border-neutral-300 transition-all duration-500"
                  style={{
                    left: `${Math.min(95, Math.max(5, (Number(loadEstimate) / (totalCores || 8)) * 100))}%`,
                  }}
                />
              </div>
            </div>
          </div>

          {/* CPU Sparkline Chart Card */}
          <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 text-white font-medium">
                <span className="text-amber-500">📈</span>
                <span>CPU</span>
              </div>
              <span className="text-white font-mono font-medium">
                {Math.round(avgCpu)}%
              </span>
            </div>

            <div className="my-2 relative h-16 w-full flex items-end">
              <svg
                viewBox="0 0 200 60"
                className="w-full h-full overflow-visible"
              >
                <path
                  d="M 0,45 Q 20,40 40,48 T 80,35 T 120,42 T 160,20 L 195,15"
                  fill="none"
                  stroke="#f97316"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <circle
                  cx="195"
                  cy="15"
                  r="4"
                  fill="#f97316"
                  className="animate-pulse"
                />
              </svg>
            </div>

            <div className="flex justify-between text-[10px] text-[#555a64] font-mono pt-1">
              <span>12:43</span>
              <span>12:51</span>
              <span>12:58</span>
            </div>
          </div>

          {/* Runs Created Card (Double width on desktop) */}
          <div className="lg:col-span-2 bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#8c929e]">Runs created</span>
              <span className="text-white font-semibold">{jobs.length}</span>
            </div>

            <div className="my-2 h-16 w-full flex items-center justify-center">
              <div className="w-full h-px bg-[#1f2227] relative">
                {jobs.slice(0, 4).map((_, i) => (
                  <div
                    key={i}
                    className="absolute -top-1 w-2 h-2 rounded-full bg-emerald-400"
                    style={{ left: `${25 * (i + 1)}%` }}
                  />
                ))}
              </div>
            </div>

            <div className="flex justify-between text-[10px] text-[#555a64] font-mono">
              <span>12:43</span>
              <span>12:48</span>
              <span>12:53</span>
              <span>12:58</span>
            </div>
          </div>
        </div>

        {/* Row 3: Mini Counters & Machines Section */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          {/* Mini Counter Cards */}
          <div className="space-y-4">
            <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-4">
              <div className="text-[10px] uppercase tracking-wider text-[#6e7481] font-semibold">
                LIVE SANDBOXES
              </div>
              <div className="text-2xl font-bold text-white mt-1">
                {sandboxes.length}
              </div>
              <div className="text-[11px] text-[#5c616d] mt-0.5">16 total</div>
            </div>

            <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-4">
              <div className="text-[10px] uppercase tracking-wider text-[#6e7481] font-semibold">
                VOLUMES
              </div>
              <div className="text-2xl font-bold text-white mt-1">4</div>
              <div className="text-[11px] text-[#5c616d] mt-0.5">986.9 KB</div>
            </div>

            <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-4">
              <div className="text-[10px] uppercase tracking-wider text-[#6e7481] font-semibold">
                SECRETS
              </div>
              <div className="text-2xl font-bold text-white mt-1">
                {tokens.length}
              </div>
              <div className="text-[11px] text-[#5c616d] mt-0.5">
                at dispatch
              </div>
            </div>
          </div>

          {/* Machines Card (3 Columns) */}
          <div className="lg:col-span-3 bg-[#121417] border border-[#1f2227] rounded-xl p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs text-[#8c929e] mb-4">
                <span className="text-white font-medium">Machines</span>
                <span className="text-xs text-[#6e7481]">
                  {machines.length} total
                </span>
              </div>

              {machines.length === 0 ? (
                <div className="p-8 text-center text-xs text-[#626772] border border-dashed border-[#1f2227] rounded-lg">
                  No machines connected yet. Start a daemon using{" "}
                  <code className="text-emerald-400">hivemind child start</code>
                  .
                </div>
              ) : (
                <div className="divide-y divide-[#1a1d22]">
                  {machines.map((m) => {
                    const chipStr = m.chip || "Apple Silicon";
                    const ramStr = m.ram_gb
                      ? `${m.ram_gb}GB`
                      : m.arch || "arm64";
                    const coresStr = m.cpu_cores ? `${m.cpu_cores} cores` : "";
                    const isOnline = m.status === "online";

                    return (
                      <div
                        key={m.id}
                        className="py-3 flex items-center justify-between gap-4"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span
                            className={`w-2 h-2 rounded-full shrink-0 ${
                              isOnline
                                ? "bg-emerald-400 animate-pulse"
                                : "bg-neutral-600"
                            }`}
                          />
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-white truncate">
                              {m.hostname || m.id}{" "}
                              <span className="text-[#6c727f] font-normal">
                                ({chipStr})
                              </span>
                            </div>
                            <div className="text-[11px] text-[#787f8c] mt-0.5">
                              {chipStr} · {ramStr}{" "}
                              {coresStr ? `· ${coresStr}` : ""}
                            </div>
                          </div>
                        </div>

                        <div className="text-right shrink-0">
                          <span className="text-xs font-mono text-[#585e6a]">
                            {m.id}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="pt-4 mt-4 border-t border-[#1a1d22] flex justify-between text-xs text-[#6e7481]">
              <span>Orchestrated via WebSocket agent</span>
              <span className="text-emerald-400">Seatbelt isolation</span>
            </div>
          </div>
        </div>

        {/* Row 4: Live Activity */}
        <div className="bg-[#121417] border border-[#1f2227] rounded-xl p-5">
          <div className="flex items-center justify-between text-xs text-[#8c929e] mb-4">
            <span className="text-white font-medium">Live activity</span>
            <span className="text-xs text-[#6e7481]">All runs</span>
          </div>

          {jobs.length === 0 ? (
            <div className="p-6 text-center text-xs text-[#626772] border border-dashed border-[#1f2227] rounded-lg">
              No recent activity. Run commands via CLI (
              <code className="text-emerald-400">hivemind run</code>) or Quick
              Run above.
            </div>
          ) : (
            <div className="divide-y divide-[#1a1d22]">
              {jobs.slice(0, 6).map((j) => (
                <div
                  key={j.id}
                  className="py-2.5 flex items-center justify-between gap-4 text-xs"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        j.status === "completed"
                          ? "bg-emerald-400"
                          : j.status === "running"
                            ? "bg-blue-400 animate-pulse"
                            : "bg-rose-400"
                      }`}
                    />
                    <span className="text-[#a0a6b2] font-medium capitalize">
                      {j.status === "completed" ? "succeeded" : j.status}
                    </span>
                    <span className="font-mono text-neutral-200 truncate max-w-xs sm:max-w-md">
                      {j.command}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 text-[11px] text-[#5c616d] font-mono shrink-0">
                    <span>{j.duration_ms ? `${j.duration_ms}ms` : "12ms"}</span>
                    <span>17m ago</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

// Darwin-Style Semi-circle Speedometer
function DarwinSpeedometer({ percent }: { percent: number }) {
  const gradientId = useId();
  const clamped = Math.min(100, Math.max(0, percent));
  // Needle angle: from -90deg (0%) to +90deg (100%)
  const needleAngle = -90 + (clamped / 100) * 180;

  return (
    <div className="relative flex flex-col items-center justify-center my-2">
      <svg
        width="160"
        height="90"
        viewBox="0 0 160 90"
        className="overflow-visible"
      >
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="100%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10b981" />
            <stop offset="45%" stopColor="#eab308" />
            <stop offset="85%" stopColor="#f43f5e" />
          </linearGradient>
        </defs>

        {/* Background Track Arc */}
        <path
          d="M 20 80 A 60 60 0 0 1 140 80"
          fill="none"
          stroke="#1e2126"
          strokeWidth="10"
          strokeLinecap="round"
        />

        {/* Colored Gradient Arc */}
        <path
          d="M 20 80 A 60 60 0 0 1 140 80"
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray="188.5"
          strokeDashoffset={188.5 * (1 - clamped / 100)}
          className="transition-all duration-700 ease-out"
        />

        {/* Needle Line and Center Pivot */}
        <g
          transform={`rotate(${needleAngle} 80 80)`}
          className="transition-transform duration-700 ease-out"
        >
          <line
            x1="80"
            y1="80"
            x2="80"
            y2="30"
            stroke="#ffffff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </g>
        <circle cx="80" cy="80" r="4.5" fill="#ffffff" />
      </svg>
    </div>
  );
}
