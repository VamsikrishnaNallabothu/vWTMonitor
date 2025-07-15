#!/usr/bin/env python3
"""
vWT Monitor - Advanced SSH tool for workload management and network monitoring
A high-performance, parallel SSH tool with enhanced features for workload management.

This is the main CLI interface for vWT Monitor.
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import List, Optional
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.layout import Layout

from vwt_monitor import (
    SSHManager, Config, StructuredLogger, IperfManager, IperfTestConfig,
    TrafficManager, TrafficTestConfig, ProtocolType, Direction
)


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """vWT Monitor - Advanced SSH tool for workload management and network monitoring."""
    pass


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--hosts', '-h', help='Comma-separated list of hosts (overrides config)')
@click.option('--user', '-u', help='SSH username (overrides config)')
@click.option('--password', '-p', help='SSH password (overrides config)')
@click.option('--key-file', '-k', help='SSH private key file (overrides config)')
@click.option('--port', default=22, help='SSH port (overrides config)')
@click.option('--timeout', default=30, help='SSH connection timeout (overrides config)')
@click.option('--parallel', default=10, help='Maximum parallel connections (overrides config)')
@click.option('--output-dir', '-o', default='output', help='Output directory for results')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--no-progress', is_flag=True, help='Disable progress bars')
@click.argument('command')
def execute(config, hosts, user, password, key_file, port, timeout, parallel, 
           output_dir, output_format, verbose, no_progress, command):
    """Execute a command on multiple hosts."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Override with CLI arguments
        if hosts:
            cfg.hosts = hosts.split(',')
        if user:
            cfg.user = user
        if password:
            cfg.password = password
        if key_file:
            cfg.key_file = key_file
        if port != 22:
            cfg.port = port
        if timeout != 30:
            cfg.timeout = timeout
        if parallel != 10:
            cfg.max_parallel = parallel
        
        # Validate configuration
        if not cfg.hosts:
            console.print("[red]Error: No hosts specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key file must be specified[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file=os.path.join(output_dir, "vwt_monitor.log"),
            log_format=cfg.log_format
        )
        
        # Execute command
        with SSHManager(cfg, logger) as manager:
            console.print(f"[green]Executing command on {len(cfg.hosts)} hosts:[/green] {command}")
            
            results = manager.execute_command(
                command, 
                show_progress=not no_progress
            )
            
            # Display results
            display_results(console, results, command)
            
            # Export results
            output_file = os.path.join(output_dir, f"command_results.{output_format}")
            manager.export_results(results, output_file, output_format)
            console.print(f"[green]Results exported to:[/green] {output_file}")
            
            # Display summary
            display_summary(console, results)
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--hosts', '-h', help='Comma-separated list of hosts (overrides config)')
@click.option('--user', '-u', help='SSH username (overrides config)')
@click.option('--password', '-p', help='SSH password (overrides config)')
@click.option('--key-file', '-k', help='SSH private key file (overrides config)')
@click.option('--port', default=22, help='SSH port (overrides config)')
@click.option('--timeout', default=30, help='SSH connection timeout (overrides config)')
@click.option('--parallel', default=10, help='Maximum parallel connections (overrides config)')
@click.option('--output-dir', '-o', default='output', help='Output directory for results')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--no-progress', is_flag=True, help='Disable progress bars')
@click.argument('local_file')
@click.argument('remote_path')
def upload(config, hosts, user, password, key_file, port, timeout, parallel,
          output_dir, output_format, verbose, no_progress, local_file, remote_path):
    """Upload a file to multiple hosts."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Override with CLI arguments
        if hosts:
            cfg.hosts = hosts.split(',')
        if user:
            cfg.user = user
        if password:
            cfg.password = password
        if key_file:
            cfg.key_file = key_file
        if port != 22:
            cfg.port = port
        if timeout != 30:
            cfg.timeout = timeout
        if parallel != 10:
            cfg.max_parallel = parallel
        
        # Validate configuration
        if not cfg.hosts:
            console.print("[red]Error: No hosts specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key file must be specified[/red]")
            sys.exit(1)
        
        # Check if local file exists
        if not os.path.exists(local_file):
            console.print(f"[red]Error: Local file not found: {local_file}[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file=os.path.join(output_dir, "vwt_monitor.log"),
            log_format=cfg.log_format
        )
        
        # Upload file
        with SSHManager(cfg, logger) as manager:
            console.print(f"[green]Uploading file to {len(cfg.hosts)} hosts:[/green] {local_file} -> {remote_path}")
            
            results = manager.upload_file(
                local_file, 
                remote_path,
                show_progress=not no_progress
            )
            
            # Display results
            display_file_results(console, results, "upload")
            
            # Export results
            output_file = os.path.join(output_dir, f"upload_results.{output_format}")
            manager.export_results(results, output_file, output_format)
            console.print(f"[green]Results exported to:[/green] {output_file}")
            
            # Display summary
            display_file_summary(console, results, "upload")
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--hosts', '-h', help='Comma-separated list of hosts (overrides config)')
@click.option('--user', '-u', help='SSH username (overrides config)')
@click.option('--password', '-p', help='SSH password (overrides config)')
@click.option('--key-file', '-k', help='SSH private key file (overrides config)')
@click.option('--port', default=22, help='SSH port (overrides config)')
@click.option('--timeout', default=30, help='SSH connection timeout (overrides config)')
@click.option('--parallel', default=10, help='Maximum parallel connections (overrides config)')
@click.option('--output-dir', '-o', default='output', help='Output directory for results')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--no-progress', is_flag=True, help='Disable progress bars')
@click.argument('remote_file')
def download(config, hosts, user, password, key_file, port, timeout, parallel,
            output_dir, output_format, verbose, no_progress, remote_file):
    """Download a file from multiple hosts."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Override with CLI arguments
        if hosts:
            cfg.hosts = hosts.split(',')
        if user:
            cfg.user = user
        if password:
            cfg.password = password
        if key_file:
            cfg.key_file = key_file
        if port != 22:
            cfg.port = port
        if timeout != 30:
            cfg.timeout = timeout
        if parallel != 10:
            cfg.max_parallel = parallel
        
        # Validate configuration
        if not cfg.hosts:
            console.print("[red]Error: No hosts specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key_file must be specified[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file=os.path.join(output_dir, "vwt_monitor.log"),
            log_format=cfg.log_format
        )
        
        # Download file
        with SSHManager(cfg, logger) as manager:
            console.print(f"[green]Downloading file from {len(cfg.hosts)} hosts:[/green] {remote_file}")
            
            results = manager.download_file(
                remote_file, 
                output_dir,
                show_progress=not no_progress
            )
            
            # Display results
            display_file_results(console, results, "download")
            
            # Export results
            output_file = os.path.join(output_dir, f"download_results.{output_format}")
            manager.export_results(results, output_file, output_format)
            console.print(f"[green]Results exported to:[/green] {output_file}")
            
            # Display summary
            display_file_summary(console, results, "download")
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--hosts', '-h', help='Comma-separated list of hosts (overrides config)')
@click.option('--user', '-u', help='SSH username (overrides config)')
@click.option('--password', '-p', help='SSH password (overrides config)')
@click.option('--key-file', '-k', help='SSH private key file (overrides config)')
@click.option('--port', default=22, help='SSH port (overrides config)')
@click.option('--timeout', default=30, help='SSH connection timeout (overrides config)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.argument('log_file')
def tail(config, hosts, user, password, key_file, port, timeout, verbose, log_file):
    """Tail log files from multiple hosts in real-time."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Override with CLI arguments
        if hosts:
            cfg.hosts = hosts.split(',')
        if user:
            cfg.user = user
        if password:
            cfg.password = password
        if key_file:
            cfg.key_file = key_file
        if port != 22:
            cfg.port = port
        if timeout != 30:
            cfg.timeout = timeout
        
        # Validate configuration
        if not cfg.hosts:
            console.print("[red]Error: No hosts specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key_file must be specified[/red]")
            sys.exit(1)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file="logs/vwt_monitor.log",
            log_format=cfg.log_format
        )
        
        # Start log capture
        with SSHManager(cfg, logger) as manager:
            console.print(f"[green]Starting log capture from {len(cfg.hosts)} hosts:[/green] {log_file}")
            console.print("[yellow]Press Ctrl+C to stop[/yellow]")
            
            try:
                manager.start_log_capture(log_file)
                
                # Start live dashboard
                if manager.log_capture:
                    manager.log_capture.start_live_dashboard()
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping log capture...[/yellow]")
                manager.stop_log_capture()
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--output-dir', '-o', default='output', help='Output directory')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
def metrics(config, output_dir, output_format):
    """Export metrics and statistics."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[red]Error: Config file {config} not found[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level=cfg.log_level,
            log_file=os.path.join(output_dir, "vwt_monitor.log"),
            log_format=cfg.log_format
        )
        
        # Get metrics
        with SSHManager(cfg, logger) as manager:
            # Get metrics summary
            metrics_summary = manager.get_metrics_summary()
            
            # Display metrics
            display_metrics(console, metrics_summary)
            
            # Export metrics
            metrics_file = os.path.join(output_dir, f"metrics.{output_format}")
            manager.metrics.export_metrics(metrics_file, output_format)
            console.print(f"[green]Metrics exported to:[/green] {metrics_file}")
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)





