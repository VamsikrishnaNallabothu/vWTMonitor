"""
Iperf Manager for running iperf tests across multiple client-server pairs.
"""

import time
import threading
import asyncio
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from pathlib import Path

from .channel_manager import ChannelManager, ChannelCommand, ChannelResult
from .ssh_manager import SSHManager
from .config import Config
from .logger import StructuredLogger


@dataclass
class IperfTestConfig:
    """Configuration for iperf test."""
    test_duration: int = 60
    parallel_streams: int = 128
    mtu_size: int = 1460
    interval: int = 2
    output_format: str = "json"  # json, csv, or text
    output_dir: str = "iperf_results"
    preserve_channels: bool = True
    capture_output: bool = True


@dataclass
class IperfTestResult:
    """Result of an iperf test."""
    client_host: str
    server_host: str
    test_type: str  # "client" or "server"
    command: str
    output: str
    error: str
    start_time: datetime
    end_time: datetime
    duration: float
    success: bool
    metrics: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""


class IperfManager:
    """Manages iperf tests across multiple client-server pairs."""
    
    def __init__(self, ssh_manager: SSHManager, config: IperfTestConfig, logger: StructuredLogger = None):
        """
        Initialize iperf manager.
        
        Args:
            ssh_manager: SSH manager instance
            config: Iperf test configuration
            logger: Logger instance
        """
        self.ssh_manager = ssh_manager
        self.config = config
        self.logger = logger or StructuredLogger()
        
        # Test state
        self.active_tests: Dict[str, Dict[str, Any]] = {}
        self.test_results: List[IperfTestResult] = []
        self.channels_preserved: Dict[str, bool] = {}
        
        # Threading
        self.lock = threading.RLock()
        self.test_lock = threading.RLock()
        
        # Create output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    
    def run_iperf_tests(self, client_server_pairs: List[Tuple[str, str]], 
                       test_config: Optional[IperfTestConfig] = None) -> Dict[str, List[IperfTestResult]]:
        """
        Run iperf tests across multiple client-server pairs.
        
        Args:
            client_server_pairs: List of (client_host, server_host) tuples
            test_config: Optional test configuration override
            
        Returns:
            Dictionary mapping test pairs to their results
        """
        config = test_config or self.config
        
        self.logger.info(f"Starting iperf tests for {len(client_server_pairs)} pairs",
                        test_duration=config.test_duration,
                        parallel_streams=config.parallel_streams)
        
        all_results = {}
        
        # Phase 1: Start iperf servers on all server hosts
        server_results = self._start_iperf_servers([pair[1] for pair in client_server_pairs], config)
        
        # Wait a moment for servers to start
        time.sleep(2)
        
        # Phase 2: Start iperf clients
        client_results = self._start_iperf_clients(client_server_pairs, config)
        
        # Phase 3: Wait for tests to complete
        self._wait_for_tests_completion(client_server_pairs, config)
        
        # Phase 4: Collect and process results
        all_results = self._collect_results(client_server_pairs, server_results, client_results)
        
        # Phase 5: Cleanup (optional - preserve channels if requested)
        if not config.preserve_channels:
            self._cleanup_channels(client_server_pairs)
        
        return all_results
    
    def _start_iperf_servers(self, server_hosts: List[str], config: IperfTestConfig) -> Dict[str, IperfTestResult]:
        """Start iperf servers on server hosts."""
        server_results = {}
        
        # Create server commands
        server_commands = []
        for server_host in server_hosts:
            cmd = f"iperf3 -s -J -i {config.interval}"
            server_commands.append(ChannelCommand(
                command=cmd,
                timeout=config.test_duration + 30,  # Extra time for startup
                wait_for_prompt=False  # Server runs continuously
            ))
        
        # Execute server commands
        self.logger.info("Starting iperf servers...")
        server_chain_results = self.ssh_manager.execute_chain_commands(
            commands=server_commands,
            hosts=server_hosts,
            timeout=config.test_duration + 30,
            create_new_channel=True  # New channel for each server
        )
        
        # Process server results
        for server_host, results in server_chain_results.items():
            if results and len(results) > 0:
                result = results[0]  # Server command result
                server_results[server_host] = IperfTestResult(
                    client_host="",
                    server_host=server_host,
                    test_type="server",
                    command=result.command,
                    output=result.output,
                    error=result.error,
                    start_time=result.timestamp,
                    end_time=datetime.now(),
                    duration=result.duration,
                    success=result.success,
                    raw_output=result.output
                )
                
                # Mark channel as preserved
                if config.preserve_channels:
                    self.channels_preserved[server_host] = True
        
        return server_results
    
    def _start_iperf_clients(self, client_server_pairs: List[Tuple[str, str]], 
                           config: IperfTestConfig) -> Dict[str, IperfTestResult]:
        """Start iperf clients on client hosts."""
        client_results = {}
        
        # Create client commands
        client_commands = []
        client_hosts = []
        
        for client_host, server_host in client_server_pairs:
            cmd = (f"iperf3 -c {server_host} -O1 -P {config.parallel_streams} "
                   f"-M {config.mtu_size} -t {config.test_duration} -i {config.interval} -J")
            
            client_commands.append(ChannelCommand(
                command=cmd,
                timeout=config.test_duration + 60,  # Extra time for completion
                wait_for_prompt=True
            ))
            client_hosts.append(client_host)
        
        # Execute client commands
        self.logger.info("Starting iperf clients...")
        client_chain_results = self.ssh_manager.execute_chain_commands(
            commands=client_commands,
            hosts=client_hosts,
            timeout=config.test_duration + 60,
            create_new_channel=True  # New channel for each client
        )
        
        # Process client results
        for i, (client_host, server_host) in enumerate(client_server_pairs):
            if client_host in client_chain_results and client_chain_results[client_host]:
                result = client_chain_results[client_host][0]  # Client command result
                
                # Parse iperf output for metrics
                metrics = self._parse_iperf_output(result.output)
                
                client_results[f"{client_host}_to_{server_host}"] = IperfTestResult(
                    client_host=client_host,
                    server_host=server_host,
                    test_type="client",
                    command=result.command,
                    output=result.output,
                    error=result.error,
                    start_time=result.timestamp,
                    end_time=datetime.now(),
                    duration=result.duration,
                    success=result.success,
                    metrics=metrics,
                    raw_output=result.output
                )
                
                # Mark channel as preserved
                if config.preserve_channels:
                    self.channels_preserved[client_host] = True
        
        return client_results
    
    def _wait_for_tests_completion(self, client_server_pairs: List[Tuple[str, str]], 
                                 config: IperfTestConfig):
        """Wait for all tests to complete."""
        self.logger.info(f"Waiting for tests to complete ({config.test_duration} seconds)...")
        
        # Wait for the test duration plus some buffer
        time.sleep(config.test_duration + 10)
        
        # Check if tests are still running
        self._check_test_status(client_server_pairs)
    
    def _check_test_status(self, client_server_pairs: List[Tuple[str, str]]):
        """Check the status of running tests."""
        for client_host, server_host in client_server_pairs:
            # Check if iperf processes are still running
            check_cmd = "ps aux | grep iperf3 | grep -v grep"
            
            try:
                # Check client
                client_result = self.ssh_manager.execute_command(
                    check_cmd, hosts=[client_host]
                )
                if client_result:
                    self.logger.debug(f"Client {client_host} iperf status: {client_result[0].output}")
                
                # Check server
                server_result = self.ssh_manager.execute_command(
                    check_cmd, hosts=[server_host]
                )
                if server_result:
                    self.logger.debug(f"Server {server_host} iperf status: {server_result[0].output}")
                    
            except Exception as e:
                self.logger.warning(f"Error checking test status for {client_host}-{server_host}: {e}")
    
    def _collect_results(self, client_server_pairs: List[Tuple[str, str]], 
                        server_results: Dict[str, IperfTestResult],
                        client_results: Dict[str, IperfTestResult]) -> Dict[str, List[IperfTestResult]]:
        """Collect and organize test results."""
        all_results = {}
        
        for client_host, server_host in client_server_pairs:
            pair_key = f"{client_host}_to_{server_host}"
            pair_results = []
            
            # Add server result if available
            if server_host in server_results:
                pair_results.append(server_results[server_host])
            
            # Add client result if available
            if pair_key in client_results:
                pair_results.append(client_results[pair_key])
            
            all_results[pair_key] = pair_results
            
            # Save results to file
            self._save_test_results(pair_key, pair_results)
        
        return all_results
    
    def _save_test_results(self, pair_key: str, results: List[IperfTestResult]):
        """Save test results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.config.output_dir}/{pair_key}_{timestamp}.json"
        
        data = []
        for result in results:
            data.append({
                'client_host': result.client_host,
                'server_host': result.server_host,
                'test_type': result.test_type,
                'command': result.command,
                'output': result.output,
                'error': result.error,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'duration': result.duration,
                'success': result.success,
                'metrics': result.metrics,
                'raw_output': result.raw_output
            })
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        self.logger.info(f"Saved results to {filename}")
    
    def _parse_iperf_output(self, output: str) -> Dict[str, Any]:
        """Parse iperf output to extract metrics."""
        metrics = {}
        
        try:
            # Try to parse as JSON first
            data = json.loads(output)
            
            if 'end' in data and 'streams' in data['end']:
                # Extract bandwidth metrics
                sum_sent = data['end']['sum_sent']
                sum_received = data['end']['sum_received']
                
                metrics['bandwidth_sent_mbps'] = sum_sent.get('bits_per_second', 0) / 1_000_000
                metrics['bandwidth_received_mbps'] = sum_received.get('bits_per_second', 0) / 1_000_000
                metrics['bytes_sent'] = sum_sent.get('bytes', 0)
                metrics['bytes_received'] = sum_received.get('bytes', 0)
                metrics['retransmits'] = sum_sent.get('retransmits', 0)
                
                # Extract connection info
                if 'connection' in data:
                    metrics['local_host'] = data['connection'].get('local_host', '')
                    metrics['local_port'] = data['connection'].get('local_port', '')
                    metrics['remote_host'] = data['connection'].get('remote_host', '')
                    metrics['remote_port'] = data['connection'].get('remote_port', '')
                
        except (json.JSONDecodeError, KeyError):
            # Fallback to text parsing
            self.logger.warning("Failed to parse iperf JSON output, falling back to text parsing")
            metrics = self._parse_iperf_text_output(output)
        
        return metrics
    
    def _parse_iperf_text_output(self, output: str) -> Dict[str, Any]:
        """Parse iperf text output to extract metrics."""
        metrics = {}
        
        # Extract bandwidth from text output
        bandwidth_pattern = r'(\d+\.?\d*)\s+(G|M|K)?bits/sec'
        match = re.search(bandwidth_pattern, output)
        if match:
            value = float(match.group(1))
            unit = match.group(2) or 'M'
            
            if unit == 'G':
                metrics['bandwidth_mbps'] = value * 1000
            elif unit == 'M':
                metrics['bandwidth_mbps'] = value
            elif unit == 'K':
                metrics['bandwidth_mbps'] = value / 1000
        
        return metrics
    
    def _cleanup_channels(self, client_server_pairs: List[Tuple[str, str]]):
        """Clean up channels if not preserving them."""
        all_hosts = set()
        for client_host, server_host in client_server_pairs:
            all_hosts.add(client_host)
            all_hosts.add(server_host)
        
        self.ssh_manager.close_channels()
        self.logger.info(f"Closed channels for {len(all_hosts)} hosts")
    
    def get_preserved_channels(self) -> Dict[str, bool]:
        """Get information about preserved channels."""
        return dict(self.channels_preserved)
    
    def get_test_summary(self) -> Dict[str, Any]:
        """Get summary of all test results."""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.success)
        failed_tests = total_tests - successful_tests
        
        # Calculate average bandwidth
        bandwidths = [r.metrics.get('bandwidth_received_mbps', 0) for r in self.test_results 
                     if r.test_type == 'client' and r.success]
        avg_bandwidth = sum(bandwidths) / len(bandwidths) if bandwidths else 0
        
        return {
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'failed_tests': failed_tests,
            'success_rate': (successful_tests / total_tests * 100) if total_tests > 0 else 0,
            'average_bandwidth_mbps': avg_bandwidth,
            'preserved_channels': len(self.channels_preserved)
        }
    
    def export_results_summary(self, filename: str):
        """Export a summary of all test results."""
        summary = self.get_test_summary()
        
        with open(filename, 'w') as f:
            json.dump(summary, f, indent=2)
        
        self.logger.info(f"Exported test summary to {filename}")


def create_iperf_test_scenario(client_hosts: List[str], server_hosts: List[str], 
                              test_config: Optional[IperfTestConfig] = None) -> List[Tuple[str, str]]:
    """
    Create iperf test pairs from client and server host lists.
    
    Args:
        client_hosts: List of client hostnames/IPs
        server_hosts: List of server hostnames/IPs
        test_config: Optional test configuration
        
    Returns:
        List of (client_host, server_host) pairs
    """
    pairs = []
    
    # Create pairs - each client tests against each server
    for client_host in client_hosts:
        for server_host in server_hosts:
            pairs.append((client_host, server_host))
    
    return pairs 