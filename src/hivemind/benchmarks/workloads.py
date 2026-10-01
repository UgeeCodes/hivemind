"""
Benchmark workload catalog for Hivemind isolation backend profiling.

Defines standardized, repeatable workloads that exercise different
system dimensions (startup overhead, filesystem I/O, CPU compute)
to empirically compare Seatbelt vs. Tart execution performance.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from enum import Enum
from typing import List


class WorkloadCategory(str, Enum):
    """Categories of benchmark workloads."""
    MICRO = "micro"
    IO = "io"
    COMPUTE = "compute"


@dataclass(frozen=True)
class BenchmarkWorkload:
    """Definition of a repeatable benchmark workload."""
    workload_id: str
    category: WorkloadCategory
    name: str
    description: str
    command: str


# Inline Python script for I/O burst benchmark:
# Creates, writes, reads, and unlinks 500 x 4KB files.
_IO_BURST_SCRIPT = textwrap.dedent("""\
    import os, tempfile
    d = tempfile.mkdtemp()
    data = b'x' * 4096
    for i in range(500):
        p = os.path.join(d, f'f{i}')
        with open(p, 'wb') as f:
            f.write(data)
    for i in range(500):
        p = os.path.join(d, f'f{i}')
        with open(p, 'rb') as f:
            f.read()
    for i in range(500):
        os.unlink(os.path.join(d, f'f{i}'))
    os.rmdir(d)
""").strip()

# Inline Python script for CPU prime sieve benchmark:
# Sieve of Eratosthenes computing primes up to 200,000.
_CPU_SIEVE_SCRIPT = textwrap.dedent("""\
    def sieve(n):
        is_prime = [True] * (n + 1)
        is_prime[0] = is_prime[1] = False
        for i in range(2, int(n**0.5) + 1):
            if is_prime[i]:
                for j in range(i*i, n + 1, i):
                    is_prime[j] = False
        return sum(is_prime)
    count = sieve(200000)
""").strip()


DEFAULT_WORKLOADS: List[BenchmarkWorkload] = [
    # Micro benchmarks — pure startup / provisioning floor
    BenchmarkWorkload(
        workload_id="BENCH-NOOP",
        category=WorkloadCategory.MICRO,
        name="No-Op Floor",
        description="Measures minimum provisioning + process fork latency with zero workload.",
        command="/usr/bin/true",
    ),
    BenchmarkWorkload(
        workload_id="BENCH-PY-START",
        category=WorkloadCategory.MICRO,
        name="Python Runtime Floor",
        description="Measures dynamic linker and Python interpreter initialization overhead.",
        command='python3 -c "pass"',
    ),

    # I/O benchmark — filesystem throughput
    BenchmarkWorkload(
        workload_id="BENCH-IO-BURST",
        category=WorkloadCategory.IO,
        name="APFS I/O Burst",
        description="Creates, writes, reads, and deletes 500 x 4KB files to measure filesystem isolation overhead and IOPS.",
        command="python3 -c '{script}'".format(script=_IO_BURST_SCRIPT.replace("'", "\\'")),
    ),

    # Compute benchmark — CPU-bound
    BenchmarkWorkload(
        workload_id="BENCH-CPU-SIEVE",
        category=WorkloadCategory.COMPUTE,
        name="CPU Prime Sieve",
        description="Sieve of Eratosthenes computing primes up to 200,000 to measure CPU execution efficiency and hypervisor overhead.",
        command="python3 -c '{script}'".format(script=_CPU_SIEVE_SCRIPT.replace("'", "\\'")),
    ),
]
