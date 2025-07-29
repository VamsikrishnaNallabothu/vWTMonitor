#!/usr/bin/env python3
"""
Setup script for ZTWorkload Manager.
"""

import os
import sys
from setuptools import setup, find_packages
from pathlib import Path

# Author: Vamsi


def read_readme():
    """
    Read the README file.
    
    :return: README content as string
    """
    readme_path = Path(__file__).parent / "README.md"
    if readme_path.exists():
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    return "ZTWorkload Manager - A high-performance, parallel SSH tool for workload management."


def read_requirements():
    """
    Read the requirements file.
    
    :return: List of requirements
    """
    requirements_path = Path(__file__).parent / "requirements.txt"
    if requirements_path.exists():
        with open(requirements_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return []


def get_version():
    """
    Get the version from the package.
    
    :return: Version string
    """
    try:
        from ztw_manager import __version__
        return __version__
    except ImportError:
        return "1.0.0"


setup(
    name="ztworkload",
    version=get_version(),
    description="A high-performance, parallel SSH tool for workload management",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="Vamsi",
    author_email="vamsi@example.com",
    url="https://github.com/example/ztworkload",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Networking",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ztw-manager=ztw_manager.cli:cli",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="ssh, parallel, workload, management, networking, monitoring",
    project_urls={
        "Bug Reports": "https://github.com/example/ztworkload/issues",
        "Source": "https://github.com/example/ztworkload",
        "Documentation": "https://github.com/example/ztworkload#readme",
    },
) 