"""
Logging module for ZTWorkload Manager
Provides structured logging with console and file output, metrics collection,
and real-time dashboard capabilities.
"""

import os
import json
import logging
import threading
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

# Author: Vamsi


class StructuredLogger:
    """Structured logger with console and file output."""
    
    def __init__(self, 
                 level: str = "info",
                 log_file: str = "logs/ztw_manager.log",
                 log_format: str = "json",
                 enable_console: bool = True,
                 enable_file: bool = True):
        """
        Initialize structured logger.
        
        :param level: Log level (debug, info, warning, error, critical)
        :param log_file: Log file path
        :param log_format: Log format (json, text)
        :param enable_console: Enable console output
        :param enable_file: Enable file output
        """
        self.level = level
        self.log_file = log_file
        self.log_format = log_format
        self.enable_console = enable_console
        self.enable_file = enable_file
        
        # Log buffer for metrics
        self.log_buffer: List[Dict[str, Any]] = []
        self.buffer_lock = threading.Lock()
        self.max_buffer_size = 1000
        
        # Setup logging
        self._setup_logging()
    
    def _parse_level(self, level: str) -> int:
        """
        Parse log level string to logging level.
        
        :param level: Log level string
        :return: Logging level constant
        """
        level_map = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL
        }
        return level_map.get(level.lower(), logging.INFO)
    
    def _setup_logging(self):
        """Setup logging configuration."""
        # Create logger
        self.logger = logging.getLogger('ztw_manager')
        self.logger.setLevel(self._parse_level(self.level))
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        if self.log_format == "json":
            formatter = logging.Formatter('%(message)s')
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        # Console handler
        if self.enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(self._parse_level(self.level))
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        
        # File handler
        if self.enable_file:
            # Ensure log directory exists
            log_dir = os.path.dirname(self.log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(self._parse_level(self.level))
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def _add_to_buffer(self, level: str, message: str, **kwargs):
        """
        Add log entry to buffer.
        
        :param level: Log level
        :param message: Log message
        :param **kwargs: Additional log data
        """
        with self.buffer_lock:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'level': level,
                'message': message,
                **kwargs
            }
            
            self.log_buffer.append(entry)
            
            # Trim buffer if too large
            if len(self.log_buffer) > self.max_buffer_size:
                self.log_buffer = self.log_buffer[-self.max_buffer_size:]
    
    def debug(self, message: str, **kwargs):
        """
        Log debug message.
        
        :param message: Debug message
        :param **kwargs: Additional log data
        """
        self._add_to_buffer('debug', message, **kwargs)
        if self.log_format == "json":
            self.logger.debug(json.dumps({'level': 'debug', 'message': message, **kwargs}))
        else:
            self.logger.debug(message)
    
    def info(self, message: str, **kwargs):
        """
        Log info message.
        
        :param message: Info message
        :param **kwargs: Additional log data
        """
        self._add_to_buffer('info', message, **kwargs)
        if self.log_format == "json":
            self.logger.info(json.dumps({'level': 'info', 'message': message, **kwargs}))
        else:
            self.logger.info(message)
    
    def warning(self, message: str, **kwargs):
        """
        Log warning message.
        
        :param message: Warning message
        :param **kwargs: Additional log data
        """
        self._add_to_buffer('warning', message, **kwargs)
        if self.log_format == "json":
            self.logger.warning(json.dumps({'level': 'warning', 'message': message, **kwargs}))
        else:
            self.logger.warning(message)
    
    def error(self, message: str, **kwargs):
        """
        Log error message.
        
        :param message: Error message
        :param **kwargs: Additional log data
        """
        self._add_to_buffer('error', message, **kwargs)
        if self.log_format == "json":
            self.logger.error(json.dumps({'level': 'error', 'message': message, **kwargs}))
        else:
            self.logger.error(message)
    
    def critical(self, message: str, **kwargs):
        """
        Log critical message.
        
        :param message: Critical message
        :param **kwargs: Additional log data
        """
        self._add_to_buffer('critical', message, **kwargs)
        if self.log_format == "json":
            self.logger.critical(json.dumps({'level': 'critical', 'message': message, **kwargs}))
        else:
            self.logger.critical(message)
    
    def log_command_result(self, host: str, command: str, exit_code: int, 
                          output: str, error: str, duration: float):
        """
        Log command execution result.
        
        :param host: Host name
        :param command: Executed command
        :param exit_code: Command exit code
        :param output: Command output
        :param error: Command error
        :param duration: Command duration
        """
        self.info("Command executed", 
                 host=host, command=command, exit_code=exit_code,
                 output=output, error=error, duration=duration)
    
    def log_connection_event(self, host: str, event: str, **kwargs):
        """
        Log connection event.
        
        :param host: Host name
        :param event: Event type
        :param **kwargs: Additional event data
        """
        self.info("Connection event", host=host, event=event, **kwargs)
    
    def log_file_transfer(self, host: str, operation: str, local_path: str, 
                         remote_path: str, size: int, duration: float):
        """
        Log file transfer operation.
        
        :param host: Host name
        :param operation: Transfer operation (upload/download)
        :param local_path: Local file path
        :param remote_path: Remote file path
        :param size: File size in bytes
        :param duration: Transfer duration
        """
        self.info("File transfer completed",
                 host=host, operation=operation, local_path=local_path,
                 remote_path=remote_path, size=size, duration=duration)
    
    def get_recent_logs(self, count: int = 50) -> list:
        """
        Get recent log entries.
        
        :param count: Number of log entries to return
        :return: List of recent log entries
        """
        with self.buffer_lock:
            return self.log_buffer[-count:] if self.log_buffer else []
    
    def start_live_dashboard(self):
        """Start live dashboard (placeholder for future implementation)."""
        self.info("Live dashboard started")
        # Future implementation for real-time dashboard
    
    def export_logs(self, filename: str, format: str = "json"):
        """
        Export logs to file.
        
        :param filename: Output filename
        :param format: Export format (json, csv)
        """
        try:
            with self.buffer_lock:
                logs = self.log_buffer.copy()
            
            if format == "json":
                with open(filename, 'w') as f:
                    json.dump(logs, f, indent=2)
            elif format == "csv":
                import csv
                with open(filename, 'w', newline='') as f:
                    if logs:
                        writer = csv.DictWriter(f, fieldnames=logs[0].keys())
                        writer.writeheader()
                        writer.writerows(logs)
            
            self.info(f"Logs exported to {filename}")
            
        except Exception as e:
            self.error(f"Failed to export logs: {e}")
    
    def clear_buffer(self):
        """Clear log buffer."""
        with self.buffer_lock:
            self.log_buffer.clear()
    
    def set_level(self, level: str):
        """
        Set log level.
        
        :param level: New log level
        """
        self.level = level
        self._setup_logging()


