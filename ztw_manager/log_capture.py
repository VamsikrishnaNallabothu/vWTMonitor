"""
Log Capture Module for ZTWorkload Manager
Provides real-time log capture and monitoring capabilities.
"""

import os
import time
import threading
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from paramiko import SSHClient

from .logger import StructuredLogger

# Author: Vamsi


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
    """Real-time log capture and monitoring."""
    
    def __init__(self, config: LogCaptureConfig, logger=None):
        """
        Initialize log capture.
        
        :param config: Log capture configuration
        :param logger: Logger instance
        """
        self.config = config
        self.logger = logger or StructuredLogger()
        
        # Capture state
        self.active_captures: Dict[str, Dict[str, Any]] = {}
        self.captured_logs: List[LogEntry] = []
        self.log_buffer: List[LogEntry] = []
        
        # Threading
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        
        # Display thread
        self.display_thread = None
        self.display_stop_event = threading.Event()
        
        # Statistics
        self.stats = {
            'total_entries': 0,
            'filtered_entries': 0,
            'error_count': 0,
            'start_time': None,
            'last_entry_time': None
        }
    
    def start_capture(self, host: str, ssh_client: SSHClient, log_file_path: str):
        """
        Start log capture on a host.
        
        :param host: Host name
        :param ssh_client: SSH client for the host
        :param log_file_path: Path to log file on the host
        """
        with self.lock:
            if host in self.active_captures:
                self.logger.warning(f"Log capture already active for {host}")
                return
            
            # Create capture info
            capture_info = {
                'host': host,
                'ssh_client': ssh_client,
                'log_file_path': log_file_path,
                'start_time': datetime.now(),
                'stop_event': threading.Event(),
                'thread': None
            }
            
            # Start capture thread
            capture_thread = threading.Thread(
                target=self._capture_logs,
                args=(host, ssh_client, log_file_path, capture_info['stop_event']),
                daemon=True
            )
            capture_thread.start()
            
            capture_info['thread'] = capture_thread
            self.active_captures[host] = capture_info
            
            self.logger.info(f"Started log capture on {host}: {log_file_path}")
    
    def stop_capture(self, host: str):
        """
        Stop log capture on a host.
        
        :param host: Host name
        """
        with self.lock:
            if host in self.active_captures:
                capture_info = self.active_captures[host]
                capture_info['stop_event'].set()
                
                if capture_info['thread']:
                    capture_info['thread'].join(timeout=5)
                
                del self.active_captures[host]
                self.logger.info(f"Stopped log capture on {host}")
    
    def stop_all_captures(self):
        """Stop all active log captures."""
        with self.lock:
            for host in list(self.active_captures.keys()):
                self.stop_capture(host)
    
    def _capture_logs(self, host: str, ssh_client: SSHClient, log_file_path: str, stop_event: threading.Event):
        """
        Capture logs from a host.
        
        :param host: Host name
        :param ssh_client: SSH client
        :param log_file_path: Log file path
        :param stop_event: Stop event for thread control
        """
        try:
            # Check if file exists
            stdin, stdout, stderr = ssh_client.exec_command(f"test -f {log_file_path} && echo 'exists'")
            if stdout.read().strip() != 'exists':
                self.logger.error(f"Log file not found on {host}: {log_file_path}")
                return
            
            # Start tail command
            tail_command = f"tail -f {log_file_path}"
            stdin, stdout, stderr = ssh_client.exec_command(tail_command)
            
            # Read output
            while not stop_event.is_set():
                line = stdout.readline()
                if not line:
                    break
                
                # Parse log entry
                log_entry = self._parse_log_line(host, line.strip(), log_file_path)
                if log_entry:
                    self._process_log_entry(log_entry)
                
                # Small delay to prevent high CPU usage
                time.sleep(0.01)
            
            # Clean up
            try:
                stdin.close()
                stdout.close()
                stderr.close()
            except:
                pass
                
        except Exception as e:
            self.logger.error(f"Error capturing logs from {host}: {e}")
            self.stats['error_count'] += 1
    
    def _should_process_line(self, line: str) -> bool:
        """
        Check if a log line should be processed based on filters.
        
        :param line: Log line
        :return: True if line should be processed
        """
        # Check exclude patterns first
        for pattern in self.config.exclude_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return False
        
        # Check include patterns
        if self.config.filter_patterns:
            for pattern in self.config.filter_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    return True
            return False
        
        return True
    
    def _parse_log_line(self, host: str, line: str, source_file: str) -> Optional[LogEntry]:
        """
        Parse a log line into a LogEntry object.
        
        :param host: Host name
        :param line: Log line
        :param source_file: Source file path
        :return: LogEntry object or None if parsing fails
        """
        if not line or not self._should_process_line(line):
            return None
        
        try:
            # Common log patterns
            patterns = [
                # syslog format: Jan 1 00:00:00 hostname program[pid]: message
                r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(\S+)\[(\d+)\]:\s*(.*)$',
                # ISO format: 2024-01-01T00:00:00.000Z level: message
                r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+(\w+):\s*(.*)$',
                # Simple timestamp: 2024-01-01 00:00:00 message
                r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.*)$',
            ]
            
            timestamp = datetime.now()
            level = "info"
            message = line
            process_id = None
            
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    groups = match.groups()
                    
                    if len(groups) >= 2:
                        # Try to parse timestamp
                        try:
                            if 'T' in groups[0]:
                                # ISO format
                                timestamp = datetime.fromisoformat(groups[0].replace('Z', '+00:00'))
                            elif '-' in groups[0]:
                                # Date format
                                timestamp = datetime.strptime(groups[0], '%Y-%m-%d %H:%M:%S')
                            else:
                                # syslog format
                                current_year = datetime.now().year
                                timestamp = datetime.strptime(f"{current_year} {groups[0]}", '%Y %b %d %H:%M:%S')
                        except:
                            timestamp = datetime.now()
                        
                        # Extract level and message
                        if len(groups) >= 3:
                            if groups[1].isdigit():
                                process_id = int(groups[1])
                                message = groups[2]
                            else:
                                level = groups[1].lower()
                                message = groups[2]
                        else:
                            message = groups[1]
                    
                    break
            
            return LogEntry(
                host=host,
                timestamp=timestamp,
                level=level,
                message=message,
                source_file=source_file,
                process_id=process_id
            )
            
        except Exception as e:
            self.logger.debug(f"Failed to parse log line: {e}")
            return None
    
    def _process_log_entry(self, log_entry: LogEntry, file_handle=None):
        """
        Process a log entry.
        
        :param log_entry: Log entry to process
        :param file_handle: Optional file handle for writing
        """
        with self.lock:
            # Add to buffer
            self.log_buffer.append(log_entry)
            self.captured_logs.append(log_entry)
            
            # Maintain buffer size
            if len(self.log_buffer) > self.config.buffer_size:
                self.log_buffer.pop(0)
            
            # Update statistics
            self.stats['total_entries'] += 1
            self.stats['last_entry_time'] = log_entry.timestamp
            
            # Write to file if provided
            if file_handle:
                try:
                    file_handle.write(f"{log_entry.timestamp.isoformat()} {log_entry.host} {log_entry.level}: {log_entry.message}\n")
                    file_handle.flush()
                except:
                    pass
    
    def _start_display_thread(self):
        """Start the display thread for real-time output."""
        if self.config.real_time_display and not self.display_thread:
            self.display_stop_event.clear()
            self.display_thread = threading.Thread(target=self._display_worker, daemon=True)
            self.display_thread.start()
    
    def _display_worker(self):
        """Display worker thread."""
        while not self.display_stop_event.is_set():
            try:
                # Get recent logs
                with self.lock:
                    recent_logs = self.log_buffer[-20:] if self.log_buffer else []
                
                # Display logs
                for entry in recent_logs:
                    level_color = {
                        'debug': 'blue',
                        'info': 'green', 
                        'warning': 'yellow',
                        'error': 'red',
                        'critical': 'red'
                    }.get(entry.level, 'white')
                    
                    print(f"[{entry.timestamp.strftime('%H:%M:%S')}] {entry.host} {entry.level.upper()}: {entry.message}")
                
                time.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Display error: {e}")
                break
    
    def get_recent_logs(self, count: int = 100) -> List[LogEntry]:
        """
        Get recent log entries.
        
        :param count: Number of entries to return
        :return: List of recent log entries
        """
        with self.lock:
            return self.captured_logs[-count:] if self.captured_logs else []
    
    def get_logs_by_host(self, host: str, count: int = 100) -> List[LogEntry]:
        """
        Get log entries for a specific host.
        
        :param host: Host name
        :param count: Number of entries to return
        :return: List of log entries for the host
        """
        with self.lock:
            host_logs = [entry for entry in self.captured_logs if entry.host == host]
            return host_logs[-count:] if host_logs else []
    
    def get_logs_by_level(self, level: str, count: int = 100) -> List[LogEntry]:
        """
        Get log entries by level.
        
        :param level: Log level
        :param count: Number of entries to return
        :return: List of log entries with the specified level
        """
        with self.lock:
            level_logs = [entry for entry in self.captured_logs if entry.level.lower() == level.lower()]
            return level_logs[-count:] if level_logs else []
    
    def export_logs(self, filename: str, format: str = "json", 
                   hosts: List[str] = None, levels: List[str] = None):
        """
        Export logs to file.
        
        :param filename: Output filename
        :param format: Export format (json, csv, text)
        :param hosts: Filter by hosts
        :param levels: Filter by log levels
        """
        try:
            with self.lock:
                logs_to_export = self.captured_logs.copy()
            
            # Apply filters
            if hosts:
                logs_to_export = [log for log in logs_to_export if log.host in hosts]
            
            if levels:
                logs_to_export = [log for log in logs_to_export if log.level.lower() in [l.lower() for l in levels]]
            
            # Export based on format
            if format == "json":
                import json
                data = []
                for entry in logs_to_export:
                    data.append({
                        'host': entry.host,
                        'timestamp': entry.timestamp.isoformat(),
                        'level': entry.level,
                        'message': entry.message,
                        'source_file': entry.source_file,
                        'line_number': entry.line_number,
                        'process_id': entry.process_id,
                        'thread_id': entry.thread_id,
                        'metadata': entry.metadata
                    })
                
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2)
            
            elif format == "csv":
                import csv
                with open(filename, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['timestamp', 'host', 'level', 'message', 'source_file'])
                    for entry in logs_to_export:
                        writer.writerow([
                            entry.timestamp.isoformat(),
                            entry.host,
                            entry.level,
                            entry.message,
                            entry.source_file
                        ])
            
            elif format == "text":
                with open(filename, 'w') as f:
                    for entry in logs_to_export:
                        f.write(f"{entry.timestamp.isoformat()} {entry.host} {entry.level}: {entry.message}\n")
            
            self.logger.info(f"Exported {len(logs_to_export)} log entries to {filename}")
            
        except Exception as e:
            self.logger.error(f"Failed to export logs: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get log capture statistics.
        
        :return: Dictionary of statistics
        """
        with self.lock:
            stats = self.stats.copy()
            stats.update({
                'active_captures': len(self.active_captures),
                'buffer_size': len(self.log_buffer),
                'total_captured': len(self.captured_logs),
                'hosts': list(self.active_captures.keys())
            })
            return stats
    
    def clear_buffer(self):
        """Clear the log buffer."""
        with self.lock:
            self.log_buffer.clear()
    
    def stop_display(self):
        """Stop the display thread."""
        if self.display_thread:
            self.display_stop_event.set()
            self.display_thread.join(timeout=5)
            self.display_thread = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_all_captures()
        self.stop_display() 