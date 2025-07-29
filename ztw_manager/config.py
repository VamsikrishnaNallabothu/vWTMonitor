"""
Configuration management for ZTWorkload Manager.
Provides dataclasses and utilities for managing SSH connection settings,
logging configuration, and advanced features.
"""

import os
import yaml
import configparser
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

# Author: Vamsi


@dataclass
class JumphostConfig:
    """Jumphost configuration settings."""
    host: str = ""
    user: str = ""
    password: str = ""
    key_file: str = ""
    port: int = 22
    timeout: int = 30


@dataclass
class LogCaptureConfig:
    """Real-time log capture configuration."""
    enabled: bool = True
    buffer_size: int = 8192
    flush_interval: float = 1.0
    max_file_size: str = "100MB"
    rotation_count: int = 5
    compression: bool = True
    real_time_display: bool = True
    filter_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)


@dataclass
class FileTransferConfig:
    """File transfer configuration."""
    chunk_size: int = 32768
    progress_bar: bool = True
    verify_checksum: bool = True
    preserve_permissions: bool = True


@dataclass
class SecurityConfig:
    """Security configuration."""
    strict_host_key_checking: bool = True
    known_hosts_file: str = "~/.ssh/known_hosts"
    key_types: List[str] = field(default_factory=lambda: ["ssh-rsa", "ssh-ed25519", "ecdsa-sha2-nistp256"])
    cipher_preferences: List[str] = field(default_factory=lambda: ["aes256-gcm@openssh.com", "aes128-gcm@openssh.com"])


