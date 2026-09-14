from __future__ import annotations
import logging
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

SANDBOX_BASE = Path.home() / '.hivemind' / 'sandboxes'

# Credential stores that sandboxes should NOT be able to read
DENIED_PATHS = [
    '~/.ssh',
    '~/.aws',
    '~/.config/gcloud',
    '~/.azure',
    '~/.docker',
    '~/.gnupg',
    '~/.netrc',
    '~/.npmrc',
]

def generate_seatbelt_profile(sandbox_id: str, allow_network: bool = True) -> str:
    """Generate a Seatbelt (sandbox-exec) profile for a sandbox.
    
    The profile:
    - Allows reads globally (for toolchains, system libraries)
    - Restricts writes to the sandbox directory tree
    - Denies reads of credential stores
    - Optionally allows network access
    """
    sandbox_dir = str(SANDBOX_BASE / sandbox_id)
    home_dir = str(Path.home())
    
    deny_rules = '\n'.join(
        f'    (deny file-read* (subpath "{p.replace("~", home_dir)}"))'
        for p in DENIED_PATHS
    )
    
    network_rule = '(allow network*)' if allow_network else '(deny network*)'
    
    profile = textwrap.dedent(f'''\
        (version 1)
        (allow default)
        
        ;; Deny reads of credential stores
        {deny_rules}
        
        ;; Restrict file writes to sandbox directory
        (deny file-write*
            (require-not
                (require-any
                    (subpath "{sandbox_dir}")
                    (subpath "/private/tmp")
                    (subpath "/private/var/folders")
                )
            )
        )
        
        ;; Network policy
        ({network_rule})
    ''')
    return profile


def write_seatbelt_profile(sandbox_id: str, allow_network: bool = True) -> Path:
    """Write a Seatbelt profile to disk and return the path."""
    profile = generate_seatbelt_profile(sandbox_id, allow_network)
    profile_dir = SANDBOX_BASE / sandbox_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / 'sandbox.sb'
    profile_path.write_text(profile)
    logger.info(f'Wrote Seatbelt profile to {profile_path}')
    return profile_path


def wrap_command_with_seatbelt(command: str, sandbox_id: str, allow_network: bool = True) -> str:
    """Wrap a command to execute under sandbox-exec."""
    profile_path = write_seatbelt_profile(sandbox_id, allow_network)
    return f'sandbox-exec -f {profile_path} /bin/zsh -c {_shell_quote(command)}'


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell usage."""
    import shlex
    return shlex.quote(s)


def list_sandboxes() -> list[dict]:
    """List all sandbox directories."""
    if not SANDBOX_BASE.exists():
        return []
    result = []
    for d in SANDBOX_BASE.iterdir():
        if d.is_dir():
            result.append({
                'id': d.name,
                'path': str(d),
                'has_profile': (d / 'sandbox.sb').exists(),
            })
    return result


def destroy_sandbox(sandbox_id: str) -> bool:
    """Remove a sandbox directory tree."""
    import shutil
    sandbox_dir = SANDBOX_BASE / sandbox_id
    if sandbox_dir.exists():
        shutil.rmtree(sandbox_dir)
        logger.info(f'Destroyed sandbox {sandbox_id}')
        return True
    return False
