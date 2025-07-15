"""
Enhanced logging module for SSH Tool with structured logging and real-time capabilities.
"""

import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime
from typing import Dict, Any, Optional, Union
from pathlib import Path
import structlog
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.layout import Layout


class StructuredLogger:
    """Enhanced structured logger with real-time capabilities."""
    
    def __init__(self, 
                 level: str = "info",
                 log_file: str = "logs/vwt_monitor.log",
                 log_format: str = "json",
                 enable_console: bool = True,
                 enable_file: bool = True):
        """
        Initialize the structured logger.
        
        Args:
            level: Logging level (debug, info, warn, error, fatal)
            log_file: Path to log file
            log_format: Log format (json, text, structured)
            enable_console: Enable console output
            enable_file: Enable file output
        """
        self.level = self._parse_level(level)
        self.log_file = log_file
        self.log_format = log_format
        self.enable_console = enable_console
        self.enable_file = enable_file
        
        # Initialize rich console
        self.console = Console()
        
        # Setup logging
        self._setup_logging()
        
        # Real-time log buffer
        self.log_buffer = []
        self.max_buffer_size = 1000
    
    def _parse_level(self, level: str) -> int:
        """Parse log level string to logging constant."""
        level_map = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warn': logging.WARNING,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'fatal': logging.CRITICAL,
            'critical': logging.CRITICAL
        }
        return level_map.get(level.lower(), logging.INFO)
    
    def _setup_logging(self):
        """Setup logging configuration."""
        # Create log directory
        if self.enable_file:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # Configure structlog
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]
        
        if self.log_format == "json":
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer())
        
        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        # Create logger
        self.logger = structlog.get_logger()
        
        # Setup handlers
        handlers = []
        
        if self.enable_console:
            console_handler = RichHandler(
                console=self.console,
                show_time=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True
            )
            console_handler.setLevel(self.level)
            handlers.append(console_handler)
        
        if self.enable_file:
            # Rotating file handler
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=100 * 1024 * 1024,  # 100MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(self.level)
            
            if self.log_format == "json":
                formatter = logging.Formatter('%(message)s')
            else:
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
            
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        
        # Configure root logger
        logging.basicConfig(
            level=self.level,
            handlers=handlers,
            format='%(message)s' if self.log_format == "json" else None
        )
    
    def _add_to_buffer(self, level: str, message: str, **kwargs):
        """Add log entry to buffer for real-time processing."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
            **kwargs
        }
        
        self.log_buffer.append(log_entry)
        
        # Maintain buffer size
        if len(self.log_buffer) > self.max_buffer_size:
            self.log_buffer.pop(0)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._add_to_buffer('debug', message, **kwargs)
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self._add_to_buffer('info', message, **kwargs)
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._add_to_buffer('warning', message, **kwargs)
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self._add_to_buffer('error', message, **kwargs)
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self._add_to_buffer('critical', message, **kwargs)
        self.logger.critical(message, **kwargs)
    
    def log_command_result(self, host: str, command: str, exit_code: int, 
                          output: str, error: str, duration: float):
        """Log command execution result."""
        self.info(
            "Command executed",
            host=host,
            command=command,
            exit_code=exit_code,
            output_length=len(output),
            error_length=len(error),
            duration=duration
        )
    
    def log_connection_event(self, host: str, event: str, **kwargs):
        """Log connection-related events."""
        self.info(f"Connection {event}", host=host, **kwargs)
    
    def log_file_transfer(self, host: str, operation: str, local_path: str, 
                         remote_path: str, size: int, duration: float):
        """Log file transfer events."""
        self.info(
            f"File {operation}",
            host=host,
            operation=operation,
            local_path=local_path,
            remote_path=remote_path,
            size=size,
            duration=duration
        )
    
    def get_recent_logs(self, count: int = 50) -> list:
        """Get recent log entries."""
        return self.log_buffer[-count:] if self.log_buffer else []
    
    def start_live_dashboard(self):
        """Start a live updating dashboard."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        layout["main"].split_row(
            Layout(name="logs", ratio=2),
            Layout(name="metrics", ratio=1)
        )
        
        with Live(layout, refresh_per_second=2, screen=True):
            while True:
                try:
                    # Header
                    header = Panel(
                        f"[bold blue]SSH Tool - Real-time Logging Dashboard[/bold blue]\n"
                        f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        title="Dashboard"
                    )
                    layout["header"].update(header)
                    
                    # Recent logs
                    recent_logs = self.get_recent_logs(20)
                    log_table = Table(title="Recent Logs")
                    log_table.add_column("Time", style="cyan")
                    log_table.add_column("Level", style="magenta")
                    log_table.add_column("Message", style="white")
                    
                    for log_entry in recent_logs:
                        level_color = {
                            'debug': 'blue',
                            'info': 'green',
                            'warning': 'yellow',
                            'error': 'red',
                            'critical': 'red'
                        }.get(log_entry['level'], 'white')
                        
                        log_table.add_row(
                            log_entry['timestamp'][11:19],  # Time only
                            f"[{level_color}]{log_entry['level'].upper()}[/{level_color}]",
                            log_entry['message'][:50] + "..." if len(log_entry['message']) > 50 else log_entry['message']
                        )
                    
                    layout["logs"].update(Panel(log_table))
                    
                    # Metrics
                    metrics_table = Table(title="Metrics")
                    metrics_table.add_column("Metric", style="cyan")
                    metrics_table.add_column("Value", style="green")
                    
                    metrics_table.add_row("Total Logs", str(len(self.log_buffer)))
                    metrics_table.add_row("Buffer Size", str(len(self.log_buffer)))
                    
                    layout["metrics"].update(Panel(metrics_table))
                    
                    # Footer
                    footer = Panel(
                        f"[bold]Status:[/bold] Active | "
                        f"[bold]Log File:[/bold] {self.log_file} | "
                        f"[bold]Format:[/bold] {self.log_format}",
                        title="Status"
                    )
                    layout["footer"].update(footer)
                    
                    import time
                    time.sleep(0.5)
                except KeyboardInterrupt:
                    break
        
        self.info("Live dashboard stopped")
    
    def export_logs(self, filename: str, format: str = "json"):
        """Export logs to file."""
        if format == "json":
            with open(filename, 'w') as f:
                json.dump(self.log_buffer, f, indent=2)
        elif format == "csv":
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp', 'level', 'message'])
                writer.writeheader()
                writer.writerows(self.log_buffer)
        
        self.info(f"Logs exported to {filename}")
    
    def clear_buffer(self):
        """Clear the log buffer."""
        self.log_buffer.clear()
        self.info("Log buffer cleared")
    
    def set_level(self, level: str):
        """Set logging level."""
        self.level = self._parse_level(level)
        logging.getLogger().setLevel(self.level)
        self.info(f"Log level changed to {level.upper()}")


