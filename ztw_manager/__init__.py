"""
ZTWorkload Manager - A high-performance, parallel SSH tool for workload management.

This package provides comprehensive SSH management capabilities with advanced features
for workload management, network testing, and real-time monitoring.

Key Components:
- SSHManager: Core SSH connection and command execution
- TrafficManager: Network traffic testing and monitoring
- IperfManager: Performance testing with iperf3
- LogCapture: Real-time log monitoring
- StructuredLogger: Advanced logging with multiple formats
- ConnectionPool: Efficient connection management
- ChannelManager: Persistent SSH channels for complex workflows

Features:
- Parallel SSH operations with configurable concurrency
- Chain command execution using persistent channels
- Interactive commands with expect patterns
- Real-time log capture and monitoring
- Network traffic testing (TCP, UDP, HTTP, HTTPS, DNS, ICMP)
- File transfer with progress tracking and checksum verification
- Connection pooling with health monitoring
- Jumphost support with SSH tunneling
- Comprehensive metrics and export capabilities

Example usage:
    from ztw_manager import SSHManager, Config
    
    config = Config.load('config.yaml')
    with SSHManager(config) as manager:
        results = manager.execute_command('hostname')
        for result in results:
            print(f"{result.host}: {result.output}")
"""

# Author: Vamsi

# Import main classes and functions
from .config import Config
from .logger import StructuredLogger, HostLogger
from .ssh_manager import SSHManager, CommandResult, FileTransferResult
from .traffic_manager import (
    TrafficManager, TrafficTestConfig, TrafficTestResult,
    ProtocolType, Direction, LatencyMetrics, ThroughputMetrics,
    PacketMetrics, ConnectionMetrics, ProtocolSpecificMetrics
)
from .iperf_manager import IperfManager, IperfTestConfig, IperfTestResult
from .log_capture import LogCapture, LogCaptureConfig, LogEntry
from .connection_pool import ConnectionPool, JumphostConnectionPool, ConnectionInfo
from .channel_manager import ChannelManager, ChannelCommand, ChannelResult

__version__ = "1.0.0"
__email__ = "vamsi@example.com"

# Export main classes
__all__ = [
    'SSHManager', 'Config', 'StructuredLogger', 'HostLogger',
    'CommandResult', 'FileTransferResult', 'TrafficManager',
    'TrafficTestConfig', 'TrafficTestResult', 'ProtocolType',
    'Direction', 'LatencyMetrics', 'ThroughputMetrics',
    'PacketMetrics', 'ConnectionMetrics', 'ProtocolSpecificMetrics',
    'IperfManager', 'IperfTestConfig', 'IperfTestResult',
    'LogCapture', 'LogCaptureConfig', 'LogEntry',
    'ConnectionPool', 'JumphostConnectionPool', 'ConnectionInfo',
    'ChannelManager', 'ChannelCommand', 'ChannelResult'
] 