@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--hosts', '-h', help='Comma-separated list of hosts (overrides config)')
@click.option('--user', '-u', help='SSH username (overrides config)')
@click.option('--password', '-p', help='SSH password (overrides config)')
@click.option('--key-file', '-k', help='SSH private key file (overrides config)')
@click.option('--port', default=22, help='SSH port (overrides config)')
@click.option('--timeout', default=30, help='SSH connection timeout (overrides config)')
@click.option('--parallel', default=10, help='Maximum parallel connections (overrides config)')
@click.option('--output-dir', '-o', default='output', help='Output directory for results')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--no-progress', is_flag=True, help='Disable progress bars')
@click.option('--new-channel', is_flag=True, help='Create new channel for each execution')
@click.argument('commands', nargs=-1, required=True)
def chain(config, hosts, user, password, key_file, port, timeout, parallel,
         output_dir, output_format, verbose, no_progress, new_channel, commands):
    """Execute a chain of commands on multiple hosts using channels."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Override with CLI arguments
        if hosts:
            cfg.hosts = hosts.split(',')
        if user:
            cfg.user = user
        if password:
            cfg.password = password
        if key_file:
            cfg.key_file = key_file
        if port != 22:
            cfg.port = port
        if timeout != 30:
            cfg.timeout = timeout
        if parallel != 10:
            cfg.max_parallel = parallel
        
        # Validate configuration
        if not cfg.hosts:
            console.print("[red]Error: No hosts specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key file must be specified[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file=os.path.join(output_dir, "vwt_monitor.log"),
            log_format=cfg.log_format
        )
        
        # Execute chain commands
        with SSHManager(cfg, logger) as manager:
            console.print(f"[green]Executing chain commands on {len(cfg.hosts)} hosts:[/green]")
            for i, cmd in enumerate(commands, 1):
                console.print(f"  {i}. {cmd}")
            
            results = manager.execute_chain_commands(
                commands=list(commands),
                show_progress=not no_progress,
                create_new_channel=new_channel
            )
            
            # Display results
            display_chain_results(console, results)
            
            # Export results
            output_file = os.path.join(output_dir, f"chain_results.{output_format}")
            export_chain_results(results, output_file, output_format)
            console.print(f"[green]Results exported to:[/green] {output_file}")
            
            # Display summary
            display_chain_summary(console, results)
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--hosts', '-h', help='Comma-separated list of hosts (overrides config)')
@click.option('--user', '-u', help='SSH username (overrides config)')
@click.option('--password', '-p', help='SSH password (overrides config)')
@click.option('--key-file', '-k', help='SSH private key file (overrides config)')
@click.option('--port', default=22, help='SSH port (overrides config)')
@click.option('--timeout', default=60, help='Command timeout in seconds')
@click.option('--parallel', default=10, help='Maximum parallel connections (overrides config)')
@click.option('--output-dir', '-o', default='output', help='Output directory for results')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--no-progress', is_flag=True, help='Disable progress bars')
@click.argument('commands_file', type=click.Path(exists=True))
def interactive(config, hosts, user, password, key_file, port, timeout, parallel,
               output_dir, output_format, verbose, no_progress, commands_file):
    """Execute interactive commands with expect patterns from a file."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Override with CLI arguments
        if hosts:
            cfg.hosts = hosts.split(',')
        if user:
            cfg.user = user
        if password:
            cfg.password = password
        if key_file:
            cfg.key_file = key_file
        if port != 22:
            cfg.port = port
        if parallel != 10:
            cfg.max_parallel = parallel
        
        # Validate configuration
        if not cfg.hosts:
            console.print("[red]Error: No hosts specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key file must be specified[/red]")
            sys.exit(1)
        
        # Read commands from file
        commands = []
        with open(commands_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Format: command|expect_pattern1,expect_pattern2
                    parts = line.split('|')
                    if len(parts) >= 2:
                        cmd = parts[0].strip()
                        patterns = [p.strip() for p in parts[1].split(',')]
                        commands.append((cmd, patterns))
                    else:
                        commands.append((line, []))
        
        if not commands:
            console.print("[red]Error: No valid commands found in file[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file=os.path.join(output_dir, "vwt_monitor.log"),
            log_format=cfg.log_format
        )
        
        # Execute interactive commands
        with SSHManager(cfg, logger) as manager:
            console.print(f"[green]Executing interactive commands on {len(cfg.hosts)} hosts:[/green]")
            for i, (cmd, patterns) in enumerate(commands, 1):
                pattern_str = f" (expect: {', '.join(patterns)})" if patterns else ""
                console.print(f"  {i}. {cmd}{pattern_str}")
            
            results = manager.execute_interactive_commands(
                commands=commands,
                timeout=timeout,
                show_progress=not no_progress
            )
            
            # Display results
            display_chain_results(console, results)
            
            # Export results
            output_file = os.path.join(output_dir, f"interactive_results.{output_format}")
            export_chain_results(results, output_file, output_format)
            console.print(f"[green]Results exported to:[/green] {output_file}")
            
            # Display summary
            display_chain_summary(console, results)
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
@click.option('--source-hosts', '-s', help='Comma-separated list of source hosts')
@click.option('--target-hosts', '-t', help='Comma-separated list of target hosts')
@click.option('--target-ports', '-p', help='Comma-separated list of target ports')
@click.option('--protocol', type=click.Choice(['tcp', 'udp', 'http', 'https', 'scp', 'ftp', 'dns', 'icmp']), 
              default='tcp', help='Protocol to test')
@click.option('--direction', type=click.Choice(['north_south', 'east_west']), 
              default='east_west', help='Traffic direction')
@click.option('--duration', default=60, help='Test duration in seconds')
@click.option('--interval', default=1.0, help='Sampling interval in seconds')
@click.option('--packet-size', default=1024, help='Packet size in bytes')
@click.option('--concurrent', default=10, help='Number of concurrent connections')
@click.option('--timeout', default=30, help='Connection timeout in seconds')
@click.option('--output-dir', '-o', default='traffic_tests', help='Output directory for results')
@click.option('--format', 'output_format', default='json', type=click.Choice(['json', 'csv']), help='Output format')
@click.option('--verify-ssl', is_flag=True, default=True, help='Verify SSL certificates for HTTPS')
@click.option('--ftp-user', help='FTP username')
@click.option('--ftp-pass', help='FTP password')
@click.option('--scp-user', help='SCP username')
@click.option('--scp-pass', help='SCP password')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--no-progress', is_flag=True, help='Disable progress bars')
def traffic(config, source_hosts, target_hosts, target_ports, protocol, direction, duration, 
           interval, packet_size, concurrent, timeout, output_dir, output_format, verify_ssl,
           ftp_user, ftp_pass, scp_user, scp_pass, verbose, no_progress):
    """Run network traffic tests across various protocols."""
    console = Console()
    
    try:
        # Load configuration
        try:
            cfg = Config.load(config)
        except FileNotFoundError:
            console.print(f"[yellow]Warning: Config file {config} not found, using defaults[/yellow]")
            cfg = Config()
        
        # Parse hosts and ports
        source_host_list = source_hosts.split(',') if source_hosts else cfg.hosts
        target_host_list = target_hosts.split(',') if target_hosts else cfg.hosts
        target_port_list = [int(p) for p in target_ports.split(',')] if target_ports else [22, 80, 443, 8080]
        
        # Validate configuration
        if not source_host_list:
            console.print("[red]Error: No source hosts specified[/red]")
            sys.exit(1)
        
        if not target_host_list:
            console.print("[red]Error: No target hosts specified[/red]")
            sys.exit(1)
        
        if not target_port_list:
            console.print("[red]Error: No target ports specified[/red]")
            sys.exit(1)
        
        if not cfg.user:
            console.print("[red]Error: No username specified[/red]")
            sys.exit(1)
        
        if not cfg.password and not cfg.key_file:
            console.print("[red]Error: Either password or key file must be specified[/red]")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Setup logger
        logger = StructuredLogger(
            level="debug" if verbose else cfg.log_level,
            log_file=os.path.join(output_dir, "traffic_test.log"),
            log_format=cfg.log_format
        )
        
        # Configure traffic test
        test_config = TrafficTestConfig(
            protocol=ProtocolType(protocol),
            direction=Direction(direction),
            source_hosts=source_host_list,
            target_hosts=target_host_list,
            target_ports=target_port_list,
            duration=duration,
            interval=interval,
            packet_size=packet_size,
            concurrent_connections=concurrent,
            timeout=timeout,
            verify_ssl=verify_ssl,
            ftp_credentials=(ftp_user, ftp_pass) if ftp_user and ftp_pass else None,
            scp_credentials=(scp_user, scp_pass) if scp_user and scp_pass else None
        )
        
        # Run traffic tests
        with SSHManager(cfg, logger) as manager:
            traffic_manager = TrafficManager(manager, cfg, logger)
            
            console.print(f"[green]Starting traffic test: {protocol.upper()} {direction.replace('_', ' ').title()}[/green]")
            console.print(f"Source hosts: {', '.join(source_host_list)}")
            console.print(f"Target hosts: {', '.join(target_host_list)}")
            console.print(f"Target ports: {', '.join(map(str, target_port_list))}")
            console.print(f"Duration: {duration}s, Interval: {interval}s")
            
            results = traffic_manager.run_traffic_test(test_config)
            
            # Display results
            display_traffic_results(console, results)
            
            # Export results
            output_file = os.path.join(output_dir, f"traffic_test_{protocol}_{direction}.{output_format}")
            traffic_manager.export_results(results, output_file, output_format)
            console.print(f"[green]Results exported to:[/green] {output_file}")
            
            # Display summary
            display_traffic_summary(console, results)
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(1)


@cli.command()
@click.option('--config', '-c', default='config.yaml', help='Configuration file path')
def config_validate(config):
    """Validate configuration file."""
    console = Console()
    
    try:
        cfg = Config.load(config)
        console.print(f"[green]Configuration file {config} is valid[/green]")
        
        # Display configuration
        table = Table(title="Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Hosts", str(len(cfg.hosts)))
        table.add_row("User", cfg.user)
        table.add_row("Port", str(cfg.port))
        table.add_row("Timeout", f"{cfg.timeout}s")
        table.add_row("Max Parallel", str(cfg.max_parallel))
        table.add_row("Jumphost", "Yes" if cfg.jumphost else "No")
        table.add_row("Log Level", cfg.log_level)
        table.add_row("Log Format", cfg.log_format)
        
        console.print(table)
    
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        sys.exit(1)


def display_results(console, results, command):
    """Display command execution results."""
    table = Table(title=f"Command Results: {command}")
    table.add_column("Host", style="cyan")
    table.add_column("Exit Code", style="magenta")
    table.add_column("Duration", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Output Length", style="blue")
    
    for result in results:
        status = "✅ Success" if result.success else "❌ Failed"
        table.add_row(
            result.host,
            str(result.exit_code),
            f"{result.duration:.2f}s",
            status,
            str(len(result.output))
        )
    
    console.print(table)


def display_file_results(console, results, operation):
    """Display file transfer results."""
    table = Table(title=f"File {operation.title()} Results")
    table.add_column("Host", style="cyan")
    table.add_column("Size", style="magenta")
    table.add_column("Duration", style="yellow")
    table.add_column("Status", style="green")
    table.add_column("Error", style="red")
    
    for result in results:
        status = "✅ Success" if result.success else "❌ Failed"
        size_str = f"{result.size:,} bytes" if result.size > 0 else "N/A"
        table.add_row(
            result.host,
            size_str,
            f"{result.duration:.2f}s",
            status,
            result.error or ""
        )
    
    console.print(table)


def display_summary(console, results):
    """Display command execution summary."""
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful
    avg_duration = sum(r.duration for r in results) / total if total > 0 else 0
    
    summary = Panel(
        f"Total: {total} | "
        f"Successful: {successful} | "
        f"Failed: {failed} | "
        f"Success Rate: {(successful/total*100):.1f}% | "
        f"Avg Duration: {avg_duration:.2f}s",
        title="Summary"
    )
    console.print(summary)


def display_file_summary(console, results, operation):
    """Display file transfer summary."""
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful
    total_bytes = sum(r.size for r in results if r.success)
    avg_duration = sum(r.duration for r in results) / total if total > 0 else 0
    
    summary = Panel(
        f"Total: {total} | "
        f"Successful: {successful} | "
        f"Failed: {failed} | "
        f"Success Rate: {(successful/total*100):.1f}% | "
        f"Total Bytes: {total_bytes:,} | "
        f"Avg Duration: {avg_duration:.2f}s",
        title=f"{operation.title()} Summary"
    )
    console.print(summary)


def display_metrics(console, metrics_summary):
    """Display metrics."""
    # Metrics summary
    metrics_table = Table(title="Operation Metrics")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="green")
    
    metrics_table.add_row("Total Operations", str(metrics_summary['total_operations']))
    metrics_table.add_row("Successful Operations", str(metrics_summary['successful_operations']))
    metrics_table.add_row("Failed Operations", str(metrics_summary['failed_operations']))
    metrics_table.add_row("Success Rate", f"{metrics_summary['success_rate']:.1f}%")
    metrics_table.add_row("Total Duration", f"{metrics_summary['total_duration']:.2f}s")
    metrics_table.add_row("Avg Duration", f"{metrics_summary['avg_duration']:.2f}s")
    metrics_table.add_row("Total Bytes Transferred", f"{metrics_summary['total_bytes_transferred']:,}")
    metrics_table.add_row("Unique Hosts", str(metrics_summary['unique_hosts']))
    
    console.print(metrics_table)


def display_chain_results(console, results):
    """Display chain command results."""
    for host, host_results in results.items():
        console.print(f"\n[bold cyan]Host: {host}[/bold cyan]")
        
        for i, result in enumerate(host_results, 1):
            status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
            console.print(f"  {status} Command {i}: {result.command}")
            
            if result.output:
                console.print(f"    Output: {result.output[:200]}{'...' if len(result.output) > 200 else ''}")
            
            if result.error:
                console.print(f"    Error: {result.error}")
            
            console.print(f"    Duration: {result.duration:.2f}s")
            
            if result.exit_code is not None:
                console.print(f"    Exit Code: {result.exit_code}")


def display_chain_summary(console, results):
    """Display chain command execution summary."""
    total_hosts = len(results)
    successful_hosts = 0
    total_commands = 0
    successful_commands = 0
    
    for host_results in results.values():
        total_commands += len(host_results)
        successful_commands += sum(1 for r in host_results if r.success)
        if all(r.success for r in host_results):
            successful_hosts += 1
    
    failed_hosts = total_hosts - successful_hosts
    failed_commands = total_commands - successful_commands
    
    summary_table = Table(title="Chain Command Execution Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    
    summary_table.add_row("Total Hosts", str(total_hosts))
    summary_table.add_row("Successful Hosts", f"{successful_hosts} ({successful_hosts/total_hosts*100:.1f}%)")
    summary_table.add_row("Failed Hosts", f"{failed_hosts} ({failed_hosts/total_hosts*100:.1f}%)")
    summary_table.add_row("Total Commands", str(total_commands))
    summary_table.add_row("Successful Commands", f"{successful_commands} ({successful_commands/total_commands*100:.1f}%)")
    summary_table.add_row("Failed Commands", f"{failed_commands} ({failed_commands/total_commands*100:.1f}%)")
    
    console.print(summary_table)


def export_chain_results(results, filename, format="json"):
    """Export chain command results to file."""
    if format == "json":
        data = []
        for host, host_results in results.items():
            for result in host_results:
                data.append({
                    'host': host,
                    'command': result.command,
                    'output': result.output,
                    'error': result.error,
                    'exit_code': result.exit_code,
                    'duration': result.duration,
                    'timestamp': result.timestamp.isoformat(),
                    'success': result.success
                })
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    elif format == "csv":
        import csv
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['host', 'command', 'output', 'error', 'exit_code', 'duration', 'timestamp', 'success'])
            
            for host, host_results in results.items():
                for result in host_results:
                    writer.writerow([
                        host,
                        result.command,
                        result.output,
                        result.error,
                        result.exit_code,
                        result.duration,
                        result.timestamp.isoformat(),
                        result.success
                    ])





def display_traffic_results(console, results):
    """Display traffic test results."""
    console.print(f"\n[bold cyan]Traffic Test Results[/bold cyan]")
    
    # Summary table
    summary_table = Table(title="Traffic Test Summary")
    summary_table.add_column("Test ID", style="cyan")
    summary_table.add_column("Protocol", style="blue")
    summary_table.add_column("Direction", style="yellow")
    summary_table.add_column("Source → Target", style="green")
    summary_table.add_column("Port", style="magenta")
    summary_table.add_column("Status", style="white")
    summary_table.add_column("Avg Latency", style="red")
    summary_table.add_column("Avg Throughput", style="blue")
    
    for test_id, result in results.items():
        status = "✅ Success" if result.success else "❌ Failed"
        
        avg_latency = f"{result.latency.avg_latency_ms:.1f}ms" if result.latency else "N/A"
        avg_throughput = f"{result.throughput.avg_throughput_mbps:.2f} MB/s" if result.throughput else "N/A"
        
        summary_table.add_row(
            test_id[:12] + "...",
            result.protocol.value.upper(),
            result.direction.value.replace('_', ' ').title(),
            f"{result.source_host} → {result.target_host}",
            str(result.target_port),
            status,
            avg_latency,
            avg_throughput
        )
    
    console.print(summary_table)
    
    # Detailed results for each test
    for test_id, result in results.items():
        if not result.success:
            continue
            
        console.print(f"\n[bold cyan]Detailed Results for {test_id}[/bold cyan]")
        
        # Latency metrics
        if result.latency:
            latency_table = Table(title="Latency Metrics")
            latency_table.add_column("Metric", style="cyan")
            latency_table.add_column("Value", style="green")
            
            latency_table.add_row("Min Latency", f"{result.latency.min_latency_ms:.1f}ms")
            latency_table.add_row("Max Latency", f"{result.latency.max_latency_ms:.1f}ms")
            latency_table.add_row("Average Latency", f"{result.latency.avg_latency_ms:.1f}ms")
            latency_table.add_row("Median Latency", f"{result.latency.median_latency_ms:.1f}ms")
            latency_table.add_row("95th Percentile", f"{result.latency.p95_latency_ms:.1f}ms")
            latency_table.add_row("99th Percentile", f"{result.latency.p99_latency_ms:.1f}ms")
            latency_table.add_row("Std Deviation", f"{result.latency.std_deviation_ms:.1f}ms")
            
            console.print(latency_table)
        
        # Throughput metrics
        if result.throughput:
            throughput_table = Table(title="Throughput Metrics")
            throughput_table.add_column("Metric", style="cyan")
            throughput_table.add_column("Value", style="green")
            
            throughput_table.add_row("Average Throughput", f"{result.throughput.avg_throughput_mbps:.2f} MB/s")
            throughput_table.add_row("Peak Throughput", f"{result.throughput.peak_throughput_mbps:.2f} MB/s")
            throughput_table.add_row("Min Throughput", f"{result.throughput.min_throughput_mbps:.2f} MB/s")
            throughput_table.add_row("Total Bytes Sent", f"{result.throughput.total_bytes_sent:,}")
            throughput_table.add_row("Total Bytes Received", f"{result.throughput.total_bytes_received:,}")
            
            console.print(throughput_table)
        
        # Packet metrics
        if result.packets:
            packet_table = Table(title="Packet Metrics")
            packet_table.add_column("Metric", style="cyan")
            packet_table.add_column("Value", style="green")
            
            packet_table.add_row("Packets Sent", f"{result.packets.packets_sent:,}")
            packet_table.add_row("Packets Received", f"{result.packets.packets_received:,}")
            packet_table.add_row("Packets Lost", f"{result.packets.packets_lost:,}")
            packet_table.add_row("Packet Loss %", f"{result.packets.packet_loss_percent:.2f}%")
            packet_table.add_row("Duplicate Packets", f"{result.packets.duplicate_packets:,}")
            packet_table.add_row("Out of Order", f"{result.packets.out_of_order_packets:,}")
            packet_table.add_row("Corrupted Packets", f"{result.packets.corrupted_packets:,}")
            
            console.print(packet_table)
        
        # Connection metrics
        if result.connections:
            conn_table = Table(title="Connection Metrics")
            conn_table.add_column("Metric", style="cyan")
            conn_table.add_column("Value", style="green")
            
            conn_table.add_row("Total Connections", f"{result.connections.total_connections:,}")
            conn_table.add_row("Successful Connections", f"{result.connections.successful_connections:,}")
            conn_table.add_row("Failed Connections", f"{result.connections.failed_connections:,}")
            conn_table.add_row("Success Rate", f"{result.connections.connection_success_rate:.1f}%")
            conn_table.add_row("Avg Connection Time", f"{result.connections.avg_connection_time_ms:.1f}ms")
            conn_table.add_row("Connection Timeouts", f"{result.connections.connection_timeouts:,}")
            
            console.print(conn_table)
        
        # Protocol-specific metrics
        if result.protocol_specific:
            if result.protocol_specific.http_status_codes:
                http_table = Table(title="HTTP Status Codes")
                http_table.add_column("Status Code", style="cyan")
                http_table.add_column("Count", style="green")
                
                for status_code, count in result.protocol_specific.http_status_codes.items():
                    http_table.add_row(str(status_code), str(count))
                
                console.print(http_table)
            
            if result.protocol_specific.ssl_handshake_times:
                ssl_table = Table(title="SSL Handshake Times")
                ssl_table.add_column("Metric", style="cyan")
                ssl_table.add_column("Value", style="green")
                
                avg_ssl = statistics.mean(result.protocol_specific.ssl_handshake_times)
                ssl_table.add_row("Average SSL Time", f"{avg_ssl:.1f}ms")
                ssl_table.add_row("Min SSL Time", f"{min(result.protocol_specific.ssl_handshake_times):.1f}ms")
                ssl_table.add_row("Max SSL Time", f"{max(result.protocol_specific.ssl_handshake_times):.1f}ms")
                
                console.print(ssl_table)
            
            if result.protocol_specific.udp_jitter_ms > 0:
                jitter_table = Table(title="UDP Jitter")
                jitter_table.add_column("Metric", style="cyan")
                jitter_table.add_column("Value", style="green")
                
                jitter_table.add_row("Average Jitter", f"{result.protocol_specific.udp_jitter_ms:.1f}ms")
                
                console.print(jitter_table)


def display_traffic_summary(console, results):
    """Display traffic test summary."""
    total_tests = len(results)
    successful_tests = sum(1 for r in results.values() if r.success)
    failed_tests = total_tests - successful_tests
    
    # Calculate overall metrics
    all_latencies = []
    all_throughputs = []
    all_packet_loss = []
    
    for result in results.values():
        if result.success:
            if result.latency:
                all_latencies.append(result.latency.avg_latency_ms)
            if result.throughput:
                all_throughputs.append(result.throughput.avg_throughput_mbps)
            if result.packets:
                all_packet_loss.append(result.packets.packet_loss_percent)
    
    summary_table = Table(title="Overall Traffic Test Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    
    summary_table.add_row("Total Tests", str(total_tests))
    summary_table.add_row("Successful Tests", f"{successful_tests} ({successful_tests/total_tests*100:.1f}%)")
    summary_table.add_row("Failed Tests", f"{failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    
    if all_latencies:
        summary_table.add_row("Avg Latency (All)", f"{statistics.mean(all_latencies):.1f}ms")
        summary_table.add_row("Min Latency (All)", f"{min(all_latencies):.1f}ms")
        summary_table.add_row("Max Latency (All)", f"{max(all_latencies):.1f}ms")
    
    if all_throughputs:
        summary_table.add_row("Avg Throughput (All)", f"{statistics.mean(all_throughputs):.2f} MB/s")
        summary_table.add_row("Peak Throughput (All)", f"{max(all_throughputs):.2f} MB/s")
    
    if all_packet_loss:
        summary_table.add_row("Avg Packet Loss (All)", f"{statistics.mean(all_packet_loss):.2f}%")
        summary_table.add_row("Max Packet Loss (All)", f"{max(all_packet_loss):.2f}%")
    
    console.print(summary_table)


if __name__ == '__main__':
    cli() 