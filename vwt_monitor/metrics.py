"""
Metrics collection module for SSH Tool.
"""

import time
import threading
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
import psutil
from prometheus_client import start_http_server, Counter, Gauge, Histogram, Summary


@dataclass
class OperationMetrics:
    """Metrics for a single operation."""
    operation_type: str
    host: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    success: bool = False
    error_message: Optional[str] = None
    bytes_transferred: int = 0
    exit_code: Optional[int] = None


@dataclass
class HostMetrics:
    """Aggregated metrics for a host."""
    host: str
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    total_bytes_transferred: int = 0
    last_operation: Optional[datetime] = None
    connection_count: int = 0
    connection_failures: int = 0


class MetricsCollector:
    """Collector for SSH operation metrics."""
    
    def __init__(self, enable_prometheus: bool = True, prometheus_port: int = 9090):
        """
        Initialize metrics collector.
        
        Args:
            enable_prometheus: Enable Prometheus metrics
            prometheus_port: Prometheus server port
        """
        self.enable_prometheus = enable_prometheus
        self.prometheus_port = prometheus_port
        
        # Metrics storage
        self.operations: List[OperationMetrics] = []
        self.host_metrics: Dict[str, HostMetrics] = defaultdict(lambda: HostMetrics(host=""))
        
        # Real-time metrics
        self.recent_operations = deque(maxlen=1000)
        self.operation_times = deque(maxlen=1000)
        
        # System metrics
        self.system_metrics = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'disk_usage': 0.0,
            'network_io': {'bytes_sent': 0, 'bytes_recv': 0}
        }
        
        # Threading
        self.lock = threading.RLock()
        self.monitoring_thread = None
        self.stop_monitoring = threading.Event()
        
        # Prometheus metrics
        if enable_prometheus:
            self._setup_prometheus_metrics()
            start_http_server(prometheus_port)
        
        # Start monitoring
        self._start_monitoring()
    
    def _setup_prometheus_metrics(self):
        """Setup Prometheus metrics."""
        # Counters
        self.prometheus_counters = {
            'ssh_operations_total': Counter(
                'ssh_operations_total',
                'Total number of SSH operations',
                ['operation_type', 'host', 'status']
            ),
            'ssh_connections_total': Counter(
                'ssh_connections_total',
                'Total number of SSH connections',
                ['host', 'status']
            ),
            'bytes_transferred_total': Counter(
                'bytes_transferred_total',
                'Total bytes transferred',
                ['operation_type', 'host']
            )
        }
        
        # Gauges
        self.prometheus_gauges = {
            'active_connections': Gauge(
                'ssh_active_connections',
                'Number of active SSH connections',
                ['host']
            ),
            'operation_duration_seconds': Gauge(
                'ssh_operation_duration_seconds',
                'Duration of SSH operations',
                ['operation_type', 'host']
            )
        }
        
        # Histograms
        self.prometheus_histograms = {
            'operation_duration': Histogram(
                'ssh_operation_duration_histogram',
                'Histogram of SSH operation durations',
                ['operation_type', 'host'],
                buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
            )
        }
        
        # Summaries
        self.prometheus_summaries = {
            'operation_duration_summary': Summary(
                'ssh_operation_duration_summary',
                'Summary of SSH operation durations',
                ['operation_type', 'host']
            )
        }
    
    def _start_monitoring(self):
        """Start system monitoring thread."""
        def monitoring_worker():
            while not self.stop_monitoring.is_set():
                try:
                    self._collect_system_metrics()
                    time.sleep(5)  # Collect every 5 seconds
                except Exception as e:
                    print(f"Monitoring error: {e}")
        
        self.monitoring_thread = threading.Thread(target=monitoring_worker, daemon=True)
        self.monitoring_thread.start()
    
    def _collect_system_metrics(self):
        """Collect system metrics."""
        try:
            # CPU usage
            self.system_metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_metrics['memory_usage'] = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_metrics['disk_usage'] = disk.percent
            
            # Network I/O
            network = psutil.net_io_counters()
            self.system_metrics['network_io'] = {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv
            }
            
        except Exception as e:
            print(f"Error collecting system metrics: {e}")
    
    def start_operation(self, operation_type: str, host: str) -> str:
        """
        Start tracking an operation.
        
        Args:
            operation_type: Type of operation (command, upload, download, etc.)
            host: Target host
            
        Returns:
            Operation ID
        """
        operation_id = f"{operation_type}_{host}_{int(time.time() * 1000)}"
        
        operation = OperationMetrics(
            operation_type=operation_type,
            host=host,
            start_time=datetime.now()
        )
        
        with self.lock:
            self.operations.append(operation)
            self.recent_operations.append(operation)
            
            # Update host metrics
            if host not in self.host_metrics:
                self.host_metrics[host] = HostMetrics(host=host)
            
            self.host_metrics[host].total_operations += 1
            self.host_metrics[host].last_operation = datetime.now()
        
        return operation_id
    
    def end_operation(self, operation_id: str, success: bool = True, 
                     error_message: str = None, bytes_transferred: int = 0,
                     exit_code: int = None):
        """
        End tracking an operation.
        
        Args:
            operation_id: Operation ID
            success: Whether operation was successful
            error_message: Error message if failed
            bytes_transferred: Bytes transferred
            exit_code: Exit code for command operations
        """
        with self.lock:
            # Find operation
            operation = None
            for op in self.operations:
                if f"{op.operation_type}_{op.host}_{int(op.start_time.timestamp() * 1000)}" == operation_id:
                    operation = op
                    break
            
            if operation:
                operation.end_time = datetime.now()
                operation.duration = (operation.end_time - operation.start_time).total_seconds()
                operation.success = success
                operation.error_message = error_message
                operation.bytes_transferred = bytes_transferred
                operation.exit_code = exit_code
                
                # Update host metrics
                host_metrics = self.host_metrics[operation.host]
                if success:
                    host_metrics.successful_operations += 1
                else:
                    host_metrics.failed_operations += 1
                
                host_metrics.total_duration += operation.duration
                host_metrics.avg_duration = host_metrics.total_duration / host_metrics.total_operations
                host_metrics.min_duration = min(host_metrics.min_duration, operation.duration)
                host_metrics.max_duration = max(host_metrics.max_duration, operation.duration)
                host_metrics.total_bytes_transferred += bytes_transferred
                
                # Update real-time metrics
                self.operation_times.append(operation.duration)
                
                # Update Prometheus metrics
                if self.enable_prometheus:
                    self._update_prometheus_metrics(operation)
    
    def _update_prometheus_metrics(self, operation: OperationMetrics):
        """Update Prometheus metrics."""
        status = 'success' if operation.success else 'failure'
        
        # Counters
        self.prometheus_counters['ssh_operations_total'].labels(
            operation_type=operation.operation_type,
            host=operation.host,
            status=status
        ).inc()
        
        if operation.bytes_transferred > 0:
            self.prometheus_counters['bytes_transferred_total'].labels(
                operation_type=operation.operation_type,
                host=operation.host
            ).inc(operation.bytes_transferred)
        
        # Gauges
        self.prometheus_gauges['operation_duration_seconds'].labels(
            operation_type=operation.operation_type,
            host=operation.host
        ).set(operation.duration)
        
        # Histograms
        self.prometheus_histograms['operation_duration'].labels(
            operation_type=operation.operation_type,
            host=operation.host
        ).observe(operation.duration)
        
        # Summaries
        self.prometheus_summaries['operation_duration_summary'].labels(
            operation_type=operation.operation_type,
            host=operation.host
        ).observe(operation.duration)
    
    def log_connection_event(self, host: str, event: str, success: bool = True):
        """
        Log a connection event.
        
        Args:
            host: Target host
            event: Event type (connect, disconnect, failure)
            success: Whether event was successful
        """
        with self.lock:
            if host not in self.host_metrics:
                self.host_metrics[host] = HostMetrics(host=host)
            
            host_metrics = self.host_metrics[host]
            
            if event == 'connect':
                host_metrics.connection_count += 1
            elif event == 'failure':
                host_metrics.connection_failures += 1
            
            # Update Prometheus metrics
            if self.enable_prometheus:
                status = 'success' if success else 'failure'
                self.prometheus_counters['ssh_connections_total'].labels(
                    host=host,
                    status=status
                ).inc()
    
    def get_operation_metrics(self, operation_type: str = None, 
                            host: str = None, limit: int = 100) -> List[OperationMetrics]:
        """
        Get operation metrics with optional filtering.
        
        Args:
            operation_type: Filter by operation type
            host: Filter by host
            limit: Maximum number of results
            
        Returns:
            List of operation metrics
        """
        with self.lock:
            filtered_operations = self.operations
            
            if operation_type:
                filtered_operations = [op for op in filtered_operations if op.operation_type == operation_type]
            
            if host:
                filtered_operations = [op for op in filtered_operations if op.host == host]
            
            return filtered_operations[-limit:]
    
    def get_host_metrics(self, host: str = None) -> Dict[str, HostMetrics]:
        """
        Get host metrics.
        
        Args:
            host: Specific host (None for all hosts)
            
        Returns:
            Dictionary of host metrics
        """
        with self.lock:
            if host:
                return {host: self.host_metrics.get(host, HostMetrics(host=host))}
            else:
                return dict(self.host_metrics)
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """
        Get system metrics.
        
        Returns:
            Dictionary of system metrics
        """
        return dict(self.system_metrics)
    
    def get_summary_metrics(self) -> Dict[str, Any]:
        """
        Get summary metrics.
        
        Returns:
            Dictionary of summary metrics
        """
        with self.lock:
            total_operations = len(self.operations)
            successful_operations = sum(1 for op in self.operations if op.success)
            failed_operations = total_operations - successful_operations
            
            total_duration = sum(op.duration or 0 for op in self.operations)
            avg_duration = total_duration / total_operations if total_operations > 0 else 0
            
            total_bytes = sum(op.bytes_transferred for op in self.operations)
            
            return {
                'total_operations': total_operations,
                'successful_operations': successful_operations,
                'failed_operations': failed_operations,
                'success_rate': (successful_operations / total_operations * 100) if total_operations > 0 else 0,
                'total_duration': total_duration,
                'avg_duration': avg_duration,
                'total_bytes_transferred': total_bytes,
                'unique_hosts': len(self.host_metrics),
                'recent_operations': len(self.recent_operations),
                'system_metrics': self.system_metrics
            }
    
    def export_metrics(self, filename: str, format: str = "json"):
        """
        Export metrics to file.
        
        Args:
            filename: Output filename
            format: Export format (json, csv)
        """
        if format == "json":
            data = {
                'summary': self.get_summary_metrics(),
                'host_metrics': {
                    host: {
                        'total_operations': metrics.total_operations,
                        'successful_operations': metrics.successful_operations,
                        'failed_operations': metrics.failed_operations,
                        'total_duration': metrics.total_duration,
                        'avg_duration': metrics.avg_duration,
                        'min_duration': metrics.min_duration,
                        'max_duration': metrics.max_duration,
                        'total_bytes_transferred': metrics.total_bytes_transferred,
                        'connection_count': metrics.connection_count,
                        'connection_failures': metrics.connection_failures
                    }
                    for host, metrics in self.host_metrics.items()
                },
                'recent_operations': [
                    {
                        'operation_type': op.operation_type,
                        'host': op.host,
                        'start_time': op.start_time.isoformat(),
                        'end_time': op.end_time.isoformat() if op.end_time else None,
                        'duration': op.duration,
                        'success': op.success,
                        'error_message': op.error_message,
                        'bytes_transferred': op.bytes_transferred,
                        'exit_code': op.exit_code
                    }
                    for op in self.recent_operations
                ],
                'system_metrics': self.system_metrics,
                'export_time': datetime.now().isoformat()
            }
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
        
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'operation_type', 'host', 'start_time', 'end_time', 'duration',
                    'success', 'error_message', 'bytes_transferred', 'exit_code'
                ])
                
                for op in self.operations:
                    writer.writerow([
                        op.operation_type,
                        op.host,
                        op.start_time.isoformat(),
                        op.end_time.isoformat() if op.end_time else '',
                        op.duration or '',
                        op.success,
                        op.error_message or '',
                        op.bytes_transferred,
                        op.exit_code or ''
                    ])
    
    def clear_metrics(self):
        """Clear all metrics."""
        with self.lock:
            self.operations.clear()
            self.host_metrics.clear()
            self.recent_operations.clear()
            self.operation_times.clear()
    
    def stop_monitoring(self):
        """Stop monitoring."""
        self.stop_monitoring.set()
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_monitoring() 