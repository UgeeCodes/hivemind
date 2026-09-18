from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()
app = typer.Typer(
    name='hivemind',
    help='Turn any Mac into a programmable runtime.',
    no_args_is_help=True,
)

# Sub-command groups
child_app = typer.Typer(help='Manage the local daemon.')
token_app = typer.Typer(help='Manage API tokens.')
volume_app = typer.Typer(help='Manage volumes.')

app.add_typer(child_app, name='child')
app.add_typer(token_app, name='token')
app.add_typer(volume_app, name='volume')

# ---- Top-level commands ----

@app.command()
def run(
    command: list[str] = typer.Argument(..., help='Command to execute'),
    machine: Optional[str] = typer.Option(None, '-m', '--machine', help='Target machine ID'),
    timeout: Optional[float] = typer.Option(None, '--timeout', help='Timeout in seconds'),
    sandbox: Optional[str] = typer.Option(None, '--sandbox', help='Sandbox ID'),
    real: bool = typer.Option(False, '--real', help='Use real HOME (not sandboxed)'),
):
    """Run a command on a remote Mac."""
    from hivemind.sdk.client import mac as get_mac
    
    cmd = ' '.join(command)
    m = get_mac(machine_id=machine)
    
    console.print(f'[dim]Running on {m.machine_id or "idlest machine"}...[/dim]')
    result = m.run(cmd, timeout=timeout, sandbox_id=sandbox, inherit_home=real, stream=True)
    
    if result.exit_code != 0:
        console.print(f'\n[red]✗ Exit code {result.exit_code}[/red] ({result.duration_s:.2f}s)')
        raise typer.Exit(code=result.exit_code)
    else:
        console.print(f'\n[green]✓ Done[/green] ({result.duration_s:.2f}s)')

@app.command()
def machines():
    """List online machines in your fleet."""
    from hivemind.sdk.client import fleet
    
    macs = fleet()
    if not macs:
        console.print('[yellow]No machines online.[/yellow]')
        return
    
    table = Table(title='Online Machines')
    table.add_column('Machine ID', style='cyan')
    table.add_column('Hostname', style='green')
    table.add_column('Specs')
    table.add_column('Load')
    table.add_column('Status')
    table.add_column('Tags')
    for m in macs:
        tag_str = ', '.join(m.tags) if m.tags else '—'
        status_style = 'green' if m.status == 'online' else 'dim'

        specs_parts = []
        if m.chip:
            specs_parts.append(m.chip)
        if m.ram_gb:
            specs_parts.append(f'{m.ram_gb}GB')
        if m.cpu_cores:
            specs_parts.append(f'{m.cpu_cores} cores')
        specs_str = ' · '.join(specs_parts) if specs_parts else (m.arch or '—')

        load_parts = []
        if m.cpu_percent is not None:
            load_parts.append(f'{m.cpu_percent:.0f}% CPU')
        if m.memory_percent is not None:
            load_parts.append(f'{m.memory_percent:.0f}% RAM')
        load_str = ' / '.join(load_parts) if load_parts else '—'

        table.add_row(
            m.machine_id or '—',
            m.hostname or '—',
            specs_str,
            load_str,
            f'[{status_style}]{m.status or "online"}[/{status_style}]',
            tag_str,
        )
    console.print(table)

@app.command()
def shell(
    machine: Optional[str] = typer.Option(None, '-m', '--machine', help='Target machine ID'),
):
    """Open an interactive shell to a remote Mac."""
    from hivemind.sdk.client import mac as get_mac
    
    m = get_mac(machine_id=machine)
    console.print(f'[bold]Interactive shell to {m.machine_id or "idlest machine"}[/bold]')
    console.print('[dim]Type commands. Ctrl+D to exit.[/dim]')
    
    while True:
        try:
            cmd = console.input('[bold cyan]hivemind>[/bold cyan] ')
            if not cmd.strip():
                continue
            result = m.run(cmd, stream=True, inherit_home=True)
            if result.exit_code != 0:
                console.print(f'[red]exit {result.exit_code}[/red]')
        except (EOFError, KeyboardInterrupt):
            console.print('\n[dim]Disconnected.[/dim]')
            break

@app.command()
def status():
    """Show current configuration and connection status."""
    from hivemind.sdk.client import _config
    
    console.print(f'[bold]Control Plane:[/bold] {_config["url"]}')
    console.print(f'[bold]API Key:[/bold] {_config["token"][:16]}...' if _config['token'] else '[bold]API Key:[/bold] [red]not set[/red]')

@app.command()
def serve(
    host: str = typer.Option('0.0.0.0', help='Host to bind'),
    port: int = typer.Option(8000, help='Port to bind'),
):
    """Start the control plane server."""
    from hivemind.control.server import run as run_server
    console.print(f'[bold green]Starting Hivemind control plane on {host}:{port}[/bold green]')
    run_server(host=host, port=port)

