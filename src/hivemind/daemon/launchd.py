from __future__ import annotations
import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

LABEL = 'com.hivemind.daemon'
PLIST_PATH = Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'
LOG_DIR = Path.home() / '.hivemind' / 'logs'

def generate_plist(
    control_plane_url: str,
    device_token: str,
    tags: list[str] | None = None,
) -> dict:
    """Generate the LaunchAgent plist dictionary."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    python_path = sys.executable
    
    program_args = [
        python_path, '-m', 'hivemind.daemon',
        '--control-plane', control_plane_url,
        '--device-token', device_token,
    ]
    if tags:
        for tag in tags:
            program_args.extend(['--tag', tag])
    
    return {
        'Label': LABEL,
        'ProgramArguments': program_args,
        'RunAtLoad': True,
        'KeepAlive': {
            'SuccessfulExit': False,  # Restart on crash, not on clean exit
        },
        'StandardOutPath': str(LOG_DIR / 'daemon.stdout.log'),
        'StandardErrorPath': str(LOG_DIR / 'daemon.stderr.log'),
        'EnvironmentVariables': {
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        },
        'ThrottleInterval': 5,  # Don't restart more than every 5 seconds
    }

def install(
    control_plane_url: str,
    device_token: str,
    tags: list[str] | None = None,
) -> Path:
    """Install the LaunchAgent plist and load it."""
    plist = generate_plist(control_plane_url, device_token, tags)
    
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST_PATH, 'wb') as f:
        plistlib.dump(plist, f)
    
    logger.info(f'Wrote LaunchAgent to {PLIST_PATH}')
    
    # Load it
    subprocess.run(['launchctl', 'load', str(PLIST_PATH)], check=True)
    logger.info(f'Loaded LaunchAgent {LABEL}')
    
    return PLIST_PATH

def uninstall() -> bool:
    """Unload and remove the LaunchAgent."""
    if PLIST_PATH.exists():
        subprocess.run(['launchctl', 'unload', str(PLIST_PATH)], check=False)
        PLIST_PATH.unlink()
        logger.info(f'Uninstalled LaunchAgent {LABEL}')
        return True
    return False

def status() -> dict:
    """Check the LaunchAgent status."""
    if not PLIST_PATH.exists():
        return {'installed': False, 'running': False}
    
    result = subprocess.run(
        ['launchctl', 'list', LABEL],
        capture_output=True, text=True
    )
    running = result.returncode == 0
    
    pid = None
    if running:
        for line in result.stdout.splitlines():
            parts = line.strip().split('\t')
            if len(parts) >= 1 and parts[0].isdigit():
                pid = int(parts[0])
    
    return {
        'installed': True,
        'running': running,
        'pid': pid,
        'plist_path': str(PLIST_PATH),
        'label': LABEL,
    }

def is_installed() -> bool:
    """Check if the LaunchAgent is installed."""
    return PLIST_PATH.exists()
