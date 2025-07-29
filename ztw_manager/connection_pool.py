"""
Connection Pool for ZTWorkload Manager
Manages SSH connections with pooling, health checks, and automatic cleanup.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
from paramiko import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import (
    SSHException, AuthenticationException, NoValidConnectionsError,
    BadHostKeyException
)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .logger import StructuredLogger

# Author: Vamsi


@dataclass
class ConnectionInfo:
    """Information about an SSH connection."""
    host: str
    port: int
    user: str
    client: SSHClient
    created_at: datetime
    last_used: datetime
    use_count: int = 0
    is_active: bool = True
    error_count: int = 0
    last_error: Optional[str] = None


class ConnectionPool:
    """Manages a pool of SSH connections with automatic cleanup."""
    
    def __init__(self, 
                 max_connections: int = 50,
                 max_idle_time: int = 300,
                 connection_timeout: int = 30,
                 health_check_interval: int = 60):
        """
        Initialize connection pool.
        
        :param max_connections: Maximum number of connections in pool
        :param max_idle_time: Maximum idle time in seconds
        :param connection_timeout: Connection timeout in seconds
        :param health_check_interval: Health check interval in seconds
        """
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.connection_timeout = connection_timeout
        self.health_check_interval = health_check_interval
        
        # Connection storage
        self.connections: Dict[str, ConnectionInfo] = {}
        self.lock = threading.RLock()
        
        # Health check thread
        self.health_check_thread = None
        self.stop_health_check_event = threading.Event()
        
        # Start health check thread
        self._start_health_check()
    
    def _get_connection_key(self, host: str, port: int, user: str) -> str:
        """
        Generate connection key.
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        :return: Connection key
        """
        return f"{host}:{port}:{user}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((SSHException, AuthenticationException, NoValidConnectionsError))
    )
    def _create_connection(self, host: str, port: int, user: str, 
                          password: str = None, key_file: str = None) -> SSHClient:
        """
        Create a new SSH connection.
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        :param password: Password
        :param key_file: Key file path
        :return: SSH client
        """
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        
        try:
            if key_file:
                client.connect(
                    hostname=host,
                    port=port,
                    username=user,
                    key_filename=key_file,
                    timeout=self.connection_timeout,
                    banner_timeout=240,
                    auth_timeout=60
                )
            elif password:
                client.connect(
                    hostname=host,
                    port=port,
                    username=user,
                    password=password,
                    timeout=self.connection_timeout,
                    banner_timeout=240,
                    auth_timeout=60
                )
            else:
                raise ValueError("Either password or key_file must be provided")
            
            return client
            
        except Exception as e:
            client.close()
            raise e
    
    def get_connection(self, host: str, port: int, user: str, 
                      password: str = None, key_file: str = None) -> SSHClient:
        """
        Get a connection from the pool or create a new one.
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        :param password: Password
        :param key_file: Key file path
        :return: SSH client
        """
        connection_key = self._get_connection_key(host, port, user)
        
        with self.lock:
            # Check if connection exists and is active
            if connection_key in self.connections:
                conn_info = self.connections[connection_key]
                
                # Check if connection is still valid
                if self._test_connection(conn_info.client):
                    conn_info.last_used = datetime.now()
                    conn_info.use_count += 1
                    return conn_info.client
                else:
                    # Remove invalid connection
                    self._remove_connection(connection_key)
            
            # Check pool size limit
            if len(self.connections) >= self.max_connections:
                self._cleanup_idle_connections(count=1)
            
            # Create new connection
            client = self._create_connection(host, port, user, password, key_file)
            
            # Store connection info
            conn_info = ConnectionInfo(
                host=host,
                port=port,
                user=user,
                client=client,
                created_at=datetime.now(),
                last_used=datetime.now(),
                use_count=1
            )
            
            self.connections[connection_key] = conn_info
            
            return client
    
    def return_connection(self, host: str, port: int, user: str):
        """
        Return a connection to the pool (no-op for this implementation).
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        """
        # In this implementation, connections stay in the pool
        # until they are explicitly closed or cleaned up
        pass
    
    def close_connection(self, host: str, port: int, user: str):
        """
        Close a specific connection.
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        """
        connection_key = self._get_connection_key(host, port, user)
        
        with self.lock:
            if connection_key in self.connections:
                conn_info = self.connections[connection_key]
                try:
                    conn_info.client.close()
                except:
                    pass
                self._remove_connection(connection_key)
    
    def _remove_connection(self, connection_key: str):
        """
        Remove a connection from the pool.
        
        :param connection_key: Connection key
        """
        if connection_key in self.connections:
            del self.connections[connection_key]
    
    def _test_connection(self, client: SSHClient) -> bool:
        """
        Test if a connection is still active.
        
        :param client: SSH client to test
        :return: True if connection is active
        """
        try:
            # Try to execute a simple command
            stdin, stdout, stderr = client.exec_command("echo 'test'", timeout=5)
            exit_status = stdout.channel.recv_exit_status()
            return exit_status == 0
        except:
            return False
    
    def _cleanup_idle_connections(self, count: int = None):
        """
        Clean up idle connections.
        
        :param count: Number of connections to clean up (None for all idle)
        """
        with self.lock:
            now = datetime.now()
            idle_connections = []
            
            for key, conn_info in self.connections.items():
                idle_time = (now - conn_info.last_used).total_seconds()
                if idle_time > self.max_idle_time:
                    idle_connections.append((key, idle_time))
            
            # Sort by idle time (oldest first)
            idle_connections.sort(key=lambda x: x[1], reverse=True)
            
            # Remove connections
            to_remove = count if count is not None else len(idle_connections)
            for key, _ in idle_connections[:to_remove]:
                conn_info = self.connections[key]
                try:
                    conn_info.client.close()
                except:
                    pass
                self._remove_connection(key)
    
    def _start_health_check(self):
        """Start the health check thread."""
        if self.health_check_thread is None:
            self.stop_health_check_event.clear()
            self.health_check_thread = threading.Thread(target=self._health_check_worker, daemon=True)
            self.health_check_thread.start()
    
    def _health_check_worker(self):
        """Health check worker thread."""
        while not self.stop_health_check_event.is_set():
            try:
                # Clean up idle connections
                self._cleanup_idle_connections()
                
                # Test active connections
                with self.lock:
                    for key, conn_info in list(self.connections.items()):
                        if not self._test_connection(conn_info.client):
                            conn_info.is_active = False
                            try:
                                conn_info.client.close()
                            except:
                                pass
                            self._remove_connection(key)
                
                # Wait for next check
                self.stop_health_check_event.wait(self.health_check_interval)
                
            except Exception as e:
                # Log error and continue
                pass
    
    def stop_health_check(self):
        """Stop the health check thread."""
        if self.health_check_thread:
            self.stop_health_check_event.set()
            self.health_check_thread.join(timeout=5)
            self.health_check_thread = None
    
    def get_connection_info(self, host: str, port: int, user: str) -> Optional[ConnectionInfo]:
        """
        Get information about a connection.
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        :return: Connection information or None
        """
        connection_key = self._get_connection_key(host, port, user)
        
        with self.lock:
            return self.connections.get(connection_key)
    
    def list_connections(self) -> List[Tuple[str, ConnectionInfo]]:
        """
        List all connections in the pool.
        
        :return: List of (key, connection_info) tuples
        """
        with self.lock:
            return list(self.connections.items())
    
    def clear_pool(self):
        """Clear all connections from the pool."""
        with self.lock:
            for conn_info in self.connections.values():
                try:
                    conn_info.client.close()
                except:
                    pass
            self.connections.clear()
    
    @contextmanager
    def get_connection_context(self, host: str, port: int, user: str,
                             password: str = None, key_file: str = None):
        """
        Context manager for getting a connection.
        
        :param host: Host name
        :param port: Port number
        :param user: Username
        :param password: Password
        :param key_file: Key file path
        :yield: SSH client
        """
        client = self.get_connection(host, port, user, password, key_file)
        try:
            yield client
        finally:
            self.return_connection(host, port, user)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_health_check()
        self.clear_pool()


class JumphostConnectionPool(ConnectionPool):
    """Connection pool for jumphost connections."""
    
    def __init__(self, jumphost_config, **kwargs):
        """
        Initialize jumphost connection pool.
        
        :param jumphost_config: Jumphost configuration
        :param **kwargs: Additional pool configuration
        """
        super().__init__(**kwargs)
        self.jumphost_config = jumphost_config
        self.jumphost_client = None
    
    def _create_jumphost_connection(self) -> SSHClient:
        """
        Create connection to jumphost.
        
        :return: SSH client for jumphost
        """
        return self._create_connection(
            self.jumphost_config.host,
            self.jumphost_config.port,
            self.jumphost_config.user,
            self.jumphost_config.password,
            self.jumphost_config.key_file
        )
    
    def get_connection_through_jumphost(self, target_host: str, target_port: int, 
                                      target_user: str, password: str = None, 
                                      key_file: str = None) -> SSHClient:
        """
        Get connection through jumphost.
        
        :param target_host: Target host name
        :param target_port: Target port number
        :param target_user: Target username
        :param password: Target password
        :param key_file: Target key file
        :return: SSH client connected through jumphost
        """
        # Ensure jumphost connection exists
        if self.jumphost_client is None:
            self.jumphost_client = self._create_jumphost_connection()
        
        # Create transport through jumphost
        transport = self.jumphost_client.get_transport()
        dest_addr = (target_host, target_port)
        local_addr = ('', 0)  # Let the system choose local port
        
        # Create channel through jumphost
        channel = transport.open_channel("direct-tcpip", dest_addr, local_addr)
        
        # Create SSH client using the channel
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        
        # Connect through the channel
        if key_file:
            client.connect(
                hostname=target_host,
                port=target_port,
                username=target_user,
                key_filename=key_file,
                sock=channel,
                timeout=self.connection_timeout
            )
        elif password:
            client.connect(
                hostname=target_host,
                port=target_port,
                username=target_user,
                password=password,
                sock=channel,
                timeout=self.connection_timeout
            )
        else:
            raise ValueError("Either password or key_file must be provided")
        
        return client 