# ---- Child (daemon) commands ----

@child_app.command('start')
def child_start(
    control_plane: str = typer.Option('http://localhost:8000', '--control-plane', '-c', help='Control plane URL'),
    token: Optional[str] = typer.Option(None, '--token', '-t', help='Device token'),
    tag: list[str] = typer.Option([], '--tag', help='Machine tags'),
    foreground: bool = typer.Option(False, '--foreground', '-f', help='Run in foreground'),
):
    """Start the daemon (connect this Mac to the control plane)."""
    token_file = Path.home() / '.hivemind' / 'device_token'
    if not token:
        if token_file.exists():
            token = token_file.read_text().strip()
        else:
            # Auto-generate a device token for first-time setup
            from hivemind.control.auth import generate_device_token
            full_token, _ = generate_device_token()
            token = full_token
            try:
                token_file.parent.mkdir(parents=True, exist_ok=True)
                token_file.write_text(token)
                console.print(f'[bold]Generated device token:[/bold] {token}')
                console.print(f'[dim]Saved to {token_file}[/dim]')
            except Exception:
                pass
    elif token:
        try:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(token)
        except Exception:
            pass
    
    if foreground:
        from hivemind.daemon.agent import DaemonAgent
        agent = DaemonAgent(control_plane_url=control_plane, device_token=token, tags=tag)
        console.print(f'[bold green]✓ Hivemind daemon starting (foreground)[/bold green]')
        console.print(f'  Control plane: {control_plane}')
        asyncio.run(agent.run())
    else:
        from hivemind.daemon.launchd import install
        plist_path = install(control_plane_url=control_plane, device_token=token, tags=tag)
        console.print(f'[bold green]✓ Hivemind daemon is live (background)[/bold green]')
        console.print(f'  LaunchAgent: {plist_path}')
        console.print(f'  Control plane: {control_plane}')
        console.print('\n  [dim]status:[/dim] hivemind child status')
        console.print('  [dim]stop:[/dim]   hivemind child stop')
        console.print('  [dim]logs:[/dim]   hivemind child logs')

@child_app.command('stop')
def child_stop():
    """Stop the local daemon."""
    from hivemind.daemon.launchd import uninstall
    if uninstall():
        console.print('[green]✓ Daemon stopped and uninstalled.[/green]')
    else:
        console.print('[yellow]Daemon not installed.[/yellow]')

@child_app.command('status')
def child_status():
    """Check daemon status."""
    from hivemind.daemon.launchd import status as daemon_status
    info = daemon_status()
    if info['installed']:
        status_str = '[green]running[/green]' if info['running'] else '[red]stopped[/red]'
        console.print(f'[bold]Daemon:[/bold] {status_str}')
        if info.get('pid'):
            console.print(f'[bold]PID:[/bold] {info["pid"]}')
        console.print(f'[bold]Plist:[/bold] {info["plist_path"]}')
    else:
        console.print('[yellow]Daemon not installed. Run: hivemind child start[/yellow]')

@child_app.command('logs')
def child_logs(
    follow: bool = typer.Option(False, '-f', '--follow', help='Follow log output'),
):
    """View daemon logs."""
    import subprocess
    from hivemind.daemon.launchd import LOG_DIR
    log_file = LOG_DIR / 'daemon.stderr.log'
    if not log_file.exists():
        console.print('[yellow]No logs found.[/yellow]')
        return
    cmd = ['tail', '-f' if follow else '-n', '50', str(log_file)]
    subprocess.run(cmd)

# ---- Token commands ----

