"""
Real-time log capture module for SSH Tool.
"""

import os
import time
import threading
import asyncio
import json
import gzip
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any, Union
from pathlib import Path
import paramiko
from paramiko import SSHClient
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import queue
from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout


@dataclass
class LogEntry:
    """A log entry with metadata."""
    host: str
    timestamp: datetime
    level: str
    message: str
    source_file: str
    line_number: Optional[int] = None
    process_id: Optional[int] = None
    thread_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogCaptureConfig:
    """Configuration for log capture."""
    buffer_size: int = 8192
    flush_interval: float = 1.0
    max_file_size: str = "100MB"
    rotation_count: int = 5
    compression: bool = True
    real_time_display: bool = True
    filter_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)


class LogCapture:
    """Real-time log capture from remote hosts."""
    
    def __init__(self, config: LogCaptureConfig, logger=None):
        """
        Initialize log capture.
        
        Args:
            config: Log capture configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger
        self.console = Console()
        
        # Log storage
        self.log_buffer: List[LogEntry] = []
        self.log_files: Dict[str, str] = {}  # host -> log file path
        
        # Capture threads
        self.capture_threads: Dict[str, threading.Thread] = {}
        self.stop_events: Dict[str, threading.Event] = {}
        
        # Output management
        self.output_dir = "logs/captured"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Statistics
        self.stats = {
            'total_entries': 0,
            'entries_by_host': {},
            'entries_by_level': {},
            'start_time': datetime.now()
        }
        
        # Real-time display
        self.display_thread = None
        self.display_stop_event = threading.Event()
        
        if config.real_time_display:
            self._start_display_thread()
    
    def start_capture(self, host: str, ssh_client: SSHClient, log_file_path: str):
        """
        Start capturing logs from a remote host.
        
        Args:
            host: Target host
            ssh_client: SSH client connection
            log_file_path: Path to log file on remote host
        """
        if host in self.capture_threads:
            self.logger.warning(f"Log capture already running for {host}")
            return
        
        # Create stop event
        stop_event = threading.Event()
        self.stop_events[host] = stop_event
        
        # Create capture thread
        thread = threading.Thread(
            target=self._capture_logs,
            args=(host, ssh_client, log_file_path, stop_event),
            daemon=True
        )
        
        self.capture_threads[host] = thread
        thread.start()
        
        self.logger.info(f"Started log capture for {host}: {log_file_path}")
    
    def stop_capture(self, host: str):
        """
        Stop capturing logs from a host.
        
        Args:
            host: Target host
        """
        if host in self.stop_events:
            self.stop_events[host].set()
            
            if host in self.capture_threads:
                self.capture_threads[host].join(timeout=5)
                del self.capture_threads[host]
            
            del self.stop_events[host]
            self.logger.info(f"Stopped log capture for {host}")
    
    def stop_all_captures(self):
        """Stop all log captures."""
        for host in list(self.stop_events.keys()):
            self.stop_capture(host)
    
    def _capture_logs(self, host: str, ssh_client: SSHClient, log_file_path: str, stop_event: threading.Event):
        """
        Capture logs from remote host.
        
        Args:
            host: Target host
            ssh_client: SSH client connection
            log_file_path: Path to log file on remote host
            stop_event: Stop event for this capture
        """
        try:
            # Create session for log tailing
            session = ssh_client.get_transport().open_session()
            
            # Execute tail command
            tail_command = f"tail -f {log_file_path}"
            session.exec_command(tail_command)
            
            # Get stdout and stderr
            stdout = session.makefile('r', -1)
            stderr = session.makefile_stderr('r', -1)
            
            # Create local log file
            local_log_file = os.path.join(self.output_dir, f"{host}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
            self.log_files[host] = local_log_file
            
            with open(local_log_file, 'w', encoding='utf-8') as f:
                while not stop_event.is_set():
                    # Read from stdout
                    line = stdout.readline()
                    if line:
                        line = line.strip()
                        if line and self._should_process_line(line):
                            log_entry = self._parse_log_line(host, line, log_file_path)
                            if log_entry:
                                self._process_log_entry(log_entry, f)
                    
                    # Read from stderr
                    error_line = stderr.readline()
                    if error_line:
                        error_line = error_line.strip()
                        if error_line:
                            self.logger.warning(f"Log capture error for {host}: {error_line}")
                    
                    # Small delay to prevent busy waiting
                    time.sleep(0.1)
            
            session.close()
            
        except Exception as e:
            self.logger.error(f"Log capture error for {host}: {e}")
        finally:
            if host in self.log_files:
                del self.log_files[host]
    
    def _should_process_line(self, line: str) -> bool:
        """
        Check if a log line should be processed based on filters.
        
        Args:
            line: Log line to check
            
        Returns:
            True if line should be processed
        """
        # Check exclude patterns
        for pattern in self.config.exclude_patterns:
            if pattern in line:
                return False
        
        # Check include patterns
        if self.config.filter_patterns:
            for pattern in self.config.filter_patterns:
                if pattern in line:
                    return True
            return False
        
        return True
    
    def _parse_log_line(self, host: str, line: str, source_file: str) -> Optional[LogEntry]:
        """
        Parse a log line into a LogEntry.
        
        Args:
            host: Source host
            line: Log line
            source_file: Source file path
            
        Returns:
            LogEntry if parsing successful, None otherwise
        """
        try:
            # Try to parse common log formats
            timestamp = datetime.now()  # Default timestamp
            
            # Try to extract timestamp from line
            # This is a simple implementation - can be enhanced for specific log formats
            if '[' in line and ']' in line:
                timestamp_str = line[line.find('[')+1:line.find(']')]
                try:
                    # Try common timestamp formats
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%b %d %H:%M:%S']:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            # Try to extract log level
            level = "INFO"  # Default level
            level_indicators = {
                'ERROR': ['ERROR', 'error', 'ERR', 'err'],
                'WARNING': ['WARNING', 'warning', 'WARN', 'warn'],
                'DEBUG': ['DEBUG', 'debug'],
                'CRITICAL': ['CRITICAL', 'critical', 'FATAL', 'fatal']
            }
            
            for level_name, indicators in level_indicators.items():
                if any(indicator in line for indicator in indicators):
                    level = level_name
                    break
            
            return LogEntry(
                host=host,
                timestamp=timestamp,
                level=level,
                message=line,
                source_file=source_file
            )
            
        except Exception as e:
            self.logger.debug(f"Failed to parse log line: {e}")
            return None
    
    def _process_log_entry(self, log_entry: LogEntry, file_handle):
        """
        Process a log entry.
        
        Args:
            log_entry: Log entry to process
            file_handle: File handle to write to
        """
        # Add to buffer
        self.log_buffer.append(log_entry)
        
        # Maintain buffer size
        if len(self.log_buffer) > self.config.buffer_size:
            self.log_buffer.pop(0)
        
        # Write to file
        log_line = f"{log_entry.timestamp.isoformat()} [{log_entry.level}] {log_entry.host}: {log_entry.message}\n"
        file_handle.write(log_line)
        file_handle.flush()
        
        # Update statistics
        self.stats['total_entries'] += 1
        
        if log_entry.host not in self.stats['entries_by_host']:
            self.stats['entries_by_host'][log_entry.host] = 0
        self.stats['entries_by_host'][log_entry.host] += 1
        
        if log_entry.level not in self.stats['entries_by_level']:
            self.stats['entries_by_level'][log_entry.level] = 0
        self.stats['entries_by_level'][log_entry.level] += 1
    
    def _start_display_thread(self):
        """Start real-time display thread."""
        def display_worker():
            layout = self._create_display_layout()
            
            with Live(layout, refresh_per_second=2, screen=True):
                while not self.display_stop_event.is_set():
                    try:
                        self._update_display(layout)
                        time.sleep(0.5)
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        self.logger.error(f"Display error: {e}")
        
        self.display_thread = threading.Thread(target=display_worker, daemon=True)
        self.display_thread.start()
    
    def _create_display_layout(self) -> Layout:
        """Create display layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="logs", ratio=2),
            Layout(name="stats", ratio=1)
        )
        
        return layout
    
    def _update_display(self, layout: Layout):
        """Update the display."""
        # Header
        header = Panel(
            f"[bold blue]Real-time Log Capture Dashboard[/bold blue]\n"
            f"Active captures: {len(self.capture_threads)} | "
            f"Total entries: {self.stats['total_entries']}",
            title="Log Capture"
        )
        layout["header"].update(header)
        
        # Recent logs
        recent_logs = self.log_buffer[-20:] if self.log_buffer else []
        log_table = Table(title="Recent Logs")
        log_table.add_column("Time", style="cyan")
        log_table.add_column("Host", style="green")
        log_table.add_column("Level", style="magenta")
        log_table.add_column("Message", style="white")
        
        for entry in recent_logs:
            level_color = {
                'ERROR': 'red',
                'WARNING': 'yellow',
                'DEBUG': 'blue',
                'CRITICAL': 'red',
                'INFO': 'green'
            }.get(entry.level, 'white')
            
            log_table.add_row(
                entry.timestamp.strftime('%H:%M:%S'),
                entry.host,
                f"[{level_color}]{entry.level}[/{level_color}]",
                entry.message[:50] + "..." if len(entry.message) > 50 else entry.message
            )
        
        layout["logs"].update(Panel(log_table))
        
        # Statistics
        stats_table = Table(title="Statistics")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", style="green")
        
        uptime = datetime.now() - self.stats['start_time']
        stats_table.add_row("Uptime", f"{uptime.total_seconds():.1f}s")
        stats_table.add_row("Active Captures", str(len(self.capture_threads)))
        stats_table.add_row("Buffer Size", str(len(self.log_buffer)))
        
        for level, count in self.stats['entries_by_level'].items():
            stats_table.add_row(f"{level} Entries", str(count))
        
        layout["stats"].update(Panel(stats_table))
        
        # Footer
        footer = Panel(
            f"[bold]Status:[/bold] Active | "
            f"[bold]Output Dir:[/bold] {self.output_dir} | "
            f"[bold]Buffer:[/bold] {len(self.log_buffer)}/{self.config.buffer_size}",
            title="Status"
        )
        layout["footer"].update(footer)
    
    def get_recent_logs(self, count: int = 100) -> List[LogEntry]:
        """
        Get recent log entries.
        
        Args:
            count: Number of entries to return
            
        Returns:
            List of recent log entries
        """
        return self.log_buffer[-count:] if self.log_buffer else []
    
    def get_logs_by_host(self, host: str, count: int = 100) -> List[LogEntry]:
        """
        Get log entries for a specific host.
        
        Args:
            host: Target host
            count: Number of entries to return
            
        Returns:
            List of log entries for the host
        """
        host_logs = [entry for entry in self.log_buffer if entry.host == host]
        return host_logs[-count:] if host_logs else []
    
    def get_logs_by_level(self, level: str, count: int = 100) -> List[LogEntry]:
        """
        Get log entries by level.
        
        Args:
            level: Log level
            count: Number of entries to return
            
        Returns:
            List of log entries with the specified level
        """
        level_logs = [entry for entry in self.log_buffer if entry.level == level.upper()]
        return level_logs[-count:] if level_logs else []
    
    def export_logs(self, filename: str, format: str = "json", 
                   hosts: List[str] = None, levels: List[str] = None):
        """
        Export logs to file.
        
        Args:
            filename: Output filename
            format: Export format (json, csv, text)
            hosts: Filter by hosts
            levels: Filter by levels
        """
        # Filter logs
        filtered_logs = self.log_buffer
        
        if hosts:
            filtered_logs = [entry for entry in filtered_logs if entry.host in hosts]
        
        if levels:
            filtered_logs = [entry for entry in filtered_logs if entry.level in levels]
        
        # Export based on format
        if format == "json":
            with open(filename, 'w') as f:
                json.dump([{
                    'host': entry.host,
                    'timestamp': entry.timestamp.isoformat(),
                    'level': entry.level,
                    'message': entry.message,
                    'source_file': entry.source_file,
                    'metadata': entry.metadata
                } for entry in filtered_logs], f, indent=2)
        
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'host', 'level', 'message', 'source_file'])
                for entry in filtered_logs:
                    writer.writerow([
                        entry.timestamp.isoformat(),
                        entry.host,
                        entry.level,
                        entry.message,
                        entry.source_file
                    ])
        
        elif format == "text":
            with open(filename, 'w') as f:
                for entry in filtered_logs:
                    f.write(f"{entry.timestamp.isoformat()} [{entry.level}] {entry.host}: {entry.message}\n")
        
        self.logger.info(f"Exported {len(filtered_logs)} log entries to {filename}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get log capture statistics.
        
        Returns:
            Dictionary with statistics
        """
        uptime = datetime.now() - self.stats['start_time']
        
        return {
            'total_entries': self.stats['total_entries'],
            'entries_by_host': self.stats['entries_by_host'],
            'entries_by_level': self.stats['entries_by_level'],
            'uptime_seconds': uptime.total_seconds(),
            'active_captures': len(self.capture_threads),
            'buffer_size': len(self.log_buffer),
            'start_time': self.stats['start_time'].isoformat()
        }
    
    def clear_buffer(self):
        """Clear the log buffer."""
        self.log_buffer.clear()
        self.logger.info("Log buffer cleared")
    
    def stop_display(self):
        """Stop the real-time display."""
        self.display_stop_event.set()
        if self.display_thread:
            self.display_thread.join(timeout=5)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all_captures()
        self.stop_display() 