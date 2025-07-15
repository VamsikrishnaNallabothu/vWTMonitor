"""
Advanced connection pool for managing SSH connections efficiently.
"""

import asyncio
import threading
import time
import weakref
from typing import Dict, Optional, List, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import paramiko
from paramiko import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import SSHException, AuthenticationException, NoValidConnectionsError
import queue
import logging
from contextlib import contextmanager
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


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
    """Advanced SSH connection pool with connection reuse and health monitoring."""
    
    def __init__(self, 
                 max_connections: int = 50,
                 max_idle_time: int = 300,
                 connection_timeout: int = 30,
                 health_check_interval: int = 60,
                 enable_metrics: bool = True):
        """
        Initialize the connection pool.
        
        Args:
            max_connections: Maximum number of connections in the pool
            max_idle_time: Maximum idle time for connections (seconds)
            connection_timeout: Connection timeout (seconds)
            health_check_interval: Health check interval (seconds)
            enable_metrics: Enable connection metrics
        """
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.connection_timeout = connection_timeout
        self.health_check_interval = health_check_interval
        self.enable_metrics = enable_metrics
        
        # Connection storage
        self._connections: Dict[str, ConnectionInfo] = {}
        self._connection_queue = queue.Queue()
        self._lock = threading.RLock()
        
        # Connection tracking
        self.connection_times: List[float] = []
        
        # Health monitoring
        self._health_check_thread = None
        self._stop_health_check = threading.Event()
        
        # Start health check thread
        if health_check_interval > 0:
            self._start_health_check()
    
    def _get_connection_key(self, host: str, port: int, user: str) -> str:
        """Generate a unique key for a connection."""
        return f"{user}@{host}:{port}"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((SSHException, AuthenticationException, NoValidConnectionsError))
    )
    def _create_connection(self, host: str, port: int, user: str, 
                          password: str = None, key_file: str = None) -> SSHClient:
        """
        Create a new SSH connection with retry logic.
        
        Args:
            host: Target host
            port: SSH port
            user: Username
            password: Password (optional)
            key_file: Private key file path (optional)
            
        Returns:
            SSHClient instance
            
        Raises:
            SSHException: If connection fails
        """
        start_time = time.time()
        
        try:
            client = SSHClient()
            client.set_missing_host_key_policy(AutoAddPolicy())
            
            # Connection parameters
            connect_kwargs = {
                'hostname': host,
                'port': port,
                'username': user,
                'timeout': self.connection_timeout,
                'banner_timeout': self.connection_timeout * 2,
                'auth_timeout': self.connection_timeout
            }
            
            if password:
                connect_kwargs['password'] = password
            elif key_file:
                connect_kwargs['key_filename'] = key_file
            
            # Establish connection
            client.connect(**connect_kwargs)
            
            # Record connection time
            connection_time = time.time() - start_time
            self.connection_times.append(connection_time)
            
            # Record connection time
            with self._lock:
                pass
            
            return client
            
        except Exception as e:
            raise SSHException(f"Failed to connect to {host}:{port}: {str(e)}")
    
    def get_connection(self, host: str, port: int, user: str, 
                      password: str = None, key_file: str = None) -> SSHClient:
        """
        Get an SSH connection from the pool or create a new one.
        
        Args:
            host: Target host
            port: SSH port
            user: Username
            password: Password (optional)
            key_file: Private key file path (optional)
            
        Returns:
            SSHClient instance
        """
        connection_key = self._get_connection_key(host, port, user)
        
        with self._lock:
            # Check if connection exists and is active
            if connection_key in self._connections:
                conn_info = self._connections[connection_key]
                
                if conn_info.is_active:
                    # Update connection info
                    conn_info.last_used = datetime.now()
                    conn_info.use_count += 1
                    
                    # Test connection health
                    if self._test_connection(conn_info.client):
                        return conn_info.client
                    else:
                        # Mark as inactive and remove
                        conn_info.is_active = False
                        self._remove_connection(connection_key)
                else:
                    # Remove inactive connection
                    self._remove_connection(connection_key)
            
            # Check if we can create a new connection
            if len(self._connections) >= self.max_connections:
                # Remove oldest idle connection
                self._cleanup_idle_connections(1)
            
            # Create new connection
            client = self._create_connection(host, port, user, password, key_file)
            
            # Add to pool
            conn_info = ConnectionInfo(
                host=host,
                port=port,
                user=user,
                client=client,
                created_at=datetime.now(),
                last_used=datetime.now(),
                use_count=1
            )
            
            self._connections[connection_key] = conn_info
            
            return client
    
    def return_connection(self, host: str, port: int, user: str):
        """
        Return a connection to the pool.
        
        Args:
            host: Target host
            port: SSH port
            user: Username
        """
        connection_key = self._get_connection_key(host, port, user)
        
        with self._lock:
            if connection_key in self._connections:
                conn_info = self._connections[connection_key]
                conn_info.last_used = datetime.now()
    
    def close_connection(self, host: str, port: int, user: str):
        """
        Close and remove a specific connection.
        
        Args:
            host: Target host
            port: SSH port
            user: Username
        """
        connection_key = self._get_connection_key(host, port, user)
        
        with self._lock:
            if connection_key in self._connections:
                conn_info = self._connections[connection_key]
                try:
                    conn_info.client.close()
                except:
                    pass
                
                self._remove_connection(connection_key)
    
    def _remove_connection(self, connection_key: str):
        """Remove a connection from the pool."""
        if connection_key in self._connections:
            conn_info = self._connections[connection_key]
            
            del self._connections[connection_key]
    
    def _test_connection(self, client: SSHClient) -> bool:
        """
        Test if a connection is still active.
        
        Args:
            client: SSHClient to test
            
        Returns:
            True if connection is active, False otherwise
        """
        try:
            # Try to create a simple session to test connection
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                return False
            
            # Try to open a session
            session = transport.open_session()
            session.close()
            return True
            
        except Exception:
            return False
    
    def _cleanup_idle_connections(self, count: int = None):
        """
        Clean up idle connections.
        
        Args:
            count: Number of connections to clean up (None for all idle)
        """
        now = datetime.now()
        idle_connections = []
        
        for key, conn_info in self._connections.items():
            if not conn_info.is_active:
                continue
            
            idle_time = (now - conn_info.last_used).total_seconds()
            if idle_time > self.max_idle_time:
                idle_connections.append((key, idle_time))
        
        # Sort by idle time (oldest first)
        idle_connections.sort(key=lambda x: x[1], reverse=True)
        
        # Remove connections
        to_remove = count if count is not None else len(idle_connections)
        for key, _ in idle_connections[:to_remove]:
            self._remove_connection(key)
    
    def _start_health_check(self):
        """Start the health check thread."""
        def health_check_worker():
            while not self._stop_health_check.is_set():
                try:
                    with self._lock:
                        # Clean up idle connections
                        self._cleanup_idle_connections()
                        
                        # Test active connections
                        for key, conn_info in list(self._connections.items()):
                            if not conn_info.is_active:
                                continue
                            
                            if not self._test_connection(conn_info.client):
                                conn_info.is_active = False
                                conn_info.error_count += 1
                                conn_info.last_error = "Connection test failed"
                                
                                if conn_info.error_count >= 3:
                                    self._remove_connection(key)
                    

                    
                except Exception as e:
                    logging.warning(f"Health check error: {e}")
                
                # Wait for next check
                self._stop_health_check.wait(self.health_check_interval)
        
        self._health_check_thread = threading.Thread(target=health_check_worker, daemon=True)
        self._health_check_thread.start()
    
    def stop_health_check(self):
        """Stop the health check thread."""
        self._stop_health_check.set()
        if self._health_check_thread:
            self._health_check_thread.join()
    

    
    def get_connection_info(self, host: str, port: int, user: str) -> Optional[ConnectionInfo]:
        """Get information about a specific connection."""
        connection_key = self._get_connection_key(host, port, user)
        
        with self._lock:
            return self._connections.get(connection_key)
    
    def list_connections(self) -> List[Tuple[str, ConnectionInfo]]:
        """List all connections in the pool."""
        with self._lock:
            return list(self._connections.items())
    
    def clear_pool(self):
        """Clear all connections from the pool."""
        with self._lock:
            for conn_info in self._connections.values():
                try:
                    conn_info.client.close()
                except:
                    pass
            
            self._connections.clear()
    
    @contextmanager
    def get_connection_context(self, host: str, port: int, user: str,
                             password: str = None, key_file: str = None):
        """
        Context manager for getting and returning connections.
        
        Args:
            host: Target host
            port: SSH port
            user: Username
            password: Password (optional)
            key_file: Private key file path (optional)
            
        Yields:
            SSHClient instance
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
    """Connection pool with jumphost support."""
    
    def __init__(self, jumphost_config, **kwargs):
        """
        Initialize jumphost connection pool.
        
        Args:
            jumphost_config: Jumphost configuration
            **kwargs: Connection pool arguments
        """
        super().__init__(**kwargs)
        self.jumphost_config = jumphost_config
        self.jumphost_connection = None
    
    def _create_jumphost_connection(self) -> SSHClient:
        """Create connection to jumphost."""
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
        Get connection to target host through jumphost.
        
        Args:
            target_host: Target host
            target_port: Target port
            target_user: Target user
            password: Password (optional)
            key_file: Private key file path (optional)
            
        Returns:
            SSHClient connected to target through jumphost
        """
        # Get or create jumphost connection
        if self.jumphost_connection is None or not self._test_connection(self.jumphost_connection):
            self.jumphost_connection = self._create_jumphost_connection()
        
        # Create transport through jumphost
        jumphost_transport = self.jumphost_connection.get_transport()
        dest_addr = (target_host, target_port)
        local_addr = ('', 0)  # Let the jumphost choose local port
        
        # Create channel through jumphost
        channel = jumphost_transport.open_channel(
            'direct-tcpip', dest_addr, local_addr
        )
        
        # Create SSH client using the channel
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        
        # Connect through the channel
        connect_kwargs = {
            'sock': channel,
            'username': target_user,
            'timeout': self.connection_timeout,
            'banner_timeout': self.connection_timeout * 2,
            'auth_timeout': self.connection_timeout
        }
        
        if password:
            connect_kwargs['password'] = password
        elif key_file:
            connect_kwargs['key_filename'] = key_file
        
        client.connect(**connect_kwargs)
        
        return client 