@dataclass
class Config:
    """Main configuration class for SSH Tool."""
    
    # SSH Connection settings
    hosts: List[str] = field(default_factory=list)
    user: str = ""
    password: str = ""
    key_file: str = ""
    port: int = 22
    timeout: int = 30
    max_parallel: int = 10
    
    # Jumphost configuration
    jumphost: Optional[JumphostConfig] = None
    
    # Logging configuration
    log_level: str = "info"
    log_file: str = "logs/ztw_manager.log"
    log_format: str = "json"
    
    # Advanced SSH settings
    banner_timeout: int = 240
    keep_alive: int = 30
    compression: bool = False
    host_key_verification: bool = True
    
    # Performance and monitoring
    connection_pool_size: int = 50
    connection_idle_timeout: int = 300
    max_retries: int = 3
    retry_delay: int = 1
    
    # Real-time log capture settings
    log_capture: LogCaptureConfig = field(default_factory=LogCaptureConfig)
    
    # File transfer settings
    file_transfer: FileTransferConfig = field(default_factory=FileTransferConfig)
    
    # Security settings
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    def __post_init__(self):
        """Post-initialization processing."""
        self._expand_paths()
        self._validate()
    
    def _expand_paths(self):
        """Expand user paths in configuration."""
        if self.key_file:
            self.key_file = os.path.expanduser(self.key_file)
        
        if self.jumphost and self.jumphost.key_file:
            self.jumphost.key_file = os.path.expanduser(self.jumphost.key_file)
        
        if self.security.known_hosts_file:
            self.security.known_hosts_file = os.path.expanduser(self.security.known_hosts_file)
    
    def _validate(self):
        """Validate configuration settings."""
        if not self.hosts:
            raise ValueError("No hosts specified in configuration")
        
        if not self.user:
            raise ValueError("No username specified in configuration")
        
        if not self.password and not self.key_file:
            raise ValueError("Either password or key_file must be specified")
        
        if self.key_file and not os.path.exists(self.key_file):
            raise ValueError(f"Key file not found: {self.key_file}")
        
        if self.jumphost:
            if not self.jumphost.host:
                raise ValueError("Jumphost host not specified")
            if not self.jumphost.user:
                raise ValueError("Jumphost username not specified")
            if not self.jumphost.password and not self.jumphost.key_file:
                raise ValueError("Either jumphost password or key_file must be specified")
            if self.jumphost.key_file and not os.path.exists(self.jumphost.key_file):
                raise ValueError(f"Jumphost key file not found: {self.jumphost.key_file}")
    
    @classmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def load(cls, filename: str) -> 'Config':
        """
        Load configuration from YAML (.yaml/.yml) or INI/CFG (.cfg/.ini) file.
        
        :param filename: Path to configuration file
        :return: Config instance
        :raises FileNotFoundError: If config file doesn't exist
        :raises yaml.YAMLError: If YAML config file is invalid
        :raises ValueError: If configuration is invalid
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Configuration file not found: {filename}")
        ext = os.path.splitext(filename)[1].lower()
        if ext in ['.yaml', '.yml']:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise yaml.YAMLError(f"Invalid YAML in configuration file: {e}")
        elif ext in ['.cfg', '.ini']:
            parser = configparser.ConfigParser()
            parser.optionxform = str  # preserve case
            parser.read(filename, encoding='utf-8')
            data = {}
            for section in parser.sections():
                for key, value in parser.items(section):
                    # Handle nested sections like [[AWS]] as section.AWS
                    if key.startswith('[') and key.endswith(']'):
                        continue
                    data_key = f"{section}.{key}" if section not in ['DEFAULT'] else key
                    # Try to parse as float/int/bool if possible
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    else:
                        try:
                            value = int(value)
                        except ValueError:
                            try:
                                value = float(value)
                            except ValueError:
                                pass
                    data[data_key] = value
            # Flatten known sections for compatibility
            # Example: [AWS-EC2] USER -> aws_ec2_user
            for section in parser.sections():
                for key, value in parser.items(section):
                    flat_key = f"{section.replace('-', '_').lower()}_{key.lower()}"
                    data[flat_key] = value
        else:
            raise ValueError(f"Unsupported config file extension: {ext}")
        # The rest of the logic expects a dict like YAML
        # Create jumphost config if specified
        jumphost_data = data.get('jumphost')
        jumphost_config = None
        if jumphost_data:
            jumphost_config = JumphostConfig(**jumphost_data)
        # Create log capture config
        log_capture_data = data.get('log_capture', {})
        log_capture_config = LogCaptureConfig(**log_capture_data)
        # Create file transfer config
        file_transfer_data = data.get('file_transfer', {})
        file_transfer_config = FileTransferConfig(**file_transfer_data)
        # Create security config
        security_data = data.get('security', {})
        security_config = SecurityConfig(**security_data)
        # Create main config
        config_data = {k: v for k, v in data.items() 
                      if k not in ['jumphost', 'log_capture', 'file_transfer', 'security']}
        return cls(
            jumphost=jumphost_config,
            log_capture=log_capture_config,
            file_transfer=file_transfer_config,
            security=security_config,
            **config_data
        )
    
    def save(self, filename: str) -> None:
        """
        Save configuration to YAML file.
        
        :param filename: Path to save configuration file
        """
        # Convert dataclasses to dictionaries
        data = {
            'hosts': self.hosts,
            'user': self.user,
            'password': self.password,
            'key_file': self.key_file,
            'port': self.port,
            'timeout': self.timeout,
            'max_parallel': self.max_parallel,
            'log_level': self.log_level,
            'log_file': self.log_file,
            'log_format': self.log_format,
            'banner_timeout': self.banner_timeout,
            'keep_alive': self.keep_alive,
            'compression': self.compression,
            'host_key_verification': self.host_key_verification,
            'connection_pool_size': self.connection_pool_size,
            'connection_idle_timeout': self.connection_idle_timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
        }
        
        if self.jumphost:
            data['jumphost'] = {
                'host': self.jumphost.host,
                'user': self.jumphost.user,
                'password': self.jumphost.password,
                'key_file': self.jumphost.key_file,
                'port': self.jumphost.port,
                'timeout': self.jumphost.timeout,
            }
        
        data['log_capture'] = {
            'enabled': self.log_capture.enabled,
            'buffer_size': self.log_capture.buffer_size,
            'flush_interval': self.log_capture.flush_interval,
            'max_file_size': self.log_capture.max_file_size,
            'rotation_count': self.log_capture.rotation_count,
            'compression': self.log_capture.compression,
        }
        
        data['file_transfer'] = {
            'chunk_size': self.file_transfer.chunk_size,
            'progress_bar': self.file_transfer.progress_bar,
            'verify_checksum': self.file_transfer.verify_checksum,
            'preserve_permissions': self.file_transfer.preserve_permissions,
        }
        
        data['security'] = {
            'strict_host_key_checking': self.security.strict_host_key_checking,
            'known_hosts_file': self.security.known_hosts_file,
            'key_types': self.security.key_types,
            'cipher_preferences': self.security.cipher_preferences,
        }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)
    
    def merge_cli_args(self, **kwargs) -> None:
        """
        Merge command-line arguments into configuration.
        
        :param **kwargs: Command-line arguments to merge
        """
        if 'hosts' in kwargs and kwargs['hosts']:
            self.hosts = kwargs['hosts'].split(',')
        
        if 'user' in kwargs and kwargs['user']:
            self.user = kwargs['user']
        
        if 'password' in kwargs and kwargs['password']:
            self.password = kwargs['password']
        
        if 'key_file' in kwargs and kwargs['key_file']:
            self.key_file = kwargs['key_file']
        
        if 'port' in kwargs and kwargs['port']:
            self.port = kwargs['port']
        
        if 'timeout' in kwargs and kwargs['timeout']:
            self.timeout = kwargs['timeout']
        
        if 'max_parallel' in kwargs and kwargs['max_parallel']:
            self.max_parallel = kwargs['max_parallel']
        
        # Re-validate after merging
        self._expand_paths()
        self._validate() 