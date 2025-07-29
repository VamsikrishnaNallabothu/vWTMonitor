"""
Workload module for ZTWorkload Manager.
Provides host-specific workload functions for each host in config.yaml.
"""

import os
import time
import threading
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

from ztw_manager.config import Config
from ztw_manager.ssh_manager import SSHManager, CommandResult, FileTransferResult
from ztw_manager.traffic_manager import TrafficManager, ProtocolType, Direction, TrafficTestConfig, TrafficTestResult
from ztw_manager.logger import StructuredLogger
from ztw_manager.iperf_manager import IperfManager, IperfTestConfig

# Author: Vamsi


class Protocol(Enum):
    """Protocol types for traffic testing."""
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"
    SCP = "scp"
    FTP = "ftp"
    DNS = "dns"
    ICMP = "icmp"


@dataclass
class WorkloadConfig:
    """Configuration for workload operations."""
    timeout: int = 30
    show_progress: bool = True
    output_dir: str = "workload_results"
    log_level: str = "info"


class HostWorkload:
    """Host-specific workload functions."""
    
    def __init__(self, host: str, ssh_manager: SSHManager, traffic_manager: TrafficManager, 
                 config: WorkloadConfig, logger: StructuredLogger):
        self.host = host
        self.ssh_manager = ssh_manager
        self.traffic_manager = traffic_manager
        self.config = config
        self.logger = logger
        self._lock = threading.Lock()
    
    def execute(self, command: str, timeout: int = None, show_progress: bool = None) -> CommandResult:
        """
        Execute a command on this host.
        
        :param command: Command to execute
        :param timeout: Command timeout in seconds
        :param show_progress: Whether to show progress bar
        :return: CommandResult object
        """
        timeout = timeout or self.config.timeout
        show_progress = show_progress if show_progress is not None else self.config.show_progress
        
        with self._lock:
            results = self.ssh_manager.execute_command(
                command=command,
                hosts=[self.host],
                timeout=timeout,
                show_progress=show_progress
            )
            
            if results:
                return results[0]
            else:
                # Return empty result if no results
                return CommandResult(
                    host=self.host,
                    command=command,
                    output="",
                    error="No result returned",
                    exit_code=-1,
                    duration=0.0,
                    timestamp=datetime.now(),
                    success=False
                )
    
    def upload(self, local_path: str, remote_path: str, show_progress: bool = None) -> FileTransferResult:
        """
        Upload a file to this host.
        
        :param local_path: Local file path
        :param remote_path: Remote file path
        :param show_progress: Whether to show progress bar
        :return: FileTransferResult object
        """
        show_progress = show_progress if show_progress is not None else self.config.show_progress
        
        with self._lock:
            results = self.ssh_manager.upload_file(
                local_path=local_path,
                remote_path=remote_path,
                hosts=[self.host],
                show_progress=show_progress
            )
            
            if results:
                return results[0]
            else:
                # Return empty result if no results
                return FileTransferResult(
                    host=self.host,
                    operation="upload",
                    local_path=local_path,
                    remote_path=remote_path,
                    size=0,
                    duration=0.0,
                    timestamp=datetime.now(),
                    success=False,
                    error="No result returned"
                )
    
    def download(self, remote_path: str, local_dir: str, show_progress: bool = None) -> FileTransferResult:
        """
        Download a file from this host.
        
        :param remote_path: Remote file path
        :param local_dir: Local directory to save file
        :param show_progress: Whether to show progress bar
        :return: FileTransferResult object
        """
        show_progress = show_progress if show_progress is not None else self.config.show_progress
        
        with self._lock:
            results = self.ssh_manager.download_file(
                remote_path=remote_path,
                local_dir=local_dir,
                hosts=[self.host],
                show_progress=show_progress
            )
            
            if results:
                return results[0]
            else:
                # Return empty result if no results
                return FileTransferResult(
                    host=self.host,
                    operation="download",
                    local_path="",
                    remote_path=remote_path,
                    size=0,
                    duration=0.0,
                    timestamp=datetime.now(),
                    success=False,
                    error="No result returned"
                )
    
    def send_traffic(self, protocol: Union[Protocol, str], target: Union['HostWorkload', str], 
                    port: int = None, duration: int = 60, **kwargs) -> TrafficTestResult:
        """
        Send traffic from this host to a target.
        
        :param protocol: Protocol type (TCP, UDP, HTTP, etc.)
        :param target: Target host (HostWorkload object or host string)
        :param port: Target port
        :param duration: Test duration in seconds
        :param **kwargs: Additional traffic test parameters
        :return: TrafficTestResult object
        """
        # Convert protocol to ProtocolType
        if isinstance(protocol, str):
            try:
                protocol = Protocol(protocol.lower())
            except ValueError:
                raise ValueError(f"Invalid protocol: {protocol}")
        
        # Get target host string
        if isinstance(target, HostWorkload):
            target_host = target.host
        else:
            target_host = str(target)
        
        # Set default port based on protocol
        if port is None:
            port = self._get_default_port(protocol)
        
        # Create test configuration
        test_config = TrafficTestConfig(
            protocol=ProtocolType(protocol.value),
            direction=Direction.EAST_WEST,
            source_hosts=[self.host],
            target_hosts=[target_host],
            target_ports=[port],
            duration=duration,
            **kwargs
        )
        
        # Create test pair
        test_pair = {
            'source_host': self.host,
            'target_host': target_host,
            'target_port': port
        }
        
        with self._lock:
            results = self.traffic_manager.run_traffic_test([test_pair], test_config)
            
            if results:
                return list(results.values())[0]
            else:
                # Return empty result if no results
                return TrafficTestResult(
                    test_id=f"{self.host}_to_{target_host}_{protocol.value}",
                    protocol=ProtocolType(protocol.value),
                    direction=Direction.EAST_WEST,
                    source_host=self.host,
                    target_host=target_host,
                    target_port=port,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_seconds=0.0,
                    success=False,
                    error_message="No result returned"
                )
    
    def ping(self, target: Union['HostWorkload', str], count: int = 4) -> CommandResult:
        """
        Ping a target from this host.
        
        :param target: Target host (HostWorkload object or host string)
        :param count: Number of ping packets
        :return: CommandResult object
        """
        if isinstance(target, HostWorkload):
            target_host = target.host
        else:
            target_host = str(target)
        
        command = f"ping -c {count} {target_host}"
        return self.execute(command)
    
    def check_connectivity(self, target: Union['HostWorkload', str], port: int = 22) -> CommandResult:
        """
        Check connectivity to a target host and port.
        
        :param target: Target host (HostWorkload object or host string)
        :param port: Target port
        :return: CommandResult object
        """
        if isinstance(target, HostWorkload):
            target_host = target.host
        else:
            target_host = str(target)
        
        command = f"nc -zv {target_host} {port}"
        return self.execute(command)
    
    def get_system_info(self) -> CommandResult:
        """
        Get system information.
        
        :return: CommandResult object
        """
        commands = [
            "uname -a",
            "cat /etc/os-release",
            "free -h",
            "df -h",
            "uptime"
        ]
        
        # Execute all commands and combine results
        results = []
        for cmd in commands:
            result = self.execute(cmd)
            results.append(result)
        
        # Combine outputs
        combined_output = "\n".join([f"=== {r.command} ===\n{r.output}" for r in results])
        combined_error = "\n".join([r.error for r in results if r.error])
        
        # Use the first result as base and modify
        base_result = results[0]
        return CommandResult(
            host=self.host,
            command="system_info",
            output=combined_output,
            error=combined_error,
            exit_code=0 if all(r.success for r in results) else 1,
            duration=sum(r.duration for r in results),
            timestamp=datetime.now(),
            success=all(r.success for r in results)
        )
    
    def install_package(self, package: str) -> CommandResult:
        """
        Install a package on this host.
        
        :param package: Package name to install
        :return: CommandResult object
        """
        # First, detect the Linux distribution
        distro_result = self._detect_linux_distribution()
        
        if not distro_result.success:
            # Fallback to trying all package managers if detection fails
            return self._install_package_fallback(package)
        
        distro = distro_result.output.strip().lower()
        
        # Use the appropriate package manager based on distribution
        if any(d in distro for d in ['ubuntu', 'debian', 'mint', 'kali']):
            # Debian-based distributions
            command = f"apt-get update && apt-get install -y {package}"
        elif any(d in distro for d in ['centos', 'rhel', 'redhat', 'fedora', 'rocky', 'alma']):
            # Red Hat-based distributions
            if 'fedora' in distro or int(distro.split()[-1]) >= 22:
                command = f"dnf install -y {package}"
            else:
                command = f"yum install -y {package}"
        elif any(d in distro for d in ['alpine']):
            # Alpine Linux
            command = f"apk add {package}"
        else:
            # Unknown distribution, try fallback
            return self._install_package_fallback(package)
        
        return self.execute(command)
    
    def _detect_linux_distribution(self) -> CommandResult:
        """
        Detect the Linux distribution on this host.
        
        :return: CommandResult with distribution information
        """
        # Try multiple methods to detect distribution
        detection_commands = [
            "cat /etc/os-release",
            "cat /etc/redhat-release",
            "cat /etc/debian_version",
            "cat /etc/issue",
            "lsb_release -a"
        ]
        
        for cmd in detection_commands:
            result = self.execute(cmd)
            if result.success and result.output.strip():
                return result
        
        # If all detection methods fail, return a failed result
        return CommandResult(
            host=self.host,
            command="detect_distribution",
            output="",
            error="Failed to detect Linux distribution",
            exit_code=1,
            duration=0.0,
            timestamp=datetime.now(),
            success=False
        )
    
    def _install_package_fallback(self, package: str) -> CommandResult:
        """
        Fallback method to install package by trying all package managers.
        
        :param package: Package name to install
        :return: CommandResult object
        """
        # Try different package managers in order of popularity
        commands = [
            f"apt-get update && apt-get install -y {package}",
            f"yum install -y {package}",
            f"dnf install -y {package}",
            f"zypper install -y {package}",
            f"pacman -S --noconfirm {package}",
            f"apk add {package}"
        ]
        
        for cmd in commands:
            result = self.execute(cmd)
            if result.success:
                return result
        
        # If all fail, return the last result
        return result
    
    def start_service(self, service: str) -> CommandResult:
        """
        Start a service on this host.
        
        :param service: Service name to start
        :return: CommandResult object
        """
        commands = [
            f"systemctl start {service}",
            f"service {service} start",
            f"/etc/init.d/{service} start"
        ]
        
        for cmd in commands:
            result = self.execute(cmd)
            if result.success:
                return result
        
        return result
    
    def stop_service(self, service: str) -> CommandResult:
        """
        Stop a service on this host.
        
        :param service: Service name to stop
        :return: CommandResult object
        """
        commands = [
            f"systemctl stop {service}",
            f"service {service} stop",
            f"/etc/init.d/{service} stop"
        ]
        
        for cmd in commands:
            result = self.execute(cmd)
            if result.success:
                return result
        
        return result
    
    def tail(self, log_file: str, lines: int = 10, follow: bool = False, 
             timeout: int = None, show_progress: bool = None) -> CommandResult:
        """
        Tail a log file on this host.
        
        :param log_file: Path to log file on the host
        :param lines: Number of lines to show (default: 10)
        :param follow: Whether to follow the log file in real-time
        :param timeout: Command timeout in seconds
        :param show_progress: Whether to show progress bar
        :return: CommandResult object
        """
        timeout = timeout or self.config.timeout
        show_progress = show_progress if show_progress is not None else self.config.show_progress
        
        # Build tail command
        if follow:
            command = f"tail -f -n {lines} {log_file}"
        else:
            command = f"tail -n {lines} {log_file}"
        
        return self.execute(command, timeout, show_progress)
    
    def tail_realtime(self, log_file: str, lines: int = 10, duration: int = 60,
                     filter_pattern: str = None, exclude_pattern: str = None) -> CommandResult:
        """
        Tail a log file in real-time with filtering and duration limit.
        
        :param log_file: Path to log file on the host
        :param lines: Number of lines to show initially
        :param duration: Duration to follow in seconds (0 for unlimited)
        :param filter_pattern: Pattern to include (grep pattern)
        :param exclude_pattern: Pattern to exclude (grep pattern)
        :return: CommandResult object
        """
        # Build the command with filtering
        base_cmd = f"tail -f -n {lines} {log_file}"
        
        if filter_pattern:
            base_cmd += f" | grep '{filter_pattern}'"
        
        if exclude_pattern:
            base_cmd += f" | grep -v '{exclude_pattern}'"
        
        # Add timeout if duration is specified
        if duration > 0:
            base_cmd = f"timeout {duration} {base_cmd}"
        
        return self.execute(base_cmd, timeout=duration if duration > 0 else None)
    
    def grep_log(self, log_file: str, pattern: str, lines_before: int = 0, 
                 lines_after: int = 0, case_insensitive: bool = False) -> CommandResult:
        """
        Search for patterns in a log file.
        
        :param log_file: Path to log file on the host
        :param pattern: Search pattern
        :param lines_before: Number of lines before match to include
        :param lines_after: Number of lines after match to include
        :param case_insensitive: Whether to perform case-insensitive search
        :return: CommandResult object
        """
        # Build grep command
        cmd_parts = ["grep"]
        
        if case_insensitive:
            cmd_parts.append("-i")
        
        if lines_before > 0:
            cmd_parts.append(f"-B {lines_before}")
        
        if lines_after > 0:
            cmd_parts.append(f"-A {lines_after}")
        
        cmd_parts.extend([f"'{pattern}'", log_file])
        
        command = " ".join(cmd_parts)
        return self.execute(command)
    
    def get_log_stats(self, log_file: str) -> CommandResult:
        """
        Get statistics about a log file.
        
        :param log_file: Path to log file on the host
        :return: CommandResult object with log statistics
        """
        commands = [
            f"wc -l {log_file}",  # Line count
            f"ls -lh {log_file}",  # File size
            f"head -n 1 {log_file}",  # First line
            f"tail -n 1 {log_file}",  # Last line
            f"stat {log_file}"  # File stats
        ]
        
        # Execute all commands and combine results
        results = []
        for cmd in commands:
            result = self.execute(cmd)
            results.append(result)
        
        # Combine outputs
        combined_output = "\n".join([f"=== {r.command} ===\n{r.output}" for r in results])
        combined_error = "\n".join([r.error for r in results if r.error])
        
        # Use the first result as base and modify
        base_result = results[0]
        return CommandResult(
            host=self.host,
            command="log_stats",
            output=combined_output,
            error=combined_error,
            exit_code=0 if all(r.success for r in results) else 1,
            duration=sum(r.duration for r in results),
            timestamp=datetime.now(),
            success=all(r.success for r in results)
        )
    
    def _get_default_port(self, protocol: Protocol) -> int:
        """
        Get default port for protocol.
        
        :param protocol: Protocol enum
        :return: Default port number
        """
        default_ports = {
            Protocol.HTTP: 80,
            Protocol.HTTPS: 443,
            Protocol.SSH: 22,
            Protocol.FTP: 21,
            Protocol.DNS: 53,
            Protocol.TCP: 80,
            Protocol.UDP: 53,
            Protocol.SCP: 22,
            Protocol.ICMP: 0  # ICMP doesn't use ports
        }
        return default_ports.get(protocol, 80)
    
    def __str__(self) -> str:
        return f"HostWorkload({self.host})"
    
    def __repr__(self) -> str:
        return self.__str__()

    def run_iperf_test(self, target: Union['HostWorkload', str], protocol: Union[Protocol, str] = Protocol.TCP,
                       port: int = 5201, duration: int = 60, parallel_streams: int = 1, 
                       mtu_size: int = 1460, interval: int = 2) -> dict:
        """
        Run iperf test from this host to a target.
        
        :param target: Target host (HostWorkload object or host string)
        :param protocol: Protocol type (TCP or UDP)
        :param port: Target port
        :param duration: Test duration in seconds
        :param parallel_streams: Number of parallel streams
        :param mtu_size: MTU size
        :param interval: Reporting interval
        :return: Dictionary with iperf test results
        """
        # Convert protocol to string
        if isinstance(protocol, Protocol):
            protocol_str = protocol.value
        else:
            protocol_str = str(protocol).lower()
        
        # Get target host string
        if isinstance(target, HostWorkload):
            target_host = target.host
        else:
            target_host = str(target)
        
        # Create iperf test configuration
        iperf_config = IperfTestConfig(
            test_duration=duration,
            parallel_streams=parallel_streams,
            mtu_size=mtu_size,
            interval=interval,
            output_format="json",
            output_dir="workload_iperf_results",
            preserve_channels=True,
            capture_output=True
        )
        
        # Create iperf manager
        iperf_manager = IperfManager(self.ssh_manager, iperf_config, self.logger)
        
        try:
            # Run full iperf workflow
            results = iperf_manager.run_full_iperf_workflow(
                client_host=self.host,
                server_host=target_host,
                port=port,
                duration=duration,
                parallel_streams=parallel_streams,
                mtu_size=mtu_size,
                interval=interval,
                output_dir=f"workload_iperf_results/{self.host}_to_{target_host}"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Iperf test failed from {self.host} to {target_host}: {e}")
            return {
                'success': False,
                'error': str(e),
                'client_host': self.host,
                'server_host': target_host,
                'protocol': protocol_str
            }


class WorkloadManager:
    """Manager for host workload operations."""
    
    def __init__(self, config_file: str = "config.yaml", workload_config: WorkloadConfig = None):
        """
        Initialize workload manager.
        
        :param config_file: Path to configuration file
        :param workload_config: Workload configuration
        """
        self.config_file = config_file
        self.workload_config = workload_config or WorkloadConfig()
        
        # Load configuration
        self.config = Config.load(config_file)
        
        # Initialize components
        self.logger = StructuredLogger(
            level=self.workload_config.log_level,
            log_file=f"{self.workload_config.output_dir}/workload.log",
            log_format="json"
        )
        
        self.ssh_manager = SSHManager(self.config, self.logger)
        self.traffic_manager = TrafficManager(self.ssh_manager, self.config, self.logger)
        
        # Create host workload objects
        self.hosts: Dict[str, HostWorkload] = {}
        self._create_host_workloads()
    
    def _create_host_workloads(self):
        """Create HostWorkload objects for each host."""
        for host in self.config.hosts:
            self.hosts[host] = HostWorkload(
                host=host,
                ssh_manager=self.ssh_manager,
                traffic_manager=self.traffic_manager,
                config=self.workload_config,
                logger=self.logger
            )
    
    def get_host(self, host: str) -> HostWorkload:
        """
        Get a host workload object.
        
        :param host: Host name or IP
        :return: HostWorkload object
        """
        if host in self.hosts:
            return self.hosts[host]
        else:
            raise ValueError(f"Host '{host}' not found in configuration")
    
    def get_all_hosts(self) -> Dict[str, HostWorkload]:
        """
        Get all host workload objects.
        
        :return: Dictionary of host name to HostWorkload object
        """
        return self.hosts.copy()
    
    def execute_on_all(self, command: str, timeout: int = None, show_progress: bool = None) -> Dict[str, CommandResult]:
        """
        Execute a command on all hosts.
        
        :param command: Command to execute
        :param timeout: Command timeout
        :param show_progress: Whether to show progress
        :return: Dictionary of host to CommandResult
        """
        results = {}
        for host_name, host_workload in self.hosts.items():
            results[host_name] = host_workload.execute(command, timeout, show_progress)
        return results
    
    def upload_to_all(self, local_path: str, remote_path: str, show_progress: bool = None) -> Dict[str, FileTransferResult]:
        """
        Upload a file to all hosts.
        
        :param local_path: Local file path
        :param remote_path: Remote file path
        :param show_progress: Whether to show progress
        :return: Dictionary of host to FileTransferResult
        """
        results = {}
        for host_name, host_workload in self.hosts.items():
            results[host_name] = host_workload.upload(local_path, remote_path, show_progress)
        return results
    
    def download_from_all(self, remote_path: str, local_dir: str, show_progress: bool = None) -> Dict[str, FileTransferResult]:
        """
        Download a file from all hosts.
        
        :param remote_path: Remote file path
        :param local_dir: Local directory
        :param show_progress: Whether to show progress
        :return: Dictionary of host to FileTransferResult
        """
        results = {}
        for host_name, host_workload in self.hosts.items():
            results[host_name] = host_workload.download(remote_path, local_dir, show_progress)
        return results
    
    def run_traffic_test(self, source_host: str, target_host: str, protocol: Union[Protocol, str], 
                        port: int = None, duration: int = 60, **kwargs) -> TrafficTestResult:
        """
        Run a traffic test between two hosts.
        
        :param source_host: Source host name
        :param target_host: Target host name
        :param protocol: Protocol type
        :param port: Target port
        :param duration: Test duration
        :param **kwargs: Additional parameters
        :return: TrafficTestResult object
        """
        source = self.get_host(source_host)
        target = self.get_host(target_host)
        
        return source.send_traffic(protocol, target, port, duration, **kwargs)
    
    def tail_on_all(self, log_file: str, lines: int = 10, follow: bool = False,
                   timeout: int = None, show_progress: bool = None) -> Dict[str, CommandResult]:
        """
        Tail a log file on all hosts.
        
        :param log_file: Path to log file on the hosts
        :param lines: Number of lines to show
        :param follow: Whether to follow the log file in real-time
        :param timeout: Command timeout
        :param show_progress: Whether to show progress
        :return: Dictionary of host to CommandResult
        """
        results = {}
        for host_name, host_workload in self.hosts.items():
            results[host_name] = host_workload.tail(log_file, lines, follow, timeout, show_progress)
        return results
    
    def grep_log_on_all(self, log_file: str, pattern: str, lines_before: int = 0,
                       lines_after: int = 0, case_insensitive: bool = False) -> Dict[str, CommandResult]:
        """
        Search for patterns in a log file on all hosts.
        
        :param log_file: Path to log file on the hosts
        :param pattern: Search pattern
        :param lines_before: Number of lines before match to include
        :param lines_after: Number of lines after match to include
        :param case_insensitive: Whether to perform case-insensitive search
        :return: Dictionary of host to CommandResult
        """
        results = {}
        for host_name, host_workload in self.hosts.items():
            results[host_name] = host_workload.grep_log(log_file, pattern, lines_before, lines_after, case_insensitive)
        return results
    
    def get_log_stats_on_all(self, log_file: str) -> Dict[str, CommandResult]:
        """
        Get statistics about a log file on all hosts.
        
        :param log_file: Path to log file on the hosts
        :return: Dictionary of host to CommandResult
        """
        results = {}
        for host_name, host_workload in self.hosts.items():
            results[host_name] = host_workload.get_log_stats(log_file)
        return results
    
    def close(self):
        """Close all connections."""
        self.ssh_manager.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Convenience function to create workload manager
def create_workload(config_file: str = "config.yaml", **kwargs) -> WorkloadManager:
    """
    Create a workload manager.
    
    :param config_file: Path to configuration file
    :param **kwargs: Additional configuration parameters
    :return: WorkloadManager object
    """
    workload_config = WorkloadConfig(**kwargs)
    return WorkloadManager(config_file, workload_config)


# Example usage and documentation
if __name__ == "__main__":
    # Example usage
    with create_workload() as workload:
        # Get host objects
        host1 = workload.get_host("192.168.1.10")
        host2 = workload.get_host("192.168.1.11")
        
        # Execute commands
        result = host1.execute("ls -la")
        print(f"Command result: {result.output}")
        
        # Upload files
        upload_result = host1.upload("local_file.txt", "/tmp/remote_file.txt")
        print(f"Upload success: {upload_result.success}")
        
        # Send traffic
        traffic_result = host1.send_traffic(Protocol.HTTP, host2, port=80)
        print(f"Traffic test success: {traffic_result.success}")
        
        # Ping test
        ping_result = host1.ping(host2)
        print(f"Ping success: {ping_result.success}")
        
        # System info
        sys_info = host1.get_system_info()
        print(f"System info: {sys_info.output}")
