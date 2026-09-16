from setuptools import setup, find_packages

setup(
    name="hivemind",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.115",
        "uvicorn[standard]>=0.30",
        "websockets>=13.0",
        "httpx>=0.27",
        "typer>=0.12",
        "rich>=13.7",
        "pydantic>=2.7",
        "aiosqlite>=0.20",
    ],
    extras_require={
        "dev": ["pytest>=8.0", "pytest-asyncio>=0.23"],
        "mcp": ["mcp>=1.0"],
    },
    entry_points={
        "console_scripts": [
            "hivemind=hivemind.cli.main:app",
        ],
    },
)