class HostLogger:
    """Host-specific logger for tracking operations per host."""
    
    def __init__(self, host: str, parent_logger: StructuredLogger):
        """
        Initialize host-specific logger.
        
        Args:
            host: Host name/IP
            parent_logger: Parent structured logger
        """
        self.host = host
        self.parent_logger = parent_logger
        self.host_metrics = {
            'commands_executed': 0,
            'files_transferred': 0,
            'connection_attempts': 0,
            'connection_failures': 0,
            'total_duration': 0.0
        }
    
    def log_command(self, command: str, exit_code: int, output: str, 
                   error: str, duration: float):
        """Log command execution for this host."""
        self.parent_logger.log_command_result(
            self.host, command, exit_code, output, error, duration
        )
        self.host_metrics['commands_executed'] += 1
        self.host_metrics['total_duration'] += duration
    
    def log_connection(self, event: str, **kwargs):
        """Log connection event for this host."""
        self.parent_logger.log_connection_event(self.host, event, **kwargs)
        if event == 'attempt':
            self.host_metrics['connection_attempts'] += 1
        elif event == 'failure':
            self.host_metrics['connection_failures'] += 1
    
    def log_file_transfer(self, operation: str, local_path: str, 
                         remote_path: str, size: int, duration: float):
        """Log file transfer for this host."""
        self.parent_logger.log_file_transfer(
            self.host, operation, local_path, remote_path, size, duration
        )
        self.host_metrics['files_transferred'] += 1
        self.host_metrics['total_duration'] += duration
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get host-specific metrics."""
        return {
            'host': self.host,
            **self.host_metrics,
            'success_rate': (
                (self.host_metrics['commands_executed'] - self.host_metrics['connection_failures']) /
                max(self.host_metrics['commands_executed'], 1) * 100
            )
        } 