@token_app.command('new')
def token_new(
    name: str = typer.Argument(..., help='Token name'),
    scope: list[str] = typer.Option(['admin'], '--scope', '-s', help='Token scopes'),
):
    """Create a new API token."""
    import httpx
    from hivemind.sdk.client import _base_url, _headers
    
    with httpx.Client() as client:
        resp = client.post(
            f'{_base_url()}/api/tokens',
            json={'name': name, 'scopes': scope},
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    
    console.print(f'[bold green]✓ Token created[/bold green]')
    console.print(f'[bold]Token:[/bold] {data["token"]}')
    console.print(f'[bold]Prefix:[/bold] {data["prefix"]}')
    console.print(f'[bold]Scopes:[/bold] {", ".join(data["scopes"])}')
    console.print('[dim]This is the only time the full token is shown.[/dim]')

@token_app.command('ls')
def token_list():
    """List API tokens."""
    import httpx
    from hivemind.sdk.client import _base_url, _headers
    
    with httpx.Client() as client:
        resp = client.get(f'{_base_url()}/api/tokens', headers=_headers())
        resp.raise_for_status()
        keys = resp.json().get('keys', [])
    
    table = Table(title='API Tokens')
    table.add_column('Prefix', style='cyan')
    table.add_column('Name')
    table.add_column('Scopes')
    table.add_column('Status')
    for k in keys:
        status_str = '[red]revoked[/red]' if k.get('revoked_at') else '[green]active[/green]'
        table.add_row(k.get('key_prefix', ''), k.get('name', '—'), ', '.join(k.get('scopes', [])), status_str)
    console.print(table)

@token_app.command('revoke')
def token_revoke(
    prefix: str = typer.Argument(..., help='Token prefix to revoke'),
):
    """Revoke an API token."""
    import httpx
    from hivemind.sdk.client import _base_url, _headers
    
    with httpx.Client() as client:
        resp = client.delete(f'{_base_url()}/api/tokens/{prefix}', headers=_headers())
        resp.raise_for_status()
    console.print(f'[green]✓ Token {prefix} revoked.[/green]')

# ---- Volume commands ----

@volume_app.command('ls')
def volume_list():
    """List volumes."""
    console.print('[yellow]Volume listing coming soon.[/yellow]')

@volume_app.command('create')
def volume_create(name: str = typer.Argument(..., help='Volume name')):
    """Create a volume."""
    console.print(f'[yellow]Volume creation coming soon: {name}[/yellow]')

@volume_app.command('rm')
def volume_remove(name: str = typer.Argument(..., help='Volume name')):
    """Remove a volume."""
    console.print(f'[yellow]Volume removal coming soon: {name}[/yellow]')

# ---- MCP command ----

@app.command()
def mcp():
    """Start the MCP server (for Claude Desktop, Cursor, etc.)."""
    try:
        from hivemind.mcp_server import run_server
        import asyncio
        console.print('[bold green]Starting Hivemind MCP server...[/bold green]')
        asyncio.run(run_server())
    except ImportError:
        console.print('[red]MCP support requires the mcp package.[/red]')
        console.print('Install with: [bold]pip install "hivemind[mcp]"[/bold]')
        raise typer.Exit(code=1)

# ---- Agent command ----

@app.command()
def agent(
    prompt: str = typer.Argument(..., help='Task for the agent'),
    proxy: Optional[str] = typer.Option(None, '--proxy', help='Proxy URL for model API calls'),
    secret: Optional[str] = typer.Option(None, '--secret', help='Hivemind secret name for proxy token'),
    harness_name: str = typer.Option('claude', '--harness', '-h', help='Agent harness (claude/codex)'),
    sandbox_mode: bool = typer.Option(False, '--sandbox', help='Run in isolated sandbox'),
    machine: Optional[str] = typer.Option(None, '-m', '--machine', help='Target machine ID'),
    all_machines: bool = typer.Option(False, '--all', help='Run on all machines in parallel'),
):
    """Run an AI agent on a remote Mac (keyless via proxy)."""
    from hivemind.agent import run_agent, run_agent_on_fleet

    if all_machines:
        console.print(f'[bold]Running agent on all machines...[/bold]')
        results = run_agent_on_fleet(prompt=prompt, proxy=proxy, secret=secret, harness=harness_name)
        for mid, result in results.items():
            status = '[green]✓[/green]' if result.exit_code == 0 else '[red]✗[/red]'
            console.print(f'  {status} {mid}: exit {result.exit_code}')
    else:
        console.print(f'[bold]Running agent ({harness_name})...[/bold]')
        result = run_agent(
            prompt=prompt, proxy=proxy, secret=secret,
            harness=harness_name, sandbox=sandbox_mode,
            machine_id=machine, stream=True,
        )
        if result.exit_code == 0:
            console.print(f'\n[green]✓ Agent completed[/green] ({result.duration_s:.2f}s)')
        else:
            console.print(f'\n[red]✗ Agent failed (exit {result.exit_code})[/red]')
            raise typer.Exit(code=result.exit_code)

# ---- Skill command ----

@app.command()
def skill(
    install_flag: bool = typer.Option(False, '--install', help='Install SKILL.md for Claude Code'),
    output: Optional[str] = typer.Option(None, '--output', '-o', help='Output directory'),
):
    """Generate or install a SKILL.md for AI agent integration."""
    from hivemind.skill import generate_skill, install_skill

    if install_flag:
        path = install_skill()
        console.print(f'[bold green]✓ SKILL.md installed[/bold green] → {path}')
    else:
        path = generate_skill(output_dir=output)
        console.print(f'[bold green]✓ SKILL.md generated[/bold green] → {path}')

if __name__ == '__main__':
    app()

