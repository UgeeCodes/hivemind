from __future__ import annotations
import logging
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_TEMPLATE = textwrap.dedent('''\
---
name: hivemind
description: Drive a remote Mac using the Hivemind SDK. Execute commands, read/write files, and manage sandboxes.
---

# Hivemind — Remote Mac Execution

You have access to a remote Mac via the Hivemind SDK. Use it to:
- Execute shell commands (`run`)
- Read and write files
- Take screenshots
- Run builds and tests (Xcode, npm, cargo, etc.)

## Setup

The SDK is configured via environment variables:
- `HIVEMIND_CONTROL_PLANE` — Control plane URL
- `HIVEMIND_API_KEY` — API key (scoped token recommended)

## Usage

```python
import hivemind

mac = hivemind.mac()
result = mac.run("uname -msr")
print(result.stdout)  # Darwin 25.2.0 arm64
```

### Run a command
```python
result = mac.run("xcodebuild -scheme MyApp build")
print(result.stdout)
print(result.exit_code)  # 0 = success
```

### Read a file
```python
result = mac.run("cat /path/to/file")
print(result.stdout)
```

### Write a file
```python
mac.run("echo 'content' > /path/to/file")
```

### Sandboxed execution
```python
sbx = mac.sandbox()
result = sbx.exec("npm test", check=True)
```

### Stream output
```python
for stream, data in mac.stream("long-running-command"):
    print(data, end="")
```

## MCP Server

Alternatively, use the MCP server directly:

```jsonc
// Claude Desktop / Cursor — mcpServers:
"hivemind": {
  "command": "hivemind",
  "args": ["mcp"],
  "env": {
    "HIVEMIND_CONTROL_PLANE": "http://your-server:8000",
    "HIVEMIND_API_KEY": "hm_sk_..."
  }
}
```

## Security

Always use scoped tokens for agents:
```bash
hivemind token new my-agent --scope run  # can run commands, can\\'t mint keys
```
''')

def generate_skill(output_dir: str | None = None) -> Path:
    """Generate a SKILL.md file for Claude Code / Cursor integration."""
    if output_dir:
        path = Path(output_dir) / 'SKILL.md'
    else:
        path = Path.home() / '.hivemind' / 'SKILL.md'
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SKILL_TEMPLATE)
    logger.info(f'Wrote SKILL.md to {path}')
    return path

def install_skill() -> Path:
    """Install SKILL.md into the default location for Claude Code discovery."""
    # Claude Code looks for skills in ~/.claude/skills/ or the project root
    claude_dir = Path.home() / '.claude' / 'skills'
    claude_dir.mkdir(parents=True, exist_ok=True)
    
    path = claude_dir / 'hivemind-SKILL.md'
    path.write_text(SKILL_TEMPLATE)
    logger.info(f'Installed SKILL.md to {path}')
    return path
