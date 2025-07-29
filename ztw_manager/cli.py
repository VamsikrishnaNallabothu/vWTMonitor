#!/usr/bin/env python3
"""
ZTWorkload Manager - CLI interface.
"""

import os
import sys
import json
import statistics
from pathlib import Path
from typing import List, Optional
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from . import (
    SSHManager, Config, StructuredLogger, TrafficManager, TrafficTestConfig,
    ProtocolType, Direction, LogCapture, LogCaptureConfig
)

# Author: Vamsi


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """ZTWorkload Manager - A high-performance, parallel SSH tool for workload management."""
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
            log_file=os.path.join(output_dir, "ztw_manager.log"),
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
            log_file=os.path.join(output_dir, "ztw_manager.log"),
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
            log_file=os.path.join(output_dir, "ztw_manager.log"),
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
            log_file="logs/ztw_manager.log",
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