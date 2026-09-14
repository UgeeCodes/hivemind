"""Hivemind daemon — runs on the Mac, dials home to the control plane."""
from __future__ import annotations
import argparse
import asyncio
import logging

def main():
    parser = argparse.ArgumentParser(description='Hivemind daemon')
    parser.add_argument('--control-plane', required=True, help='Control plane URL')
    parser.add_argument('--device-token', required=True, help='Device token')
    parser.add_argument('--tag', action='append', default=[], help='Machine tags')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    
    from hivemind.daemon.agent import DaemonAgent
    agent = DaemonAgent(
        control_plane_url=args.control_plane,
        device_token=args.device_token,
        tags=args.tag,
    )
    asyncio.run(agent.run())

if __name__ == '__main__':
    main()
