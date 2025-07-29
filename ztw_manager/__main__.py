#!/usr/bin/env python3
"""
ZTWorkload Manager - Main entry point for module execution.
"""

import sys
import os

# Find the project root directory (where setup.py is located)
# This allows the module to be run from any location
current_file = os.path.abspath(__file__)
package_dir = os.path.dirname(current_file)
project_root = os.path.dirname(package_dir)

# Add the project root to the path to ensure imports work correctly
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ztw_manager.cli import cli

if __name__ == '__main__':
    cli() 