"use client";

import React, { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_HIVEMIND_CONTROL_PLANE || "http://localhost:8000";

interface Token {
  id: string;
  prefix: string;
  name: string;
  scopes: string[];
  created_at: string;
  status: "active" | "revoked";
}

export default function TokensPage() {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [loading, setLoading] = useState(true);

  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Form state
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState({ admin: false, run: true, read: true });

  const fetchTokens = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/tokens`);
      if (res.ok) {
        setTokens(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchTokens();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const selectedScopes = Object.entries(scopes)
      .filter(([_, v]) => v)
      .map(([k]) => k);
    try {
      const res = await fetch(`${API_BASE}/api/tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, scopes: selectedScopes }),
      });
      if (res.ok) {
        const data = await res.json();
        setCreatedToken(data.token);
        setCopied(false);
      }
      setName("");
      fetchTokens();
    } catch (err) {
      console.error(err);
    }
  };

  const handleRevoke = async (id: string) => {
    if (!confirm("Are you sure you want to revoke this token?")) return;
    try {
      await fetch(`${API_BASE}/api/tokens/${id}/revoke`, { method: "POST" });
      fetchTokens();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-200 font-sans p-4 md:p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        <div className="flex items-center gap-1 border-b border-neutral-800 pb-3">
          {[
            { name: "Overview", href: "/" },
            { name: "Sandboxes", href: "/sandboxes" },
            { name: "Volumes", href: "/volumes" },
            { name: "API Tokens", href: "/tokens" },
          ].map((tab) => (
            <a
              key={tab.name}
              href={tab.href}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                tab.name === "API Tokens"
                  ? "bg-[#1e2126] text-white shadow-sm"
                  : "text-[#828894] hover:text-white"
              }`}
            >
              {tab.name}
            </a>
          ))}
        </div>

        {/* Newly Created Token Banner */}
        {createdToken && (
          <div className="bg-emerald-950/70 border border-emerald-500/50 rounded-lg p-5 space-y-3">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="font-semibold text-emerald-400">
                  Token Generated Successfully!
                </h3>
                <p className="text-xs text-neutral-300 mt-1">
                  Make sure to copy your full API key now. For security, it will
                  never be displayed again.
                </p>
              </div>
              <button
                onClick={() => setCreatedToken(null)}
                className="text-neutral-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>
            <div className="flex gap-2 items-center">
              <input
                type="text"
                readOnly
                value={createdToken}
                className="w-full bg-neutral-950 border border-neutral-800 rounded px-3 py-2 text-xs font-mono text-emerald-300 focus:outline-none select-all"
              />
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(createdToken);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                }}
                className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded text-xs font-medium whitespace-nowrap transition-colors"
              >
                {copied ? "✓ Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}

        {/* Create Form */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg p-6">
          <h2 className="text-lg font-medium text-white mb-4">
            Create New Token
          </h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm text-neutral-400 mb-1">
                Token Name
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full md:w-1/2 bg-neutral-950 border border-neutral-800 rounded px-4 py-2 text-sm focus:outline-none focus:border-hivemind-600"
                placeholder="e.g. CI/CD Deployer"
              />
            </div>
            <div>
              <label className="block text-sm text-neutral-400 mb-2">
                Scopes
              </label>
              <div className="flex gap-4">
                {["admin", "run", "read"].map((scope) => (
                  <label
                    key={scope}
                    className="flex items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={scopes[scope as keyof typeof scopes]}
                      onChange={(e) =>
                        setScopes({ ...scopes, [scope]: e.target.checked })
                      }
                      className="accent-hivemind-600 rounded bg-neutral-900 border-neutral-700"
                    />
                    <span className="capitalize">{scope}</span>
                  </label>
                ))}
              </div>
            </div>
            <button
              type="submit"
              className="bg-hivemind-600 hover:bg-hivemind-700 text-white px-6 py-2 rounded text-sm font-medium transition-colors"
            >
              Generate Token
            </button>
          </form>
        </section>

        {/* Token List */}
        <section className="bg-neutral-900 border border-neutral-800 rounded-lg overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-950 border-b border-neutral-800">
              <tr>
                <th className="px-6 py-3 text-neutral-400 font-medium">Name</th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Prefix
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Scopes
                </th>
                <th className="px-6 py-3 text-neutral-400 font-medium">
                  Status
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
                    colSpan={5}
                    className="px-6 py-8 text-center text-neutral-500"
                  >
                    Loading tokens...
                  </td>
                </tr>
              ) : tokens.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-6 py-8 text-center text-neutral-500"
                  >
                    No API tokens generated
                  </td>
                </tr>
              ) : (
                tokens.map((t) => (
                  <tr key={t.id} className="hover:bg-neutral-800/20">
                    <td className="px-6 py-4 font-medium text-neutral-200">
                      {t.name}
                    </td>
                    <td className="px-6 py-4 font-mono text-neutral-400">
                      {t.prefix}...
                    </td>
                    <td className="px-6 py-4 text-neutral-500">
                      {t.scopes.join(", ")}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded border ${
                          t.status === "active"
                            ? "bg-green-500/10 text-green-500 border-green-500/20"
                            : "bg-red-500/10 text-red-500 border-red-500/20"
                        }`}
                      >
                        {t.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {t.status === "active" && (
                        <button
                          onClick={() => handleRevoke(t.id)}
                          className="text-red-500 hover:text-red-400 text-sm font-medium"
                        >
                          Revoke
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
