from setuptools import find_namespace_packages, setup


setup(
    name="cli-anything-clash-party",
    version="0.1.0",
    description="CLI-Anything harness for Clash Party.",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.1,<9",
        "PyYAML>=6.0,<7",
        "requests>=2.32,<3",
        "requests-unixsocket>=0.4,<1",
        "prompt-toolkit>=3.0,<4",
        "psutil>=6,<8",
    ],
    extras_require={
        "dev": [
            "pytest>=8.3,<9",
            "pytest-httpserver>=1.1,<2",
            "ruff>=0.11,<1",
            "mypy>=1.15,<2",
            "types-PyYAML>=6.0,<7",
            "types-requests>=2.32,<3",
        ],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-clash-party=cli_anything.clash_party.clash_party_cli:main",
        ],
    },
)
