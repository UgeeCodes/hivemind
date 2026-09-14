"""Hivemind — Turn any Mac into a programmable runtime."""
from __future__ import annotations

__version__ = '0.1.0'

from hivemind.sdk.client import mac, configure, fleet, Mac, Result, Sandbox, Volume

__all__ = [
    '__version__',
    'mac',
    'configure', 
    'fleet',
    'Mac',
    'Result',
    'Sandbox',
    'Volume',
]
