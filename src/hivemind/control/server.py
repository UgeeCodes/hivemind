from __future__ import annotations
import uvicorn

def run(host: str = '0.0.0.0', port: int = 8000) -> None:
    """Run the hivemind control plane server."""
    uvicorn.run('hivemind.control.app:app', host=host, port=port, log_level='info')

if __name__ == '__main__':
    run()
