"""
Channel Manager for ZTWorkload Manager
Manages SSH channels for interactive command execution and complex workflows.
"""

import time
import threading
import re
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from paramiko import SSHClient, Channel
from paramiko.ssh_exception import SSHException

from .logger import StructuredLogger

# Author: Vamsi


@dataclass
class ChannelCommand:
    """Represents a command to be executed on a channel."""
    command: str
    timeout: float = 30.0
    expect_patterns: List[str] = field(default_factory=list)
    expect_responses: Dict[str, str] = field(default_factory=dict)
    wait_for_prompt: bool = False
    prompt_pattern: str = r'[\$#]\s*$'
    clean_channel: bool = False


@dataclass
class ChannelResult:
    """Result of a channel command execution."""
    command: str
    output: str
    error: str
    exit_code: Optional[int] = None
    duration: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    channel_state: Dict[str, Any] = field(default_factory=dict)


class ChannelManager:
    """Manages SSH channels for interactive command execution."""
    
    def __init__(self, ssh_client: SSHClient, logger=None):
        """
        Initialize channel manager.
        
        :param ssh_client: SSH client instance
        :param logger: Logger instance
        """
        self.ssh_client = ssh_client
        self.logger = logger or StructuredLogger()
        self.channels: Dict[str, Channel] = {}
        self.channel_info: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        
        # Channel state tracking
        self.current_directory: Dict[str, str] = {}
        self.environment_vars: Dict[str, Dict[str, str]] = {}
    
    def create_channel(self, host: str, channel_type: str = "shell") -> Channel:
        """
        Create a new SSH channel.
        
        :param host: Host name for channel identification
        :param channel_type: Type of channel (shell, exec, etc.)
        :return: SSH channel
        """
        with self.lock:
            try:
                if channel_type == "shell":
                    channel = self.ssh_client.invoke_shell()
                else:
                    channel = self.ssh_client.get_transport().open_session()
                
                # Configure channel
                channel.settimeout(30)
                channel.set_combine_stderr(True)
                
                # Store channel
                self.channels[host] = channel
                self.channel_info[host] = {
                    'type': channel_type,
                    'created_at': datetime.now(),
                    'last_used': datetime.now(),
                    'command_count': 0,
                    'is_active': True
                }
                
                self.logger.info(f"Created {channel_type} channel for {host}")
                return channel
                
            except SSHException as e:
                self.logger.error(f"Failed to create channel for {host}: {e}")
                raise
    
    def get_channel(self, host: str) -> Optional[Channel]:
        """
        Get an existing channel for a host.
        
        :param host: Host name
        :return: SSH channel or None if not found
        """
        with self.lock:
            channel = self.channels.get(host)
            if channel and self._is_channel_active(channel):
                # Update last used time
                if host in self.channel_info:
                    self.channel_info[host]['last_used'] = datetime.now()
                    self.channel_info[host]['command_count'] += 1
                return channel
            return None
    
    def _is_channel_active(self, channel: Channel) -> bool:
        """
        Check if a channel is still active.
        
        :param channel: SSH channel to check
        :return: True if channel is active
        """
        try:
            return not channel.closed and channel.get_transport() and channel.get_transport().is_active()
        except:
            return False
    
    def close_channel(self, host: str):
        """
        Close a specific channel.
        
        :param host: Host name
        """
        with self.lock:
            if host in self.channels:
                try:
                    channel = self.channels[host]
                    if not channel.closed:
                        channel.close()
                    del self.channels[host]
                    
                    if host in self.channel_info:
                        self.channel_info[host]['is_active'] = False
                    
                    self.logger.info(f"Closed channel for {host}")
                except Exception as e:
                    self.logger.error(f"Error closing channel for {host}: {e}")
    
    def close_all_channels(self):
        """Close all channels."""
        with self.lock:
            for host in list(self.channels.keys()):
                self.close_channel(host)
    
    def execute_chain_commands(self, host: str, commands: List[ChannelCommand], 
                              create_new_channel: bool = False) -> List[ChannelResult]:
        """
        Execute a chain of commands on a channel.
        
        :param host: Host name
        :param commands: List of commands to execute
        :param create_new_channel: Whether to create a new channel
        :return: List of command results
        """
        results = []
        
        # Get or create channel
        if create_new_channel:
            self.close_channel(host)
            channel = self.create_channel(host)
        else:
            channel = self.get_channel(host)
            if not channel:
                channel = self.create_channel(host)
        
        try:
            for cmd in commands:
                result = self._execute_single_command(channel, cmd, host)
                results.append(result)
                
                # Check if command failed and we should stop
                if not result.success and cmd.clean_channel:
                    self.logger.warning(f"Command failed on {host}, cleaning channel")
                    self._clean_channel_buffer(channel)
                
                # Small delay between commands
                time.sleep(0.1)
                
        except Exception as e:
            self.logger.error(f"Error executing chain commands on {host}: {e}")
            # Create error result
            error_result = ChannelResult(
                command="chain_execution",
                output="",
                error=str(e),
                success=False
            )
            results.append(error_result)
        
        return results
    
    def _execute_single_command(self, channel: Channel, cmd: ChannelCommand, host: str) -> ChannelResult:
        """
        Execute a single command on a channel.
        
        :param channel: SSH channel
        :param cmd: Command to execute
        :param host: Host name
        :return: Command result
        """
        start_time = time.time()
        
        try:
            # Clean channel if requested
            if cmd.clean_channel:
                self._clean_channel_buffer(channel)
            
            # Send command
            command_with_newline = cmd.command + '\n'
            channel.send(command_with_newline)
            
            # Wait for output
            output, error = self.fetch_output(
                channel, 
                timeout=cmd.timeout,
                expect_patterns=cmd.expect_patterns,
                expect_responses=cmd.expect_responses,
                wait_for_prompt=cmd.wait_for_prompt,
                prompt_pattern=cmd.prompt_pattern
            )
            
            # Update current directory if it's a cd command
            if cmd.command.strip().startswith('cd '):
                self._update_current_directory(host, cmd.command)
            
            duration = time.time() - start_time
            
            # Try to extract exit code
            exit_code = self._extract_exit_code(output)
            
            return ChannelResult(
                command=cmd.command,
                output=output,
                error=error,
                exit_code=exit_code,
                duration=duration,
                success=exit_code == 0 if exit_code is not None else True
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return ChannelResult(
                command=cmd.command,
                output="",
                error=str(e),
                duration=duration,
                success=False
            )
    
    def fetch_output(self, channel: Channel, timeout: float = 30.0, encoding: str = 'utf-8', 
                    window_size: int = 4096, poll_iterations: int = 10, logger=None, 
                    expect_patterns: List[str] = None, expect_responses: Dict[str, str] = None, 
                    wait_for_prompt: bool = False, prompt_pattern: str = None) -> Tuple[str, str, Channel]:
        """
        Fetch output from a channel with pattern matching.
        
        :param channel: SSH channel
        :param timeout: Timeout in seconds
        :param encoding: Output encoding
        :param window_size: Window size for reading
        :param poll_iterations: Number of polling iterations
        :param logger: Logger instance
        :param expect_patterns: Patterns to expect in output
        :param expect_responses: Responses to send for patterns
        :param wait_for_prompt: Whether to wait for prompt
        :param prompt_pattern: Pattern for prompt
        :return: Tuple of (output, error, channel)
        """
        logger = logger or self.logger
        expect_patterns = expect_patterns or []
        expect_responses = expect_responses or {}
        
        output = ""
        error = ""
        start_time = time.time()
        
        try:
            while time.time() - start_time < timeout:
                if channel.recv_ready():
                    data = channel.recv(window_size).decode(encoding, errors='ignore')
                    output += data
                    
                    # Check for expect patterns
                    for pattern in expect_patterns:
                        if re.search(pattern, output, re.IGNORECASE):
                            response = expect_responses.get(pattern, "")
                            if response:
                                channel.send(response + '\n')
                                output += response + '\n'
                    
                    # Check for prompt if waiting
                    if wait_for_prompt and prompt_pattern:
                        if re.search(prompt_pattern, output):
                            break
                
                elif channel.recv_stderr_ready():
                    data = channel.recv_stderr(window_size).decode(encoding, errors='ignore')
                    error += data
                
                elif channel.exit_status_ready():
                    break
                
                else:
                    time.sleep(timeout / poll_iterations)
            
            return output, error, channel
            
        except Exception as e:
            logger.error(f"Error fetching output: {e}")
            return output, str(e), channel
    
    def _clean_channel_buffer(self, channel: Channel):
        """
        Clean the channel buffer.
        
        :param channel: SSH channel
        """
        try:
            while channel.recv_ready():
                channel.recv(1024)
        except:
            pass
    
    def _update_current_directory(self, host: str, cd_command: str):
        """
        Update the current directory tracking.
        
        :param host: Host name
        :param cd_command: CD command that was executed
        """
        try:
            # Extract directory from cd command
            parts = cd_command.strip().split()
            if len(parts) >= 2:
                directory = parts[1]
                
                # Handle relative paths
                if directory == '-':
                    # Go back to previous directory
                    if host in self.current_directory:
                        prev_dir = self.current_directory.get(host + '_prev', '/')
                        self.current_directory[host + '_prev'] = self.current_directory[host]
                        self.current_directory[host] = prev_dir
                elif directory.startswith('/'):
                    # Absolute path
                    self.current_directory[host + '_prev'] = self.current_directory.get(host, '/')
                    self.current_directory[host] = directory
                else:
                    # Relative path - would need to resolve
                    pass
        except Exception as e:
            self.logger.debug(f"Error updating current directory: {e}")
    
    def get_channel_info(self, host: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a channel.
        
        :param host: Host name
        :return: Channel information dictionary
        """
        with self.lock:
            if host in self.channel_info:
                info = self.channel_info[host].copy()
                if host in self.channels:
                    channel = self.channels[host]
                    info['is_active'] = self._is_channel_active(channel)
                    info['current_directory'] = self.current_directory.get(host, '/')
                return info
            return None
    
    def list_channels(self) -> Dict[str, Dict[str, Any]]:
        """
        List all channels and their information.
        
        :return: Dictionary of host to channel information
        """
        with self.lock:
            return {host: self.get_channel_info(host) for host in self.channel_info.keys()}
    
    def execute_interactive_commands(self, host: str, commands: List[Tuple[str, List[str]]], 
                                   timeout: float = 60.0) -> List[ChannelResult]:
        """
        Execute interactive commands with expect patterns.
        
        :param host: Host name
        :param commands: List of (command, expect_patterns) tuples
        :param timeout: Overall timeout
        :return: List of command results
        """
        channel_commands = []
        
        for command, expect_patterns in commands:
            channel_cmd = ChannelCommand(
                command=command,
                expect_patterns=expect_patterns,
                timeout=timeout / len(commands) if commands else timeout
            )
            channel_commands.append(channel_cmd)
        
        return self.execute_chain_commands(host, channel_commands, create_new_channel=True)
    
    def _extract_exit_code(self, output: str) -> Optional[int]:
        """
        Extract exit code from command output.
        
        :param output: Command output
        :return: Exit code or None if not found
        """
        try:
            # Look for echo $? pattern
            lines = output.split('\n')
            for line in reversed(lines):
                if line.strip().isdigit():
                    return int(line.strip())
        except:
            pass
        return None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all_channels()


def execute_command(ssh_obj, command: str, timeout: float = 30.0, logger=None):
    """
    Execute a command using SSH object.
    
    :param ssh_obj: SSH object (client or channel)
    :param command: Command to execute
    :param timeout: Command timeout
    :param logger: Logger instance
    :return: Command result
    """
    logger = logger or StructuredLogger()
    
    try:
        if hasattr(ssh_obj, 'exec_command'):
            # SSHClient
            stdin, stdout, stderr = ssh_obj.exec_command(command, timeout=timeout)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            exit_code = stdout.channel.recv_exit_status()
        else:
            # Channel
            ssh_obj.send(command + '\n')
            output = ""
            error = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if ssh_obj.recv_ready():
                    data = ssh_obj.recv(4096).decode('utf-8')
                    output += data
                elif ssh_obj.recv_stderr_ready():
                    data = ssh_obj.recv_stderr(4096).decode('utf-8')
                    error += data
                elif ssh_obj.exit_status_ready():
                    break
                else:
                    time.sleep(0.1)
            
            exit_code = ssh_obj.recv_exit_status() if ssh_obj.exit_status_ready() else None
        
        return {
            'output': output,
            'error': error,
            'exit_code': exit_code,
            'success': exit_code == 0 if exit_code is not None else True
        }
        
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return {
            'output': '',
            'error': str(e),
            'exit_code': None,
            'success': False
        } 