class HostLogger:
    """Host-specific logger with metrics collection."""
    
    def __init__(self, host: str, parent_logger: StructuredLogger):
        """
        Initialize host logger.
        
        :param host: Host name
        :param parent_logger: Parent logger instance
        """
        self.host = host
        self.parent_logger = parent_logger
        
        # Host-specific metrics
        self.command_count = 0
        self.successful_commands = 0
        self.failed_commands = 0
        self.total_duration = 0.0
        self.last_command_time = None
        
        # Thread safety
        self.lock = threading.RLock()
    
    def log_command(self, command: str, exit_code: int, output: str, 
                   error: str, duration: float):
        """
        Log command execution.
        
        :param command: Executed command
        :param exit_code: Command exit code
        :param output: Command output
        :param error: Command error
        :param duration: Command duration
        """
        with self.lock:
            self.command_count += 1
            if exit_code == 0:
                self.successful_commands += 1
            else:
                self.failed_commands += 1
            
            self.total_duration += duration
            self.last_command_time = datetime.now()
        
        self.parent_logger.log_command_result(
            self.host, command, exit_code, output, error, duration
        )
    
    def log_connection(self, event: str, **kwargs):
        """
        Log connection event.
        
        :param event: Event type
        :param **kwargs: Additional event data
        """
        self.parent_logger.log_connection_event(self.host, event, **kwargs)
    
    def log_file_transfer(self, operation: str, local_path: str, 
                         remote_path: str, size: int, duration: float):
        """
        Log file transfer.
        
        :param operation: Transfer operation
        :param local_path: Local file path
        :param remote_path: Remote file path
        :param size: File size
        :param duration: Transfer duration
        """
        self.parent_logger.log_file_transfer(
            self.host, operation, local_path, remote_path, size, duration
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get host metrics.
        
        :return: Dictionary of host metrics
        """
        with self.lock:
            success_rate = (self.successful_commands / self.command_count * 100) if self.command_count > 0 else 0
            avg_duration = (self.total_duration / self.command_count) if self.command_count > 0 else 0
            
            return {
                'host': self.host,
                'command_count': self.command_count,
                'successful_commands': self.successful_commands,
                'failed_commands': self.failed_commands,
                'success_rate': success_rate,
                'total_duration': self.total_duration,
                'avg_duration': avg_duration,
                'last_command_time': self.last_command_time.isoformat() if self.last_command_time else None
            } 