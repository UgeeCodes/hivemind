"use client";

import React, { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_HIVEMIND_CONTROL_PLANE || "http://localhost:8000";

interface Volume {
  name: string;
  owner_id: string;
  machine_id: string | null;
  path: string | null;
  size_bytes: number;
  created_at: number;
}

export default function VolumesPage() {
  const [volumes, setVolumes] = useState<Volume[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");

  const fetchVolumes = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/volumes`);
      if (res.ok) {
        setVolumes(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchVolumes();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/volumes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (res.ok) {
        setName("");
        fetchVolumes();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async (volumeName: string) => {
    if (!confirm(`Delete volume "${volumeName}"? This cannot be undone.`))
      return;
    try {
      await fetch(`${API_BASE}/api/volumes/${volumeName}`, {
        method: "DELETE",
      });
      fetchVolumes();
    } catch (err) {
      console.error(err);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (epoch: number) => {
    return new Date(epoch * 1000).toLocaleString();
  };

  const tabs = [
    { name: "Overview", href: "/", active: false },
    { name: "Sandboxes", href: "/sandboxes", active: false },
    { name: "Volumes", href: "/volumes", active: true },
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

        <div>
          <h1 className="text-2xl font-semibold text-white">Volumes</h1>
          <p className="text-sm text-neutral-500 mt-1">
            Persistent named storage across runs
          </p>
        </div>

        {/* Create Volume Form */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
          <h2 className="text-lg font-medium text-white mb-4">
            Create New Volume
          </h2>
          <form onSubmit={handleCreate} className="flex items-end gap-4">
            <div className="flex-1">
              <label className="block text-sm text-neutral-400 mb-1">
                Volume Name
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full md:w-1/2 bg-neutral-950 border border-neutral-800 rounded px-4 py-2 text-sm focus:outline-none focus:border-emerald-600"
                placeholder="e.g. build-cache"
              />
            </div>
            <button
              type="submit"
              className="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2 rounded text-sm font-medium transition-colors"
            >
              Create Volume
            </button>
          </form>
        </section>

        {/* Volume Table */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-950 border-b border-neutral-800">
              <tr>
                <th className="px-6 py-3 text-neutral-400 font-medium">Name</th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Owner
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Machine
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">Size</th>
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
                    colSpan={6}
                    className="px-6 py-8 text-center text-neutral-500"
                  >
                    Loading volumes...
                  </td>
                </tr>
              ) : volumes.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center">
                    <div className="text-neutral-500">
                      No volumes created yet
                    </div>
                    <div className="text-xs text-neutral-600 mt-1">
                      Create a volume above to get started
                    </div>
                  </td>
                </tr>
              ) : (
                volumes.map((v) => (
                  <tr key={v.name} className="hover:bg-neutral-800/20">
                    <td className="px-6 py-4 font-medium text-neutral-200">
                      {v.name}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-neutral-400">
                      {v.owner_id}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-neutral-400">
                      {v.machine_id || "—"}
                    </td>
                    <td className="px-6 py-4 text-neutral-300">
                      {formatSize(v.size_bytes)}
                    </td>
                    <td className="px-6 py-4 text-xs text-neutral-500">
                      {formatDate(v.created_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleDelete(v.name)}
                        className="text-red-500 hover:text-red-400 text-sm font-medium"
                      >
                        Delete
                      </button>
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
