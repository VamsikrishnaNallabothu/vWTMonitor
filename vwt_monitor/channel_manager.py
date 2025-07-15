"""
Channel manager for SSH chain command execution.
"""

import time
import threading
import select
import socket
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import paramiko
from paramiko import SSHClient, Channel
from paramiko.ssh_exception import SSHException
import logging


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
    """Manages SSH channels for chain command execution."""
    
    def __init__(self, ssh_client: SSHClient, logger=None):
        """
        Initialize channel manager.
        
        Args:
            ssh_client: SSH client instance
            logger: Logger instance
        """
        self.ssh_client = ssh_client
        self.logger = logger or logging.getLogger(__name__)
        
        # Channel storage
        self.channels: Dict[str, Channel] = {}
        self.channel_info: Dict[str, Dict[str, Any]] = {}
        
        # Threading
        self.lock = threading.RLock()
        
        # Default settings
        self.default_timeout = 30.0
        self.default_window_size = 4096
        self.default_encoding = 'utf-8'
        self.default_poll_iterations = 10
    
    def create_channel(self, host: str, channel_type: str = "shell") -> Channel:
        """
        Create a new channel for a host.
        
        Args:
            host: Target host
            channel_type: Type of channel (shell, exec, etc.)
            
        Returns:
            SSH channel
        """
        with self.lock:
            if host in self.channels and not self.channels[host].closed:
                self.logger.debug(f"Reusing existing channel for {host}")
                return self.channels[host]
            
            try:
                if channel_type == "shell":
                    channel = self.ssh_client.invoke_shell()
                elif channel_type == "exec":
                    # For exec channels, we'll create them per command
                    raise ValueError("Exec channels should be created per command")
                else:
                    raise ValueError(f"Unsupported channel type: {channel_type}")
                
                # Configure channel
                channel.settimeout(self.default_timeout)
                channel.set_combine_stderr(True)
                
                # Store channel
                self.channels[host] = channel
                self.channel_info[host] = {
                    'type': channel_type,
                    'created_at': datetime.now(),
                    'last_used': datetime.now(),
                    'command_count': 0,
                    'current_directory': None
                }
                
                self.logger.debug(f"Created new {channel_type} channel for {host}")
                return channel
                
            except Exception as e:
                self.logger.error(f"Failed to create channel for {host}: {e}")
                raise
    
    def get_channel(self, host: str) -> Optional[Channel]:
        """
        Get existing channel for a host.
        
        Args:
            host: Target host
            
        Returns:
            SSH channel or None if not found/closed
        """
        with self.lock:
            if host in self.channels:
                channel = self.channels[host]
                if not channel.closed:
                    self.channel_info[host]['last_used'] = datetime.now()
                    self.channel_info[host]['command_count'] += 1
                    return channel
                else:
                    # Remove closed channel
                    del self.channels[host]
                    if host in self.channel_info:
                        del self.channel_info[host]
        
        return None
    
    def close_channel(self, host: str):
        """
        Close channel for a host.
        
        Args:
            host: Target host
        """
        with self.lock:
            if host in self.channels:
                try:
                    self.channels[host].close()
                except:
                    pass
                del self.channels[host]
                
                if host in self.channel_info:
                    del self.channel_info[host]
                
                self.logger.debug(f"Closed channel for {host}")
    
    def close_all_channels(self):
        """Close all channels."""
        with self.lock:
            for host in list(self.channels.keys()):
                self.close_channel(host)
    
    def execute_chain_commands(self, host: str, commands: List[ChannelCommand], 
                              create_new_channel: bool = False) -> List[ChannelResult]:
        """
        Execute a chain of commands on a channel.
        
        Args:
            host: Target host
            commands: List of commands to execute
            create_new_channel: Whether to create a new channel
            
        Returns:
            List of command results
        """
        results = []
        
        # Get or create channel
        if create_new_channel:
            channel = self.create_channel(host)
        else:
            channel = self.get_channel(host)
            if channel is None:
                channel = self.create_channel(host)
        
        try:
            for cmd in commands:
                result = self._execute_single_command(channel, cmd, host)
                results.append(result)
                
                # Check if command failed
                if not result.success:
                    self.logger.warning(f"Command failed on {host}: {cmd.command}")
                    break
                
                # Update current directory if it's a cd command
                if cmd.command.strip().startswith('cd '):
                    self._update_current_directory(host, cmd.command)
        
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
        
        Args:
            channel: SSH channel
            cmd: Command to execute
            host: Target host
            
        Returns:
            Command result
        """
        start_time = time.time()
        
        try:
            # Clean channel if requested
            if cmd.clean_channel:
                self._clean_channel_buffer(channel)
            
            # Prepare command
            command = cmd.command
            if not command.endswith('\n'):
                command += '\n'
            
            # Send command
            if not channel.send_ready():
                raise SSHException("Channel not ready for sending")
            
            self.logger.debug(f"Sending command on {host}: {cmd.command}")
            channel.send(command)
            
            # Receive output
            output, error = self._receive_output(
                channel, 
                timeout=cmd.timeout,
                expect_patterns=cmd.expect_patterns,
                expect_responses=cmd.expect_responses,
                wait_for_prompt=cmd.wait_for_prompt,
                prompt_pattern=cmd.prompt_pattern
            )
            
            # Get exit code if available
            exit_code = None
            if channel.exit_status_ready():
                exit_code = channel.recv_exit_status()
            
            duration = time.time() - start_time
            
            result = ChannelResult(
                command=cmd.command,
                output=output,
                error=error,
                exit_code=exit_code,
                duration=duration,
                success=exit_code == 0 if exit_code is not None else True
            )
            
            self.logger.debug(f"Command completed on {host}: {cmd.command} (Duration: {duration:.2f}s)")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Error executing command on {host}: {cmd.command} - {e}")
            
            return ChannelResult(
                command=cmd.command,
                output="",
                error=str(e),
                duration=duration,
                success=False
            )
    
    def _receive_output(self, channel: Channel, timeout: float = None, 
                       expect_patterns: List[str] = None, expect_responses: Dict[str, str] = None,
                       wait_for_prompt: bool = False, prompt_pattern: str = None) -> Tuple[str, str]:
        """
        Receive output from channel with optional expect patterns.
        
        Args:
            channel: SSH channel
            timeout: Timeout for receiving
            expect_patterns: Patterns to expect
            expect_responses: Responses to send for patterns
            wait_for_prompt: Whether to wait for prompt
            prompt_pattern: Prompt pattern to wait for
            
        Returns:
            Tuple of (output, error)
        """
        if timeout is None:
            timeout = self.default_timeout
        
        output = ""
        error = ""
        iterations = 0
        max_iterations = self.default_poll_iterations
        
        try:
            while (not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready()) and \
                  iterations <= max_iterations:
                
                data = ""
                
                # Check for data to receive
                if channel.recv_ready():
                    try:
                        r, _, _ = select.select([channel], [], [], timeout)
                        if r:
                            data = channel.recv(self.default_window_size)
                            if isinstance(data, bytes):
                                data = data.decode(self.default_encoding)
                    except socket.timeout:
                        pass
                
                # Check for stderr
                elif channel.recv_stderr_ready():
                    try:
                        r, _, _ = select.select([channel], [], [], timeout)
                        if r:
                            data = channel.recv_stderr(self.default_window_size)
                            if isinstance(data, bytes):
                                data = data.decode(self.default_encoding)
                            error += data
                    except socket.timeout:
                        pass
                
                # Process received data
                if data:
                    iterations = 0
                    output += data
                    
                    # Check for expect patterns
                    if expect_patterns and expect_responses:
                        for pattern in expect_patterns:
                            if pattern in output:
                                response = expect_responses.get(pattern, "")
                                if response:
                                    channel.send(response + '\n')
                                    self.logger.debug(f"Sent expect response: {response}")
                
                else:
                    iterations += 1
                    time.sleep(0.1)
                
                # Check for prompt if waiting
                if wait_for_prompt and prompt_pattern:
                    import re
                    if re.search(prompt_pattern, output):
                        break
                
                # Check if channel is ready to exit
                if channel.exit_status_ready():
                    break
            
            return output.strip(), error.strip()
            
        except Exception as e:
            self.logger.error(f"Error receiving output: {e}")
            return output.strip(), str(e)
    
    def _clean_channel_buffer(self, channel: Channel):
        """Clean the channel buffer."""
        try:
            while channel.recv_ready():
                channel.recv(4096)
        except:
            pass
    
    def _update_current_directory(self, host: str, cd_command: str):
        """Update the current directory for a host."""
        try:
            # Extract directory from cd command
            parts = cd_command.strip().split()
            if len(parts) >= 2:
                directory = parts[1]
                
                with self.lock:
                    if host in self.channel_info:
                        if directory == '-':
                            # cd - goes to previous directory
                            pass  # Could implement directory history
                        elif directory.startswith('/'):
                            # Absolute path
                            self.channel_info[host]['current_directory'] = directory
                        else:
                            # Relative path
                            current = self.channel_info[host].get('current_directory', '/')
                            if current.endswith('/'):
                                self.channel_info[host]['current_directory'] = current + directory
                            else:
                                self.channel_info[host]['current_directory'] = current + '/' + directory
        except Exception as e:
            self.logger.debug(f"Error updating current directory: {e}")
    
    def get_channel_info(self, host: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a channel.
        
        Args:
            host: Target host
            
        Returns:
            Channel information or None
        """
        with self.lock:
            return self.channel_info.get(host)
    
    def list_channels(self) -> Dict[str, Dict[str, Any]]:
        """
        List all channels and their information.
        
        Returns:
            Dictionary of channel information
        """
        with self.lock:
            return dict(self.channel_info)
    
    def execute_interactive_commands(self, host: str, commands: List[Tuple[str, List[str]]], 
                                   timeout: float = 60.0) -> List[ChannelResult]:
        """
        Execute interactive commands with expect patterns.
        
        Args:
            host: Target host
            commands: List of (command, expect_patterns) tuples
            timeout: Timeout for each command
            
        Returns:
            List of command results
        """
        results = []
        channel = self.get_channel(host) or self.create_channel(host)
        
        try:
            for command, expect_patterns in commands:
                cmd = ChannelCommand(
                    command=command,
                    timeout=timeout,
                    expect_patterns=expect_patterns,
                    wait_for_prompt=True
                )
                
                result = self._execute_single_command(channel, cmd, host)
                results.append(result)
                
                if not result.success:
                    break
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error in interactive commands on {host}: {e}")
            return [ChannelResult(
                command="interactive_session",
                output="",
                error=str(e),
                success=False
            )]
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all_channels() 