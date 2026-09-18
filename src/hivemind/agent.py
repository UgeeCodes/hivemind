from __future__ import annotations
import logging
import os
from dataclasses import dataclass

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hivemind.sdk.client import Mac, Result, mac
else:
    try:
        from hivemind.sdk.client import Mac, Result, mac
    except ImportError:
        Mac = Any
        Result = Any
        mac = None

logger = logging.getLogger(__name__)

@dataclass
class AgentConfig:
    """Configuration for running an agent on a remote Mac."""
    prompt: str
    proxy: str | None = None
    secret: str | None = None
    token: str | None = None
    harness: str = 'claude'  # 'claude' or 'codex'
    sandbox: bool = False
    machine_id: str | None = None

def _build_agent_command(config: AgentConfig) -> tuple[str, dict[str, str]]:
    """Build the shell command and env vars to run an agent."""
    env = {}
    
    if config.harness == 'claude':
        # Claude Code in non-interactive mode
        cmd = f'claude --print "{config.prompt}"'
        if config.proxy:
            env['ANTHROPIC_BASE_URL'] = config.proxy
        if config.token:
            env['ANTHROPIC_API_KEY'] = config.token
        elif config.secret:
            # The secret would be resolved by the control plane / daemon
            env['ANTHROPIC_API_KEY'] = f'${{HIVEMIND_SECRET_{config.secret.upper()}}}'
    elif config.harness == 'codex':
        cmd = f'codex --quiet "{config.prompt}"'
        if config.proxy:
            env['OPENAI_BASE_URL'] = config.proxy
        if config.token:
            env['OPENAI_API_KEY'] = config.token
    else:
        raise ValueError(f'Unknown harness: {config.harness}')
    
    return cmd, env

def run_agent(
    prompt: str,
    proxy: str | None = None,
    secret: str | None = None,
    token: str | None = None,
    harness: str = 'claude',
    sandbox: bool = False,
    machine_id: str | None = None,
    stream: bool = True,
) -> Result:
    """Run an AI agent on a remote Mac.
    
    The agent's model API calls route through the proxy, so the real
    API key never resides on the Mac.
    
    Args:
        prompt: The task/instruction for the agent
        proxy: Proxy URL for model API calls (e.g. proxyagent)
        secret: Hivemind secret name containing the proxy token
        token: Direct proxy auth token
        harness: Agent harness - 'claude' or 'codex'
        sandbox: Run in an isolated sandbox
        machine_id: Target a specific machine
        stream: Stream output as it arrives
    
    Returns:
        Result with the agent's output
    """
    config = AgentConfig(
        prompt=prompt,
        proxy=proxy,
        secret=secret,
        token=token,
        harness=harness,
        sandbox=sandbox,
        machine_id=machine_id,
    )
    
    cmd, env = _build_agent_command(config)
    m = mac(machine_id=machine_id)
    
    if sandbox:
        sbx = m.sandbox()
        return sbx.exec(cmd, env=env)
    else:
        return m.run(cmd, env=env, stream=stream)

def run_agent_on_fleet(
    prompt: str,
    proxy: str | None = None,
    secret: str | None = None,
    token: str | None = None,
    harness: str = 'claude',
) -> dict[str, Result]:
    """Run an agent on every online Mac in the fleet, in parallel.
    
    Returns:
        Dict mapping machine_id to Result
    """
    from hivemind.sdk.client import fleet
    import concurrent.futures
    
    macs = fleet()
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(macs)) as pool:
        futures = {}
        for m in macs:
            config = AgentConfig(
                prompt=prompt, proxy=proxy, secret=secret,
                token=token, harness=harness, machine_id=m.machine_id,
            )
            cmd, env = _build_agent_command(config)
            futures[pool.submit(m.run, cmd, env=env)] = m.machine_id
        
        for future in concurrent.futures.as_completed(futures):
            mid = futures[future]
            try:
                results[mid] = future.result()
            except Exception as e:
                logger.error(f'Agent failed on {mid}: {e}')
                results[mid] = Result(stdout='', stderr=str(e), exit_code=1)
    
    return results
