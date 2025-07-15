"""
Traffic Manager for vWT Monitor.
Handles various network protocols and collects detailed traffic metrics.
"""

import time
import json
import socket
import threading
import subprocess
import asyncio
import aiohttp
import ftplib
import dns.resolver
import paramiko
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import statistics
import concurrent.futures
from enum import Enum

from .ssh_manager import SSHManager
from .config import Config
from .logger import StructuredLogger


class ProtocolType(Enum):
    """Supported network protocols."""
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"
    SCP = "scp"
    FTP = "ftp"
    DNS = "dns"
    ICMP = "icmp"


class Direction(Enum):
    """Traffic direction."""
    NORTH_SOUTH = "north_south"  # External connectivity
    EAST_WEST = "east_west"      # Internal connectivity


@dataclass
class TrafficTestConfig:
    """Configuration for traffic testing."""
    protocol: ProtocolType
    direction: Direction
    source_hosts: List[str]
    target_hosts: List[str]
    target_ports: List[int] = field(default_factory=list)
    duration: int = 60  # Test duration in seconds
    interval: float = 1.0  # Sampling interval in seconds
    packet_size: int = 1024  # Packet size in bytes
    concurrent_connections: int = 10
    timeout: int = 30
    retries: int = 3
    verify_ssl: bool = True
    custom_headers: Dict[str, str] = field(default_factory=dict)
    dns_servers: List[str] = field(default_factory=list)
    ftp_credentials: Optional[Tuple[str, str]] = None
    scp_credentials: Optional[Tuple[str, str]] = None


@dataclass
class LatencyMetrics:
    """Latency measurement metrics."""
    min_latency_ms: float
    max_latency_ms: float
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    std_deviation_ms: float
    latency_samples: List[float] = field(default_factory=list)


@dataclass
class ThroughputMetrics:
    """Throughput measurement metrics."""
    total_bytes_sent: int
    total_bytes_received: int
    avg_throughput_mbps: float
    peak_throughput_mbps: float
    min_throughput_mbps: float
    throughput_samples: List[float] = field(default_factory=list)


@dataclass
class PacketMetrics:
    """Packet-level metrics."""
    packets_sent: int
    packets_received: int
    packets_lost: int
    packet_loss_percent: float
    duplicate_packets: int
    out_of_order_packets: int
    corrupted_packets: int


@dataclass
class ConnectionMetrics:
    """Connection-level metrics."""
    total_connections: int
    successful_connections: int
    failed_connections: int
    connection_success_rate: float
    avg_connection_time_ms: float
    connection_timeouts: int
    connection_errors: List[str] = field(default_factory=list)


@dataclass
class ProtocolSpecificMetrics:
    """Protocol-specific metrics."""
    http_status_codes: Dict[int, int] = field(default_factory=dict)
    dns_resolution_times: List[float] = field(default_factory=list)
    ftp_transfer_speeds: List[float] = field(default_factory=list)
    scp_transfer_speeds: List[float] = field(default_factory=list)
    ssl_handshake_times: List[float] = field(default_factory=list)
    tcp_retransmissions: int = 0
    udp_jitter_ms: float = 0.0


@dataclass
class TrafficTestResult:
    """Complete traffic test result."""
    test_id: str
    protocol: ProtocolType
    direction: Direction
    source_host: str
    target_host: str
    target_port: int
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    success: bool
    error_message: str = ""
    
    # Metrics
    latency: Optional[LatencyMetrics] = None
    throughput: Optional[ThroughputMetrics] = None
    packets: Optional[PacketMetrics] = None
    connections: Optional[ConnectionMetrics] = None
    protocol_specific: Optional[ProtocolSpecificMetrics] = None
    
    # Raw data for analysis
    raw_latency_samples: List[float] = field(default_factory=list)
    raw_throughput_samples: List[float] = field(default_factory=list)
    raw_timestamps: List[datetime] = field(default_factory=list)


