"""
Scorecard and reporting utilities for security probe evaluations.
"""
from __future__ import annotations

from typing import Any, Dict, List
from hivemind.security.runner import ProbeResult


def generate_markdown_report(results_by_backend: Dict[str, List[ProbeResult]]) -> str:
    """Generate a publication-ready Markdown comparison table across isolation backends."""
    backends = list(results_by_backend.keys())
    if not backends:
        return "# Hivemind Security Evaluation Report\n\nNo backends evaluated.\n"

    # Index results by probe_id
    probe_map: Dict[str, Dict[str, ProbeResult]] = {}
    for b_name, res_list in results_by_backend.items():
        for r in res_list:
            if r.probe_id not in probe_map:
                probe_map[r.probe_id] = {}
            probe_map[r.probe_id][b_name] = r

    lines = [
        "# Hivemind Security Isolation Benchmark Scorecard",
        "",
        "Empirical evaluation of security boundaries comparing Apple Seatbelt OS sandboxing vs. Tart MicroVMs.",
        "",
    ]

    header_cols = ["Probe ID", "Category", "Threat Description"] + [f"{b.capitalize()} Result" for b in backends]
    lines.append("| " + " | ".join(header_cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_cols)) + " |")

    total_probes = len(probe_map)
    contained_counts: Dict[str, int] = {b: 0 for b in backends}

    for probe_id, b_results in probe_map.items():
        first_r = next(iter(b_results.values()))
        row = [probe_id, first_r.category, first_r.probe_name]
        for b in backends:
            r = b_results.get(b)
            if r is None:
                row.append("—")
            elif r.contained:
                contained_counts[b] += 1
                row.append(f"🛡️ CONTAINED ({r.duration_ms:.1f}ms)")
            else:
                row.append(f"⚠️ LEAKED ({r.duration_ms:.1f}ms)")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("## Containment Summary")
    lines.append("")
    for b in backends:
        cnt = contained_counts[b]
        pct = (cnt / total_probes * 100) if total_probes > 0 else 0
        lines.append(f"- **{b.capitalize()}**: {cnt}/{total_probes} probes contained ({pct:.1f}%)")

    lines.append("")
    return "\n".join(lines)


def generate_json_report(results_by_backend: Dict[str, List[ProbeResult]]) -> Dict[str, Any]:
    """Generate a structured dictionary / JSON dataset for statistical analysis and plotting."""
    data: Dict[str, Any] = {
        "benchmark": "hivemind_security_probe_suite",
        "backends": {},
    }

    for b_name, res_list in results_by_backend.items():
        contained_count = sum(1 for r in res_list if r.contained)
        data["backends"][b_name] = {
            "total_probes": len(res_list),
            "contained": contained_count,
            "containment_rate": (contained_count / len(res_list)) if res_list else 0.0,
            "results": [
                {
                    "probe_id": r.probe_id,
                    "probe_name": r.probe_name,
                    "category": r.category,
                    "contained": r.contained,
                    "exit_code": r.exit_code,
                    "duration_ms": r.duration_ms,
                    "output": r.output,
                }
                for r in res_list
            ],
        }

    return data
