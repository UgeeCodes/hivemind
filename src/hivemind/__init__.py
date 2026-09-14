"""
hivemind - Turn any Mac into a programmable runtime.
"""

__version__ = '0.1.0'

try:
    from hivemind.sdk.client import mac, configure, fleet
except ImportError:
    # Placeholder imports for package loading before sdk is built
    pass
