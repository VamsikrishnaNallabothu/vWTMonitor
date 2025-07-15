"""
Main SSH manager module with enhanced features and parallel execution.
"""

import os
import time
import threading
import asyncio
import concurrent.futures
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import paramiko
from paramiko import SSHClient, SFTPClient
from paramiko.ssh_exception import SSHException, AuthenticationException, NoValidConnectionsError
import hashlib
from pathlib import Path
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.live import Live
from rich.layout import Layout

from .config import Config
from .logger import StructuredLogger, HostLogger
from .connection_pool import ConnectionPool, JumphostConnectionPool
from .log_capture import LogCapture, LogCaptureConfig
# Removed: from .metrics import MetricsCollector
from .channel_manager import ChannelManager, ChannelCommand, ChannelResult


@dataclass
class CommandResult:
    """Result of a command execution."""
    host: str
    command: str
    output: str
    error: str
    exit_code: int
    duration: float
    timestamp: datetime
    success: bool


@dataclass
class FileTransferResult:
    """Result of a file transfer operation."""
    host: str
    operation: str  # upload, download
    local_path: str
    remote_path: str
    size: int
    duration: float
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    checksum: Optional[str] = None


class SSHManager:
    """Enhanced SSH manager with parallel execution and advanced features."""
    
    def __init__(self, config: Config, logger: StructuredLogger = None):
        """
        Initialize SSH manager.
        
        Args:
            config: Configuration object
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or StructuredLogger(
            level=config.log_level,
            log_file=config.log_file,
            log_format=config.log_format
        )
        
        # Initialize components
        self.connection_pool = self._create_connection_pool()
        # Removed: self.metrics = MetricsCollector(
        #     enable_prometheus=config.enable_metrics,
        #     prometheus_port=config.metrics_port
        # )
        
        # Log capture
        self.log_capture = None
        if config.log_capture.enabled:
            self.log_capture = LogCapture(config.log_capture, self.logger)
        
        # Threading
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=config.max_parallel
        )
        self.semaphore = threading.Semaphore(config.max_parallel)
        
        # Rich console
        self.console = Console()
        
        # Host loggers
        self.host_loggers: Dict[str, HostLogger] = {}
        
        # Channel managers
        self.channel_managers: Dict[str, ChannelManager] = {}
        
        self.logger.info("SSH Manager initialized", 
                        hosts_count=len(config.hosts),
                        max_parallel=config.max_parallel)
    
    def _create_connection_pool(self) -> ConnectionPool:
        """Create appropriate connection pool."""
        if self.config.jumphost:
            return JumphostConnectionPool(
                jumphost_config=self.config.jumphost,
                max_connections=self.config.connection_pool_size,
                max_idle_time=self.config.connection_idle_timeout,
                connection_timeout=self.config.timeout,
                health_check_interval=60
            )
        else:
            return ConnectionPool(
                max_connections=self.config.connection_pool_size,
                max_idle_time=self.config.connection_idle_timeout,
                connection_timeout=self.config.timeout,
                health_check_interval=60
            )
    
    def _get_host_logger(self, host: str) -> HostLogger:
        """Get or create host-specific logger."""
        if host not in self.host_loggers:
            self.host_loggers[host] = HostLogger(host, self.logger)
        return self.host_loggers[host]
    
    def execute_command(self, command: str, hosts: List[str] = None, 
                       timeout: int = None, show_progress: bool = True) -> List[CommandResult]:
        """
        Execute command on multiple hosts in parallel.
        
        Args:
            command: Command to execute
            hosts: List of hosts (None for all configured hosts)
            timeout: Command timeout (None for default)
            show_progress: Show progress bar
            
        Returns:
            List of command results
        """
        target_hosts = hosts or self.config.hosts
        timeout = timeout or self.config.timeout
        
        self.logger.info(f"Executing command on {len(target_hosts)} hosts", 
                        command=command, timeout=timeout)
        
        # Start metrics
        operation_ids = {}
        for host in target_hosts:
            operation_ids[host] = self.metrics.start_operation("command", host)
        
        # Execute commands in parallel
        futures = {}
        with self.executor as executor:
            for host in target_hosts:
                future = executor.submit(
                    self._execute_command_on_host, host, command, timeout
                )
                futures[future] = host
        
        # Collect results with progress bar
        results = []
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Executing commands...", total=len(target_hosts))
                
                for future in concurrent.futures.as_completed(futures):
                    host = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        
                        # Update metrics
                        if result.success:
                            self.metrics.end_operation(
                                operation_ids[host], success=True, 
                                exit_code=result.exit_code
                            )
                        else:
                            self.metrics.end_operation(
                                operation_ids[host], success=False,
                                error_message=result.error
                            )
                        
                        progress.update(task, advance=1)
                        
                    except Exception as e:
                        error_result = CommandResult(
                            host=host,
                            command=command,
                            output="",
                            error=str(e),
                            exit_code=-1,
                            duration=0.0,
                            timestamp=datetime.now(),
                            success=False
                        )
                        results.append(error_result)
                        
                        self.metrics.end_operation(
                            operation_ids[host], success=False,
                            error_message=str(e)
                        )
                        
                        progress.update(task, advance=1)
        else:
            # Collect results without progress bar
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update metrics
                    if result.success:
                        self.metrics.end_operation(
                            operation_ids[host], success=True,
                            exit_code=result.exit_code
                        )
                    else:
                        self.metrics.end_operation(
                            operation_ids[host], success=False,
                            error_message=result.error
                        )
                        
                except Exception as e:
                    error_result = CommandResult(
                        host=host,
                        command=command,
                        output="",
                        error=str(e),
                        exit_code=-1,
                        duration=0.0,
                        timestamp=datetime.now(),
                        success=False
                    )
                    results.append(error_result)
                    
                    self.metrics.end_operation(
                        operation_ids[host], success=False,
                        error_message=str(e)
                    )
        
        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        self.logger.info("Command execution completed",
                        total=len(results),
                        successful=successful,
                        failed=failed,
                        command=command)
        
        return results
    
    def _execute_command_on_host(self, host: str, command: str, timeout: int) -> CommandResult:
        """
        Execute command on a specific host.
        
        Args:
            host: Target host
            command: Command to execute
            timeout: Command timeout
            
        Returns:
            Command result
        """
        start_time = time.time()
        host_logger = self._get_host_logger(host)
        
        try:
            with self.semaphore:
                # Get connection
                if isinstance(self.connection_pool, JumphostConnectionPool):
                    client = self.connection_pool.get_connection_through_jumphost(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                else:
                    client = self.connection_pool.get_connection(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                
                # Execute command
                session = client.get_transport().open_session()
                session.settimeout(timeout)
                session.exec_command(command)
                
                # Get output
                stdout = session.makefile('r', -1)
                stderr = session.makefile_stderr('r', -1)
                
                output = stdout.read().strip()
                error = stderr.read().strip()
                
                # Get exit code
                exit_code = session.recv_exit_status()
                
                duration = time.time() - start_time
                success = exit_code == 0
                
                result = CommandResult(
                    host=host,
                    command=command,
                    output=output,
                    error=error,
                    exit_code=exit_code,
                    duration=duration,
                    timestamp=datetime.now(),
                    success=success
                )
                
                # Log result
                host_logger.log_command(command, exit_code, output, error, duration)
                
                return result
                
        except Exception as e:
            duration = time.time() - start_time
            host_logger.log_connection("failure", error=str(e))
            
            return CommandResult(
                host=host,
                command=command,
                output="",
                error=str(e),
                exit_code=-1,
                duration=duration,
                timestamp=datetime.now(),
                success=False
            )
    
    def _get_or_create_channel_manager(self, host: str) -> ChannelManager:
        """
        Get or create a channel manager for a host.
        
        Args:
            host: Target host
            
        Returns:
            Channel manager instance
        """
        if host not in self.channel_managers:
            # Get SSH client
            if isinstance(self.connection_pool, JumphostConnectionPool):
                client = self.connection_pool.get_connection_through_jumphost(
                    host, self.config.port, self.config.user,
                    self.config.password, self.config.key_file
                )
            else:
                client = self.connection_pool.get_connection(
                    host, self.config.port, self.config.user,
                    self.config.password, self.config.key_file
                )
            
            # Create channel manager
            self.channel_managers[host] = ChannelManager(client, self.logger)
        
        return self.channel_managers[host]
    
    def execute_chain_commands(self, commands: List[Union[str, ChannelCommand]], 
                              hosts: List[str] = None, timeout: float = None,
                              show_progress: bool = True, create_new_channel: bool = False) -> Dict[str, List[ChannelResult]]:
        """
        Execute a chain of commands on multiple hosts using channels.
        
        Args:
            commands: List of commands (strings or ChannelCommand objects)
            hosts: List of hosts (None for all configured hosts)
            timeout: Command timeout (None for default)
            show_progress: Show progress bar
            create_new_channel: Whether to create new channels
            
        Returns:
            Dictionary mapping hosts to their command results
        """
        target_hosts = hosts or self.config.hosts
        timeout = timeout or self.config.timeout
        
        # Convert string commands to ChannelCommand objects
        channel_commands = []
        for cmd in commands:
            if isinstance(cmd, str):
                channel_commands.append(ChannelCommand(command=cmd, timeout=timeout))
            else:
                channel_commands.append(cmd)
        
        self.logger.info(f"Executing chain commands on {len(target_hosts)} hosts", 
                        command_count=len(channel_commands), timeout=timeout)
        
        # Start metrics
        operation_ids = {}
        for host in target_hosts:
            operation_ids[host] = self.metrics.start_operation("chain_command", host)
        
        # Execute chain commands in parallel
        futures = {}
        with self.executor as executor:
            for host in target_hosts:
                future = executor.submit(
                    self._execute_chain_commands_on_host, host, channel_commands, create_new_channel
                )
                futures[future] = host
        
        # Collect results
        all_results = {}
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Executing chain commands...", total=len(target_hosts))
                
                for future in concurrent.futures.as_completed(futures):
                    host = futures[future]
                    try:
                        results = future.result()
                        all_results[host] = results
                        
                        # Update metrics
                        success = all(result.success for result in results)
                        if success:
                            self.metrics.end_operation(
                                operation_ids[host], success=True
                            )
                        else:
                            failed_commands = [r.command for r in results if not r.success]
                            self.metrics.end_operation(
                                operation_ids[host], success=False,
                                error_message=f"Failed commands: {failed_commands}"
                            )
                        
                        progress.update(task, advance=1)
                        
                    except Exception as e:
                        error_results = [ChannelResult(
                            command="chain_execution",
                            output="",
                            error=str(e),
                            success=False
                        )]
                        all_results[host] = error_results
                        
                        self.metrics.end_operation(
                            operation_ids[host], success=False,
                            error_message=str(e)
                        )
                        
                        progress.update(task, advance=1)
        else:
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    results = future.result()
                    all_results[host] = results
                    
                    # Update metrics
                    success = all(result.success for result in results)
                    if success:
                        self.metrics.end_operation(
                            operation_ids[host], success=True
                        )
                    else:
                        failed_commands = [r.command for r in results if not r.success]
                        self.metrics.end_operation(
                            operation_ids[host], success=False,
                            error_message=f"Failed commands: {failed_commands}"
                        )
                        
                except Exception as e:
                    error_results = [ChannelResult(
                        command="chain_execution",
                        output="",
                        error=str(e),
                        success=False
                    )]
                    all_results[host] = error_results
                    
                    self.metrics.end_operation(
                        operation_ids[host], success=False,
                        error_message=str(e)
                    )
        
        # Log summary
        total_commands = len(channel_commands)
        successful_hosts = sum(1 for results in all_results.values() 
                              if all(r.success for r in results))
        failed_hosts = len(all_results) - successful_hosts
        
        self.logger.info("Chain command execution completed",
                        total_hosts=len(all_results),
                        successful_hosts=successful_hosts,
                        failed_hosts=failed_hosts,
                        total_commands=total_commands)
        
        return all_results
    
    def _execute_chain_commands_on_host(self, host: str, commands: List[ChannelCommand], 
                                       create_new_channel: bool = False) -> List[ChannelResult]:
        """
        Execute chain commands on a specific host.
        
        Args:
            host: Target host
            commands: List of channel commands
            create_new_channel: Whether to create a new channel
            
        Returns:
            List of command results
        """
        try:
            with self.semaphore:
                # Get or create channel manager
                channel_manager = self._get_or_create_channel_manager(host)
                
                # Execute chain commands
                results = channel_manager.execute_chain_commands(
                    host, commands, create_new_channel
                )
                
                # Log results
                host_logger = self._get_host_logger(host)
                for result in results:
                    host_logger.log_command(
                        result.command, 
                        result.exit_code or 0,
                        result.output,
                        result.error,
                        result.duration
                    )
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error executing chain commands on {host}: {e}")
            return [ChannelResult(
                command="chain_execution",
                output="",
                error=str(e),
                success=False
            )]
    
    def execute_interactive_commands(self, commands: List[Tuple[str, List[str]]], 
                                   hosts: List[str] = None, timeout: float = 60.0,
                                   show_progress: bool = True) -> Dict[str, List[ChannelResult]]:
        """
        Execute interactive commands with expect patterns.
        
        Args:
            commands: List of (command, expect_patterns) tuples
            hosts: List of hosts (None for all configured hosts)
            timeout: Command timeout
            show_progress: Show progress bar
            
        Returns:
            Dictionary mapping hosts to their command results
        """
        target_hosts = hosts or self.config.hosts
        
        self.logger.info(f"Executing interactive commands on {len(target_hosts)} hosts", 
                        command_count=len(commands), timeout=timeout)
        
        # Start metrics
        operation_ids = {}
        for host in target_hosts:
            operation_ids[host] = self.metrics.start_operation("interactive_command", host)
        
        # Execute interactive commands in parallel
        futures = {}
        with self.executor as executor:
            for host in target_hosts:
                future = executor.submit(
                    self._execute_interactive_commands_on_host, host, commands, timeout
                )
                futures[future] = host
        
        # Collect results
        all_results = {}
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Executing interactive commands...", total=len(target_hosts))
                
                for future in concurrent.futures.as_completed(futures):
                    host = futures[future]
                    try:
                        results = future.result()
                        all_results[host] = results
                        
                        # Update metrics
                        success = all(result.success for result in results)
                        if success:
                            self.metrics.end_operation(
                                operation_ids[host], success=True
                            )
                        else:
                            failed_commands = [r.command for r in results if not r.success]
                            self.metrics.end_operation(
                                operation_ids[host], success=False,
                                error_message=f"Failed commands: {failed_commands}"
                            )
                        
                        progress.update(task, advance=1)
                        
                    except Exception as e:
                        error_results = [ChannelResult(
                            command="interactive_session",
                            output="",
                            error=str(e),
                            success=False
                        )]
                        all_results[host] = error_results
                        
                        self.metrics.end_operation(
                            operation_ids[host], success=False,
                            error_message=str(e)
                        )
                        
                        progress.update(task, advance=1)
        else:
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    results = future.result()
                    all_results[host] = results
                    
                    # Update metrics
                    success = all(result.success for result in results)
                    if success:
                        self.metrics.end_operation(
                            operation_ids[host], success=True
                        )
                    else:
                        failed_commands = [r.command for r in results if not r.success]
                        self.metrics.end_operation(
                            operation_ids[host], success=False,
                            error_message=f"Failed commands: {failed_commands}"
                        )
                        
                except Exception as e:
                    error_results = [ChannelResult(
                        command="interactive_session",
                        output="",
                        error=str(e),
                        success=False
                    )]
                    all_results[host] = error_results
                    
                    self.metrics.end_operation(
                        operation_ids[host], success=False,
                        error_message=str(e)
                    )
        
        return all_results
    
    def _execute_interactive_commands_on_host(self, host: str, commands: List[Tuple[str, List[str]]], 
                                             timeout: float = 60.0) -> List[ChannelResult]:
        """
        Execute interactive commands on a specific host.
        
        Args:
            host: Target host
            commands: List of (command, expect_patterns) tuples
            timeout: Command timeout
            
        Returns:
            List of command results
        """
        try:
            with self.semaphore:
                # Get or create channel manager
                channel_manager = self._get_or_create_channel_manager(host)
                
                # Execute interactive commands
                results = channel_manager.execute_interactive_commands(
                    host, commands, timeout
                )
                
                # Log results
                host_logger = self._get_host_logger(host)
                for result in results:
                    host_logger.log_command(
                        result.command, 
                        result.exit_code or 0,
                        result.output,
                        result.error,
                        result.duration
                    )
                
                return results
                
        except Exception as e:
            self.logger.error(f"Error executing interactive commands on {host}: {e}")
            return [ChannelResult(
                command="interactive_session",
                output="",
                error=str(e),
                success=False
            )]
    
    def get_channel_info(self, host: str = None) -> Dict[str, Any]:
        """
        Get channel information.
        
        Args:
            host: Specific host (None for all hosts)
            
        Returns:
            Channel information
        """
        if host:
            if host in self.channel_managers:
                return self.channel_managers[host].get_channel_info(host) or {}
            return {}
        else:
            all_info = {}
            for host, manager in self.channel_managers.items():
                all_info[host] = manager.list_channels()
            return all_info
    
    def close_channels(self, host: str = None):
        """
        Close channels.
        
        Args:
            host: Specific host (None for all hosts)
        """
        if host:
            if host in self.channel_managers:
                self.channel_managers[host].close_channel(host)
        else:
            for manager in self.channel_managers.values():
                manager.close_all_channels()
    
    def upload_file(self, local_path: str, remote_path: str, hosts: List[str] = None,
                   show_progress: bool = True) -> List[FileTransferResult]:
        """
        Upload file to multiple hosts in parallel.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
            hosts: List of hosts (None for all configured hosts)
            show_progress: Show progress bar
            
        Returns:
            List of file transfer results
        """
        target_hosts = hosts or self.config.hosts
        
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        file_size = os.path.getsize(local_path)
        
        self.logger.info(f"Uploading file to {len(target_hosts)} hosts",
                        local_path=local_path,
                        remote_path=remote_path,
                        file_size=file_size)
        
        # Start metrics
        operation_ids = {}
        for host in target_hosts:
            operation_ids[host] = self.metrics.start_operation("upload", host)
        
        # Upload files in parallel
        futures = {}
        with self.executor as executor:
            for host in target_hosts:
                future = executor.submit(
                    self._upload_file_to_host, host, local_path, remote_path
                )
                futures[future] = host
        
        # Collect results
        results = []
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Uploading files...", total=len(target_hosts))
                
                for future in concurrent.futures.as_completed(futures):
                    host = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        
                        # Update metrics
                        self.metrics.end_operation(
                            operation_ids[host],
                            success=result.success,
                            bytes_transferred=result.size,
                            error_message=result.error
                        )
                        
                        progress.update(task, advance=1)
                        
                    except Exception as e:
                        error_result = FileTransferResult(
                            host=host,
                            operation="upload",
                            local_path=local_path,
                            remote_path=remote_path,
                            size=0,
                            duration=0.0,
                            timestamp=datetime.now(),
                            success=False,
                            error=str(e)
                        )
                        results.append(error_result)
                        
                        self.metrics.end_operation(
                            operation_ids[host],
                            success=False,
                            error_message=str(e)
                        )
                        
                        progress.update(task, advance=1)
        else:
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    self.metrics.end_operation(
                        operation_ids[host],
                        success=result.success,
                        bytes_transferred=result.size,
                        error_message=result.error
                    )
                    
                except Exception as e:
                    error_result = FileTransferResult(
                        host=host,
                        operation="upload",
                        local_path=local_path,
                        remote_path=remote_path,
                        size=0,
                        duration=0.0,
                        timestamp=datetime.now(),
                        success=False,
                        error=str(e)
                    )
                    results.append(error_result)
                    
                    self.metrics.end_operation(
                        operation_ids[host],
                        success=False,
                        error_message=str(e)
                    )
        
        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_bytes = sum(r.size for r in results if r.success)
        
        self.logger.info("File upload completed",
                        total=len(results),
                        successful=successful,
                        failed=failed,
                        total_bytes=total_bytes,
                        local_path=local_path)
        
        return results
    
    def _upload_file_to_host(self, host: str, local_path: str, remote_path: str) -> FileTransferResult:
        """
        Upload file to a specific host.
        
        Args:
            host: Target host
            local_path: Local file path
            remote_path: Remote file path
            
        Returns:
            File transfer result
        """
        start_time = time.time()
        host_logger = self._get_host_logger(host)
        
        try:
            with self.semaphore:
                # Get connection
                if isinstance(self.connection_pool, JumphostConnectionPool):
                    client = self.connection_pool.get_connection_through_jumphost(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                else:
                    client = self.connection_pool.get_connection(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                
                # Create SFTP client
                sftp = client.open_sftp()
                
                # Upload file
                sftp.put(local_path, remote_path)
                
                # Get file size
                stat = sftp.stat(remote_path)
                file_size = stat.st_size
                
                # Calculate checksum if enabled
                checksum = None
                if self.config.file_transfer.verify_checksum:
                    checksum = self._calculate_file_checksum(sftp, remote_path)
                
                sftp.close()
                
                duration = time.time() - start_time
                
                result = FileTransferResult(
                    host=host,
                    operation="upload",
                    local_path=local_path,
                    remote_path=remote_path,
                    size=file_size,
                    duration=duration,
                    timestamp=datetime.now(),
                    success=True,
                    checksum=checksum
                )
                
                # Log result
                host_logger.log_file_transfer("upload", local_path, remote_path, file_size, duration)
                
                return result
                
        except Exception as e:
            duration = time.time() - start_time
            
            result = FileTransferResult(
                host=host,
                operation="upload",
                local_path=local_path,
                remote_path=remote_path,
                size=0,
                duration=duration,
                timestamp=datetime.now(),
                success=False,
                error=str(e)
            )
            
            host_logger.log_connection("failure", error=str(e))
            
            return result
    
    def download_file(self, remote_path: str, local_dir: str, hosts: List[str] = None,
                     show_progress: bool = True) -> List[FileTransferResult]:
        """
        Download file from multiple hosts in parallel.
        
        Args:
            remote_path: Remote file path
            local_dir: Local directory to save files
            hosts: List of hosts (None for all configured hosts)
            show_progress: Show progress bar
            
        Returns:
            List of file transfer results
        """
        target_hosts = hosts or self.config.hosts
        
        os.makedirs(local_dir, exist_ok=True)
        
        self.logger.info(f"Downloading file from {len(target_hosts)} hosts",
                        remote_path=remote_path,
                        local_dir=local_dir)
        
        # Start metrics
        operation_ids = {}
        for host in target_hosts:
            operation_ids[host] = self.metrics.start_operation("download", host)
        
        # Download files in parallel
        futures = {}
        with self.executor as executor:
            for host in target_hosts:
                local_path = os.path.join(local_dir, f"{host}_{os.path.basename(remote_path)}")
                future = executor.submit(
                    self._download_file_from_host, host, remote_path, local_path
                )
                futures[future] = host
        
        # Collect results
        results = []
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Downloading files...", total=len(target_hosts))
                
                for future in concurrent.futures.as_completed(futures):
                    host = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        
                        self.metrics.end_operation(
                            operation_ids[host],
                            success=result.success,
                            bytes_transferred=result.size,
                            error_message=result.error
                        )
                        
                        progress.update(task, advance=1)
                        
                    except Exception as e:
                        local_path = os.path.join(local_dir, f"{host}_{os.path.basename(remote_path)}")
                        error_result = FileTransferResult(
                            host=host,
                            operation="download",
                            local_path=local_path,
                            remote_path=remote_path,
                            size=0,
                            duration=0.0,
                            timestamp=datetime.now(),
                            success=False,
                            error=str(e)
                        )
                        results.append(error_result)
                        
                        self.metrics.end_operation(
                            operation_ids[host],
                            success=False,
                            error_message=str(e)
                        )
                        
                        progress.update(task, advance=1)
        else:
            for future in concurrent.futures.as_completed(futures):
                host = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    self.metrics.end_operation(
                        operation_ids[host],
                        success=result.success,
                        bytes_transferred=result.size,
                        error_message=result.error
                    )
                    
                except Exception as e:
                    local_path = os.path.join(local_dir, f"{host}_{os.path.basename(remote_path)}")
                    error_result = FileTransferResult(
                        host=host,
                        operation="download",
                        local_path=local_path,
                        remote_path=remote_path,
                        size=0,
                        duration=0.0,
                        timestamp=datetime.now(),
                        success=False,
                        error=str(e)
                    )
                    results.append(error_result)
                    
                    self.metrics.end_operation(
                        operation_ids[host],
                        success=False,
                        error_message=str(e)
                    )
        
        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_bytes = sum(r.size for r in results if r.success)
        
        self.logger.info("File download completed",
                        total=len(results),
                        successful=successful,
                        failed=failed,
                        total_bytes=total_bytes,
                        remote_path=remote_path)
        
        return results
    
    def _download_file_from_host(self, host: str, remote_path: str, local_path: str) -> FileTransferResult:
        """
        Download file from a specific host.
        
        Args:
            host: Target host
            remote_path: Remote file path
            local_path: Local file path
            
        Returns:
            File transfer result
        """
        start_time = time.time()
        host_logger = self._get_host_logger(host)
        
        try:
            with self.semaphore:
                # Get connection
                if isinstance(self.connection_pool, JumphostConnectionPool):
                    client = self.connection_pool.get_connection_through_jumphost(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                else:
                    client = self.connection_pool.get_connection(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                
                # Create SFTP client
                sftp = client.open_sftp()
                
                # Download file
                sftp.get(remote_path, local_path)
                
                # Get file size
                file_size = os.path.getsize(local_path)
                
                sftp.close()
                
                duration = time.time() - start_time
                
                result = FileTransferResult(
                    host=host,
                    operation="download",
                    local_path=local_path,
                    remote_path=remote_path,
                    size=file_size,
                    duration=duration,
                    timestamp=datetime.now(),
                    success=True
                )
                
                # Log result
                host_logger.log_file_transfer("download", local_path, remote_path, file_size, duration)
                
                return result
                
        except Exception as e:
            duration = time.time() - start_time
            
            result = FileTransferResult(
                host=host,
                operation="download",
                local_path=local_path,
                remote_path=remote_path,
                size=0,
                duration=duration,
                timestamp=datetime.now(),
                success=False,
                error=str(e)
            )
            
            host_logger.log_connection("failure", error=str(e))
            
            return result
    
    def _calculate_file_checksum(self, sftp: SFTPClient, remote_path: str) -> str:
        """
        Calculate MD5 checksum of remote file.
        
        Args:
            sftp: SFTP client
            remote_path: Remote file path
            
        Returns:
            MD5 checksum
        """
        try:
            # Execute md5sum command
            session = sftp.get_channel().get_transport().open_session()
            session.exec_command(f"md5sum {remote_path}")
            
            stdout = session.makefile('r', -1)
            result = stdout.read().strip()
            
            if result:
                return result.split()[0]
            
        except Exception:
            pass
        
        return None
    
    def start_log_capture(self, log_file_path: str, hosts: List[str] = None):
        """
        Start real-time log capture from multiple hosts.
        
        Args:
            log_file_path: Path to log file on remote hosts
            hosts: List of hosts (None for all configured hosts)
        """
        if not self.log_capture:
            raise RuntimeError("Log capture is not enabled in configuration")
        
        target_hosts = hosts or self.config.hosts
        
        self.logger.info(f"Starting log capture from {len(target_hosts)} hosts",
                        log_file_path=log_file_path)
        
        for host in target_hosts:
            try:
                # Get connection
                if isinstance(self.connection_pool, JumphostConnectionPool):
                    client = self.connection_pool.get_connection_through_jumphost(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                else:
                    client = self.connection_pool.get_connection(
                        host, self.config.port, self.config.user,
                        self.config.password, self.config.key_file
                    )
                
                # Start capture
                self.log_capture.start_capture(host, client, log_file_path)
                
            except Exception as e:
                self.logger.error(f"Failed to start log capture for {host}: {e}")
    
    def stop_log_capture(self, hosts: List[str] = None):
        """
        Stop log capture.
        
        Args:
            hosts: List of hosts (None for all hosts)
        """
        if not self.log_capture:
            return
        
        target_hosts = hosts or self.config.hosts
        
        for host in target_hosts:
            self.log_capture.stop_capture(host)
        
        self.logger.info("Log capture stopped", hosts_count=len(target_hosts))
    

    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get metrics summary.
        
        Returns:
            Metrics summary
        """
        return self.metrics.get_summary_metrics()
    
    def export_results(self, results: List[Union[CommandResult, FileTransferResult]], 
                      filename: str, format: str = "json"):
        """
        Export results to file.
        
        Args:
            results: List of results to export
            filename: Output filename
            format: Export format (json, csv)
        """
        if format == "json":
            data = []
            for result in results:
                if isinstance(result, CommandResult):
                    data.append({
                        'type': 'command',
                        'host': result.host,
                        'command': result.command,
                        'output': result.output,
                        'error': result.error,
                        'exit_code': result.exit_code,
                        'duration': result.duration,
                        'timestamp': result.timestamp.isoformat(),
                        'success': result.success
                    })
                else:  # FileTransferResult
                    data.append({
                        'type': 'file_transfer',
                        'host': result.host,
                        'operation': result.operation,
                        'local_path': result.local_path,
                        'remote_path': result.remote_path,
                        'size': result.size,
                        'duration': result.duration,
                        'timestamp': result.timestamp.isoformat(),
                        'success': result.success,
                        'error': result.error,
                        'checksum': result.checksum
                    })
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write header
                if results and isinstance(results[0], CommandResult):
                    writer.writerow(['host', 'command', 'output', 'error', 'exit_code', 'duration', 'timestamp', 'success'])
                else:
                    writer.writerow(['host', 'operation', 'local_path', 'remote_path', 'size', 'duration', 'timestamp', 'success', 'error'])
                
                # Write data
                for result in results:
                    if isinstance(result, CommandResult):
                        writer.writerow([
                            result.host,
                            result.command,
                            result.output,
                            result.error,
                            result.exit_code,
                            result.duration,
                            result.timestamp.isoformat(),
                            result.success
                        ])
                    else:
                        writer.writerow([
                            result.host,
                            result.operation,
                            result.local_path,
                            result.remote_path,
                            result.size,
                            result.duration,
                            result.timestamp.isoformat(),
                            result.success,
                            result.error or ''
                        ])
        
        self.logger.info(f"Results exported to {filename}", format=format, count=len(results))
    
    def close(self):
        """Close SSH manager and cleanup resources."""
        self.logger.info("Closing SSH manager")
        
        # Stop log capture
        if self.log_capture:
            self.log_capture.stop_all_captures()
        
        # Close channels
        self.close_channels()
        
        # Close connection pool
        self.connection_pool.stop_health_check()
        self.connection_pool.clear_pool()
        
        # Stop metrics
        self.metrics.stop_monitoring()
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        self.logger.info("SSH manager closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close() 