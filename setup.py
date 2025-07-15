#!/usr/bin/env python3
"""
Setup script for SSH Tool Python package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read requirements
requirements = []
with open("requirements.txt", "r") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="vwt-monitor",
    version="1.0.0",
    author="Vamsi",
    description="vWT Monitor - Advanced SSH tool for workload management and network monitoring",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/VamsikrishnaNallabothu",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Networking",
        "Topic :: Utilities",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "pre-commit>=3.0.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.0.0",
            "myst-parser>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "vwt-monitor=main:cli",
        ],
    },
    include_package_data=True,
    package_data={
        "vwt_monitor": ["*.yaml", "*.yml"],
    },
    keywords="ssh, parallel, automation, system administration, remote execution, log capture, network monitoring, traffic testing",
    project_urls={
        "Source": "https://github.com/VamsikrishnaNallabothu",
    },
) 