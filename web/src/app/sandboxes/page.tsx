"use client";

import React, { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_HIVEMIND_CONTROL_PLANE || "http://localhost:8000";

interface Sandbox {
  id: string;
  machine_id: string;
  name: string | null;
  dir_path: string;
  status: "active" | "destroyed";
  created_at: number;
  last_used_at: number | null;
}

export default function SandboxesPage() {
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"active" | "all">("active");

  const fetchSandboxes = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/sandboxes?include_destroyed=${filter === "all"}`
      );
      if (res.ok) {
        setSandboxes(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchSandboxes();
    const interval = setInterval(fetchSandboxes, 3000);
    return () => clearInterval(interval);
  }, [filter]);

  const handleDestroy = async (id: string) => {
    if (!confirm("Are you sure you want to destroy this sandbox?")) return;
    try {
      await fetch(`${API_BASE}/api/sandboxes/${id}`, { method: "DELETE" });
      fetchSandboxes();
    } catch (err) {
      console.error(err);
    }
  };

  const formatDate = (epoch: number) => {
    return new Date(epoch * 1000).toLocaleString();
  };

  const tabs = [
    { name: "Overview", href: "/", active: false },
    { name: "Sandboxes", href: "/sandboxes", active: true },
    { name: "Volumes", href: "/volumes", active: false },
    { name: "API Tokens", href: "/tokens", active: false },
  ];

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 font-sans p-4 md:p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Sub-navigation */}
        <div className="flex items-center gap-1 border-b border-neutral-800 pb-3">
          {tabs.map((tab) => (
            <a
              key={tab.name}
              href={tab.href}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                tab.active
                  ? "bg-[#1e2126] text-white shadow-sm"
                  : "text-[#828894] hover:text-white"
              }`}
            >
              {tab.name}
            </a>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-white">Sandboxes</h1>
            <p className="text-sm text-neutral-500 mt-1">
              Isolated execution environments across your Mac fleet
            </p>
          </div>
          <div className="flex items-center bg-neutral-900 border border-neutral-800 rounded-lg p-0.5 text-xs">
            <button
              onClick={() => setFilter("active")}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                filter === "active"
                  ? "bg-neutral-800 text-white shadow-sm"
                  : "text-neutral-400 hover:text-white"
              }`}
            >
              Active
            </button>
            <button
              onClick={() => setFilter("all")}
              className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                filter === "all"
                  ? "bg-neutral-800 text-white shadow-sm"
                  : "text-neutral-400 hover:text-white"
              }`}
            >
              All
            </button>
          </div>
        </div>

        {/* Sandbox Table */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-950 border-b border-neutral-800">
              <tr>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Sandbox ID
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Machine
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">Name</th>
                <th className="px-6 py-3 text-neutral-400 font-medium">Path</th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Status
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Created
                </th>
                <th className="px-6 py-3 text-right text-neutral-400 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-800">
              {loading ? (
                <tr>
                  <td
                    colSpan={7}
                    className="px-6 py-8 text-center text-neutral-500"
                  >
                    Loading sandboxes...
                  </td>
                </tr>
              ) : sandboxes.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center">
                    <div className="text-neutral-500">
                      No sandboxes created yet
                    </div>
                    <div className="text-xs text-neutral-600 mt-1">
                      Run a command with{" "}
                      <code className="text-emerald-400">
                        --sandbox &lt;id&gt;
                      </code>{" "}
                      to create one
                    </div>
                  </td>
                </tr>
              ) : (
                sandboxes.map((s) => (
                  <tr key={s.id} className="hover:bg-neutral-800/20">
                    <td className="px-6 py-4 font-mono text-xs text-neutral-300">
                      {s.id}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-neutral-400">
                      {s.machine_id}
                    </td>
                    <td className="px-6 py-4 text-neutral-300">
                      {s.name || "—"}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-neutral-500 max-w-[200px] truncate">
                      {s.dir_path}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded border ${
                          s.status === "active"
                            ? "bg-green-500/10 text-green-500 border-green-500/20"
                            : "bg-neutral-500/10 text-neutral-500 border-neutral-500/20"
                        }`}
                      >
                        {s.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-neutral-500">
                      {formatDate(s.created_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {s.status === "active" && (
                        <button
                          onClick={() => handleDestroy(s.id)}
                          className="text-red-500 hover:text-red-400 text-sm font-medium"
                        >
                          Destroy
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