class TrafficManager:
    """Manages network traffic testing across various protocols."""
    
    def __init__(self, ssh_manager: SSHManager, config: Config, logger: StructuredLogger = None):
        """
        Initialize traffic manager.
        
        Args:
            ssh_manager: SSH manager instance
            config: Configuration instance
            logger: Logger instance
        """
        self.ssh_manager = ssh_manager
        self.config = config
        self.logger = logger or StructuredLogger()
        
        # Test tracking
        self.active_tests: Dict[str, TrafficTestResult] = {}
        self.test_history: List[TrafficTestResult] = []
        
        # Protocol handlers
        self.protocol_handlers = {
            ProtocolType.TCP: self._test_tcp_connectivity,
            ProtocolType.UDP: self._test_udp_connectivity,
            ProtocolType.HTTP: self._test_http_connectivity,
            ProtocolType.HTTPS: self._test_https_connectivity,
            ProtocolType.SCP: self._test_scp_transfer,
            ProtocolType.FTP: self._test_ftp_transfer,
            ProtocolType.DNS: self._test_dns_resolution,
            ProtocolType.ICMP: self._test_icmp_ping
        }
    
    def run_traffic_test(self, test_pairs: List[dict], test_config: TrafficTestConfig) -> Dict[str, TrafficTestResult]:
        """
        Run traffic test for a given list of source-target host pairs.
        Args:
            test_pairs: List of {source_host: target_host} dicts
            test_config: Traffic test configuration (ports, protocol, etc.)
        Returns:
            Dictionary mapping test identifiers to results
        """
        self.logger.info(f"Starting traffic test: {test_config.protocol.value} {test_config.direction.value}")
        results = {}
        test_id_base = f"{test_config.protocol.value}_{test_config.direction.value}_{int(time.time())}"
        for idx, pair in enumerate(test_pairs):
            for source_host, target_host in pair.items():
                for k, target_port in enumerate(test_config.target_ports):
                    test_id = f"{test_id_base}_{idx}_{k}"
                    try:
                        result = self._run_single_test(
                            test_id, test_config, source_host, target_host, target_port
                        )
                        results[test_id] = result
                    except Exception as e:
                        self.logger.error(f"Test {test_id} failed: {e}")
                        results[test_id] = TrafficTestResult(
                            test_id=test_id,
                            protocol=test_config.protocol,
                            direction=test_config.direction,
                            source_host=source_host,
                            target_host=target_host,
                            target_port=target_port,
                            start_time=datetime.now(),
                            end_time=datetime.now(),
                            duration_seconds=0,
                            success=False,
                            error_message=str(e)
                        )
        self.test_history.extend(results.values())
        return results
    
    def _run_single_test(self, test_id: str, test_config: TrafficTestConfig, 
                        source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Run a single traffic test."""
        start_time = datetime.now()
        
        # Get the appropriate protocol handler
        handler = self.protocol_handlers.get(test_config.protocol)
        if not handler:
            raise ValueError(f"Unsupported protocol: {test_config.protocol}")
        
        try:
            # Execute the test
            result = handler(test_id, test_config, source_host, target_host, target_port)
            result.start_time = start_time
            result.end_time = datetime.now()
            result.duration_seconds = (result.end_time - result.start_time).total_seconds()
            result.success = True
            
            return result
            
        except Exception as e:
            end_time = datetime.now()
            return TrafficTestResult(
                test_id=test_id,
                protocol=test_config.protocol,
                direction=test_config.direction,
                source_host=source_host,
                target_host=target_host,
                target_port=target_port,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                success=False,
                error_message=str(e)
            )
    
    def _test_tcp_connectivity(self, test_id: str, test_config: TrafficTestConfig,
                              source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test TCP connectivity and collect metrics."""
        self.logger.info(f"Testing TCP connectivity: {source_host} -> {target_host}:{target_port}")
        
        latency_samples = []
        throughput_samples = []
        timestamps = []
        packets_sent = 0
        packets_received = 0
        connection_times = []
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            sample_start = time.time()
            
            try:
                # Create TCP connection
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(test_config.timeout)
                
                conn_start = time.time()
                sock.connect((target_host, target_port))
                conn_time = (time.time() - conn_start) * 1000
                connection_times.append(conn_time)
                
                # Send data
                data = b'X' * test_config.packet_size
                sock.send(data)
                packets_sent += 1
                
                # Receive response
                response = sock.recv(test_config.packet_size)
                packets_received += 1
                
                sock.close()
                
                # Calculate latency
                latency = (time.time() - sample_start) * 1000
                latency_samples.append(latency)
                
                # Calculate throughput
                throughput = (len(data) + len(response)) / latency * 1000 / 1024 / 1024  # MB/s
                throughput_samples.append(throughput)
                
                timestamps.append(datetime.now())
                
            except Exception as e:
                self.logger.warning(f"TCP test failed: {e}")
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        latency_metrics = self._calculate_latency_metrics(latency_samples)
        throughput_metrics = self._calculate_throughput_metrics(throughput_samples)
        packet_metrics = self._calculate_packet_metrics(packets_sent, packets_received)
        connection_metrics = self._calculate_connection_metrics(connection_times)
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.TCP,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            latency=latency_metrics,
            throughput=throughput_metrics,
            packets=packet_metrics,
            connections=connection_metrics,
            raw_latency_samples=latency_samples,
            raw_throughput_samples=throughput_samples,
            raw_timestamps=timestamps
        )
    
    def _test_udp_connectivity(self, test_id: str, test_config: TrafficTestConfig,
                              source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test UDP connectivity and collect metrics."""
        self.logger.info(f"Testing UDP connectivity: {source_host} -> {target_host}:{target_port}")
        
        latency_samples = []
        throughput_samples = []
        timestamps = []
        packets_sent = 0
        packets_received = 0
        jitter_samples = []
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            sample_start = time.time()
            
            try:
                # Create UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(test_config.timeout)
                
                # Send data
                data = b'X' * test_config.packet_size
                sock.sendto(data, (target_host, target_port))
                packets_sent += 1
                
                # Try to receive response (UDP is unreliable)
                try:
                    response, addr = sock.recvfrom(test_config.packet_size)
                    packets_received += 1
                    
                    # Calculate latency
                    latency = (time.time() - sample_start) * 1000
                    latency_samples.append(latency)
                    
                    # Calculate jitter
                    if len(latency_samples) > 1:
                        jitter = abs(latency - latency_samples[-2])
                        jitter_samples.append(jitter)
                    
                    # Calculate throughput
                    throughput = (len(data) + len(response)) / latency * 1000 / 1024 / 1024
                    throughput_samples.append(throughput)
                    
                except socket.timeout:
                    # No response received
                    pass
                
                sock.close()
                timestamps.append(datetime.now())
                
            except Exception as e:
                self.logger.warning(f"UDP test failed: {e}")
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        latency_metrics = self._calculate_latency_metrics(latency_samples)
        throughput_metrics = self._calculate_throughput_metrics(throughput_samples)
        packet_metrics = self._calculate_packet_metrics(packets_sent, packets_received)
        
        # Calculate UDP-specific metrics
        protocol_metrics = ProtocolSpecificMetrics()
        if jitter_samples:
            protocol_metrics.udp_jitter_ms = statistics.mean(jitter_samples)
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.UDP,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            latency=latency_metrics,
            throughput=throughput_metrics,
            packets=packet_metrics,
            protocol_specific=protocol_metrics,
            raw_latency_samples=latency_samples,
            raw_throughput_samples=throughput_samples,
            raw_timestamps=timestamps
        )
    
    def _test_http_connectivity(self, test_id: str, test_config: TrafficTestConfig,
                               source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test HTTP connectivity and collect metrics."""
        self.logger.info(f"Testing HTTP connectivity: {source_host} -> {target_host}:{target_port}")
        
        latency_samples = []
        throughput_samples = []
        timestamps = []
        status_codes = {}
        connection_times = []
        
        url = f"http://{target_host}:{target_port}"
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            sample_start = time.time()
            
            try:
                # Execute HTTP request via SSH on source host
                cmd = f"curl -s -w '%{{http_code}},%{{time_total}},%{{size_download}},%{{speed_download}}' -o /dev/null {url}"
                
                result = self.ssh_manager.execute_command(cmd, hosts=[source_host])
                
                if result and result[0].success:
                    output = result[0].output.strip()
                    parts = output.split(',')
                    
                    if len(parts) >= 4:
                        status_code = int(parts[0])
                        total_time = float(parts[1]) * 1000  # Convert to ms
                        bytes_downloaded = int(parts[2])
                        speed_bps = float(parts[3])
                        
                        # Record metrics
                        latency_samples.append(total_time)
                        throughput_samples.append(speed_bps / 1024 / 1024)  # Convert to MB/s
                        timestamps.append(datetime.now())
                        
                        # Record status code
                        status_codes[status_code] = status_codes.get(status_code, 0) + 1
                        
                        connection_times.append(total_time)
                
            except Exception as e:
                self.logger.warning(f"HTTP test failed: {e}")
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        latency_metrics = self._calculate_latency_metrics(latency_samples)
        throughput_metrics = self._calculate_throughput_metrics(throughput_samples)
        connection_metrics = self._calculate_connection_metrics(connection_times)
        
        protocol_metrics = ProtocolSpecificMetrics()
        protocol_metrics.http_status_codes = status_codes
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.HTTP,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            latency=latency_metrics,
            throughput=throughput_metrics,
            connections=connection_metrics,
            protocol_specific=protocol_metrics,
            raw_latency_samples=latency_samples,
            raw_throughput_samples=throughput_samples,
            raw_timestamps=timestamps
        )
    
    def _test_https_connectivity(self, test_id: str, test_config: TrafficTestConfig,
                                source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test HTTPS connectivity and collect metrics."""
        self.logger.info(f"Testing HTTPS connectivity: {source_host} -> {target_host}:{target_port}")
        
        latency_samples = []
        throughput_samples = []
        timestamps = []
        ssl_handshake_times = []
        status_codes = {}
        
        url = f"https://{target_host}:{target_port}"
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            sample_start = time.time()
            
            try:
                # Execute HTTPS request via SSH on source host
                verify_flag = "" if test_config.verify_ssl else "-k"
                cmd = f"curl -s {verify_flag} -w '%{{http_code}},%{{time_total}},%{{time_appconnect}},%{{size_download}},%{{speed_download}}' -o /dev/null {url}"
                
                result = self.ssh_manager.execute_command(cmd, hosts=[source_host])
                
                if result and result[0].success:
                    output = result[0].output.strip()
                    parts = output.split(',')
                    
                    if len(parts) >= 5:
                        status_code = int(parts[0])
                        total_time = float(parts[1]) * 1000  # Convert to ms
                        ssl_time = float(parts[2]) * 1000  # SSL handshake time
                        bytes_downloaded = int(parts[3])
                        speed_bps = float(parts[4])
                        
                        # Record metrics
                        latency_samples.append(total_time)
                        throughput_samples.append(speed_bps / 1024 / 1024)  # Convert to MB/s
                        timestamps.append(datetime.now())
                        ssl_handshake_times.append(ssl_time)
                        
                        # Record status code
                        status_codes[status_code] = status_codes.get(status_code, 0) + 1
                
            except Exception as e:
                self.logger.warning(f"HTTPS test failed: {e}")
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        latency_metrics = self._calculate_latency_metrics(latency_samples)
        throughput_metrics = self._calculate_throughput_metrics(throughput_samples)
        
        protocol_metrics = ProtocolSpecificMetrics()
        protocol_metrics.http_status_codes = status_codes
        protocol_metrics.ssl_handshake_times = ssl_handshake_times
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.HTTPS,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            latency=latency_metrics,
            throughput=throughput_metrics,
            protocol_specific=protocol_metrics,
            raw_latency_samples=latency_samples,
            raw_throughput_samples=throughput_samples,
            raw_timestamps=timestamps
        )
    
    def _test_dns_resolution(self, test_id: str, test_config: TrafficTestConfig,
                            source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test DNS resolution and collect metrics."""
        self.logger.info(f"Testing DNS resolution: {source_host} -> {target_host}")
        
        resolution_times = []
        timestamps = []
        successful_resolutions = 0
        failed_resolutions = 0
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            sample_start = time.time()
            
            try:
                # Execute DNS lookup via SSH on source host
                cmd = f"nslookup {target_host}"
                
                result = self.ssh_manager.execute_command(cmd, hosts=[source_host])
                
                if result and result[0].success:
                    resolution_time = (time.time() - sample_start) * 1000
                    resolution_times.append(resolution_time)
                    successful_resolutions += 1
                    timestamps.append(datetime.now())
                else:
                    failed_resolutions += 1
                
            except Exception as e:
                self.logger.warning(f"DNS test failed: {e}")
                failed_resolutions += 1
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        latency_metrics = self._calculate_latency_metrics(resolution_times)
        
        protocol_metrics = ProtocolSpecificMetrics()
        protocol_metrics.dns_resolution_times = resolution_times
        
        connection_metrics = ConnectionMetrics(
            total_connections=successful_resolutions + failed_resolutions,
            successful_connections=successful_resolutions,
            failed_connections=failed_resolutions,
            connection_success_rate=successful_resolutions / (successful_resolutions + failed_resolutions) * 100 if (successful_resolutions + failed_resolutions) > 0 else 0,
            avg_connection_time_ms=statistics.mean(resolution_times) if resolution_times else 0,
            connection_timeouts=0,
            connection_errors=[]
        )
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.DNS,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            latency=latency_metrics,
            connections=connection_metrics,
            protocol_specific=protocol_metrics,
            raw_latency_samples=resolution_times,
            raw_timestamps=timestamps
        )
    
    def _test_icmp_ping(self, test_id: str, test_config: TrafficTestConfig,
                       source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test ICMP ping and collect metrics."""
        self.logger.info(f"Testing ICMP ping: {source_host} -> {target_host}")
        
        latency_samples = []
        timestamps = []
        packets_sent = 0
        packets_received = 0
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            try:
                # Execute ping via SSH on source host
                cmd = f"ping -c 1 -W {test_config.timeout} {target_host}"
                
                result = self.ssh_manager.execute_command(cmd, hosts=[source_host])
                
                if result and result[0].success:
                    output = result[0].output
                    
                    # Parse ping output for latency
                    if "time=" in output:
                        time_part = output.split("time=")[1].split()[0]
                        latency = float(time_part)
                        latency_samples.append(latency)
                        packets_received += 1
                        timestamps.append(datetime.now())
                    
                    packets_sent += 1
                
            except Exception as e:
                self.logger.warning(f"ICMP test failed: {e}")
                packets_sent += 1
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        latency_metrics = self._calculate_latency_metrics(latency_samples)
        packet_metrics = self._calculate_packet_metrics(packets_sent, packets_received)
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.ICMP,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            latency=latency_metrics,
            packets=packet_metrics,
            raw_latency_samples=latency_samples,
            raw_timestamps=timestamps
        )
    
    def _test_scp_transfer(self, test_id: str, test_config: TrafficTestConfig,
                          source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test SCP file transfer and collect metrics."""
        self.logger.info(f"Testing SCP transfer: {source_host} -> {target_host}")
        
        transfer_speeds = []
        timestamps = []
        successful_transfers = 0
        failed_transfers = 0
        
        # Create test file
        test_file_size = test_config.packet_size * 100  # 100KB test file
        test_file_content = b'X' * test_file_size
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            try:
                # Create test file on source host
                create_cmd = f"echo '{test_file_content.decode()}' > /tmp/test_file_{test_id}.txt"
                self.ssh_manager.execute_command(create_cmd, hosts=[source_host])
                
                # Execute SCP transfer
                transfer_start = time.time()
                scp_cmd = f"scp -P {target_port} /tmp/test_file_{test_id}.txt user@{target_host}:/tmp/"
                
                result = self.ssh_manager.execute_command(scp_cmd, hosts=[source_host])
                
                if result and result[0].success:
                    transfer_time = time.time() - transfer_start
                    transfer_speed = test_file_size / transfer_time / 1024 / 1024  # MB/s
                    transfer_speeds.append(transfer_speed)
                    successful_transfers += 1
                    timestamps.append(datetime.now())
                else:
                    failed_transfers += 1
                
                # Cleanup
                cleanup_cmd = f"rm -f /tmp/test_file_{test_id}.txt"
                self.ssh_manager.execute_command(cleanup_cmd, hosts=[source_host])
                
            except Exception as e:
                self.logger.warning(f"SCP test failed: {e}")
                failed_transfers += 1
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        throughput_metrics = self._calculate_throughput_metrics(transfer_speeds)
        
        protocol_metrics = ProtocolSpecificMetrics()
        protocol_metrics.scp_transfer_speeds = transfer_speeds
        
        connection_metrics = ConnectionMetrics(
            total_connections=successful_transfers + failed_transfers,
            successful_connections=successful_transfers,
            failed_connections=failed_transfers,
            connection_success_rate=successful_transfers / (successful_transfers + failed_transfers) * 100 if (successful_transfers + failed_transfers) > 0 else 0,
            avg_connection_time_ms=0,
            connection_timeouts=0,
            connection_errors=[]
        )
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.SCP,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            throughput=throughput_metrics,
            connections=connection_metrics,
            protocol_specific=protocol_metrics,
            raw_throughput_samples=transfer_speeds,
            raw_timestamps=timestamps
        )
    
    def _test_ftp_transfer(self, test_id: str, test_config: TrafficTestConfig,
                          source_host: str, target_host: str, target_port: int) -> TrafficTestResult:
        """Test FTP file transfer and collect metrics."""
        self.logger.info(f"Testing FTP transfer: {source_host} -> {target_host}:{target_port}")
        
        transfer_speeds = []
        timestamps = []
        successful_transfers = 0
        failed_transfers = 0
        
        # Create test file
        test_file_size = test_config.packet_size * 100  # 100KB test file
        
        start_time = time.time()
        end_time = start_time + test_config.duration
        
        while time.time() < end_time:
            try:
                # Create test file on source host
                create_cmd = f"dd if=/dev/zero of=/tmp/test_file_{test_id}.txt bs={test_file_size} count=1"
                self.ssh_manager.execute_command(create_cmd, hosts=[source_host])
                
                # Execute FTP transfer
                transfer_start = time.time()
                ftp_cmd = f"ftp -n {target_host} {target_port} << EOF\n"
                ftp_cmd += f"user {test_config.ftp_credentials[0]} {test_config.ftp_credentials[1]}\n"
                ftp_cmd += f"put /tmp/test_file_{test_id}.txt\n"
                ftp_cmd += "quit\n"
                ftp_cmd += "EOF"
                
                result = self.ssh_manager.execute_command(ftp_cmd, hosts=[source_host])
                
                if result and result[0].success:
                    transfer_time = time.time() - transfer_start
                    transfer_speed = test_file_size / transfer_time / 1024 / 1024  # MB/s
                    transfer_speeds.append(transfer_speed)
                    successful_transfers += 1
                    timestamps.append(datetime.now())
                else:
                    failed_transfers += 1
                
                # Cleanup
                cleanup_cmd = f"rm -f /tmp/test_file_{test_id}.txt"
                self.ssh_manager.execute_command(cleanup_cmd, hosts=[source_host])
                
            except Exception as e:
                self.logger.warning(f"FTP test failed: {e}")
                failed_transfers += 1
            
            time.sleep(test_config.interval)
        
        # Calculate metrics
        throughput_metrics = self._calculate_throughput_metrics(transfer_speeds)
        
        protocol_metrics = ProtocolSpecificMetrics()
        protocol_metrics.ftp_transfer_speeds = transfer_speeds
        
        connection_metrics = ConnectionMetrics(
            total_connections=successful_transfers + failed_transfers,
            successful_connections=successful_transfers,
            failed_connections=failed_transfers,
            connection_success_rate=successful_transfers / (successful_transfers + failed_transfers) * 100 if (successful_transfers + failed_transfers) > 0 else 0,
            avg_connection_time_ms=0,
            connection_timeouts=0,
            connection_errors=[]
        )
        
        return TrafficTestResult(
            test_id=test_id,
            protocol=ProtocolType.FTP,
            direction=test_config.direction,
            source_host=source_host,
            target_host=target_host,
            target_port=target_port,
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=test_config.duration,
            success=True,
            throughput=throughput_metrics,
            connections=connection_metrics,
            protocol_specific=protocol_metrics,
            raw_throughput_samples=transfer_speeds,
            raw_timestamps=timestamps
        )
    
    def _calculate_latency_metrics(self, samples: List[float]) -> LatencyMetrics:
        """Calculate latency metrics from samples."""
        if not samples:
            return LatencyMetrics(0, 0, 0, 0, 0, 0, 0)
        
        return LatencyMetrics(
            min_latency_ms=min(samples),
            max_latency_ms=max(samples),
            avg_latency_ms=statistics.mean(samples),
            median_latency_ms=statistics.median(samples),
            p95_latency_ms=statistics.quantiles(samples, n=20)[18] if len(samples) >= 20 else max(samples),
            p99_latency_ms=statistics.quantiles(samples, n=100)[98] if len(samples) >= 100 else max(samples),
            std_deviation_ms=statistics.stdev(samples) if len(samples) > 1 else 0,
            latency_samples=samples
        )
    
    def _calculate_throughput_metrics(self, samples: List[float]) -> ThroughputMetrics:
        """Calculate throughput metrics from samples."""
        if not samples:
            return ThroughputMetrics(0, 0, 0, 0, 0)
        
        total_bytes = sum(samples) * 1024 * 1024  # Convert MB/s to bytes
        
        return ThroughputMetrics(
            total_bytes_sent=total_bytes,
            total_bytes_received=total_bytes,
            avg_throughput_mbps=statistics.mean(samples),
            peak_throughput_mbps=max(samples),
            min_throughput_mbps=min(samples),
            throughput_samples=samples
        )
    
    def _calculate_packet_metrics(self, sent: int, received: int) -> PacketMetrics:
        """Calculate packet metrics."""
        lost = sent - received
        loss_percent = (lost / sent * 100) if sent > 0 else 0
        
        return PacketMetrics(
            packets_sent=sent,
            packets_received=received,
            packets_lost=lost,
            packet_loss_percent=loss_percent,
            duplicate_packets=0,  # Would need more sophisticated tracking
            out_of_order_packets=0,  # Would need sequence numbers
            corrupted_packets=0  # Would need checksums
        )
    
    def _calculate_connection_metrics(self, connection_times: List[float]) -> ConnectionMetrics:
        """Calculate connection metrics."""
        if not connection_times:
            return ConnectionMetrics(0, 0, 0, 0, 0, 0)
        
        return ConnectionMetrics(
            total_connections=len(connection_times),
            successful_connections=len(connection_times),
            failed_connections=0,
            connection_success_rate=100.0,
            avg_connection_time_ms=statistics.mean(connection_times),
            connection_timeouts=0,
            connection_errors=[]
        )
    
    def export_results(self, results: Dict[str, TrafficTestResult], filename: str, format: str = "json"):
        """Export traffic test results to file."""
        if format == "json":
            data = []
            for result in results.values():
                data.append({
                    'test_id': result.test_id,
                    'protocol': result.protocol.value,
                    'direction': result.direction.value,
                    'source_host': result.source_host,
                    'target_host': result.target_host,
                    'target_port': result.target_port,
                    'start_time': result.start_time.isoformat(),
                    'end_time': result.end_time.isoformat(),
                    'duration_seconds': result.duration_seconds,
                    'success': result.success,
                    'error_message': result.error_message,
                    'latency': self._serialize_latency_metrics(result.latency),
                    'throughput': self._serialize_throughput_metrics(result.throughput),
                    'packets': self._serialize_packet_metrics(result.packets),
                    'connections': self._serialize_connection_metrics(result.connections),
                    'protocol_specific': self._serialize_protocol_metrics(result.protocol_specific)
                })
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'test_id', 'protocol', 'direction', 'source_host', 'target_host', 'target_port',
                    'start_time', 'end_time', 'duration_seconds', 'success', 'error_message',
                    'avg_latency_ms', 'min_latency_ms', 'max_latency_ms', 'p95_latency_ms',
                    'avg_throughput_mbps', 'peak_throughput_mbps', 'packet_loss_percent',
                    'connection_success_rate'
                ])
                
                for result in results.values():
                    writer.writerow([
                        result.test_id,
                        result.protocol.value,
                        result.direction.value,
                        result.source_host,
                        result.target_host,
                        result.target_port,
                        result.start_time.isoformat(),
                        result.end_time.isoformat(),
                        result.duration_seconds,
                        result.success,
                        result.error_message,
                        result.latency.avg_latency_ms if result.latency else 0,
                        result.latency.min_latency_ms if result.latency else 0,
                        result.latency.max_latency_ms if result.latency else 0,
                        result.latency.p95_latency_ms if result.latency else 0,
                        result.throughput.avg_throughput_mbps if result.throughput else 0,
                        result.throughput.peak_throughput_mbps if result.throughput else 0,
                        result.packets.packet_loss_percent if result.packets else 0,
                        result.connections.connection_success_rate if result.connections else 0
                    ])
    
    def _serialize_latency_metrics(self, metrics: Optional[LatencyMetrics]) -> Optional[Dict[str, Any]]:
        """Serialize latency metrics to dict."""
        if metrics is None:
            return None
        return {
            'min_latency_ms': metrics.min_latency_ms,
            'max_latency_ms': metrics.max_latency_ms,
            'avg_latency_ms': metrics.avg_latency_ms,
            'median_latency_ms': metrics.median_latency_ms,
            'p95_latency_ms': metrics.p95_latency_ms,
            'p99_latency_ms': metrics.p99_latency_ms,
            'std_deviation_ms': metrics.std_deviation_ms
        }
    
    def _serialize_throughput_metrics(self, metrics: Optional[ThroughputMetrics]) -> Optional[Dict[str, Any]]:
        """Serialize throughput metrics to dict."""
        if metrics is None:
            return None
        return {
            'total_bytes_sent': metrics.total_bytes_sent,
            'total_bytes_received': metrics.total_bytes_received,
            'avg_throughput_mbps': metrics.avg_throughput_mbps,
            'peak_throughput_mbps': metrics.peak_throughput_mbps,
            'min_throughput_mbps': metrics.min_throughput_mbps
        }
    
    def _serialize_packet_metrics(self, metrics: Optional[PacketMetrics]) -> Optional[Dict[str, Any]]:
        """Serialize packet metrics to dict."""
        if metrics is None:
            return None
        return {
            'packets_sent': metrics.packets_sent,
            'packets_received': metrics.packets_received,
            'packets_lost': metrics.packets_lost,
            'packet_loss_percent': metrics.packet_loss_percent,
            'duplicate_packets': metrics.duplicate_packets,
            'out_of_order_packets': metrics.out_of_order_packets,
            'corrupted_packets': metrics.corrupted_packets
        }
    
    def _serialize_connection_metrics(self, metrics: Optional[ConnectionMetrics]) -> Optional[Dict[str, Any]]:
        """Serialize connection metrics to dict."""
        if metrics is None:
            return None
        return {
            'total_connections': metrics.total_connections,
            'successful_connections': metrics.successful_connections,
            'failed_connections': metrics.failed_connections,
            'connection_success_rate': metrics.connection_success_rate,
            'avg_connection_time_ms': metrics.avg_connection_time_ms,
            'connection_timeouts': metrics.connection_timeouts,
            'connection_errors': metrics.connection_errors
        }
    
    def _serialize_protocol_metrics(self, metrics: Optional[ProtocolSpecificMetrics]) -> Optional[Dict[str, Any]]:
        """Serialize protocol-specific metrics to dict."""
        if metrics is None:
            return None
        return {
            'http_status_codes': metrics.http_status_codes,
            'dns_resolution_times': metrics.dns_resolution_times,
            'ftp_transfer_speeds': metrics.ftp_transfer_speeds,
            'scp_transfer_speeds': metrics.scp_transfer_speeds,
            'ssl_handshake_times': metrics.ssl_handshake_times,
            'tcp_retransmissions': metrics.tcp_retransmissions,
            'udp_jitter_ms': metrics.udp_jitter_ms
        } 