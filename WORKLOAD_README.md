# Workload Module for ZTWorkload Manager

The workload module provides convenient host-specific functions for each host specified in your `config.yaml` file. This allows you to perform operations like `host1.send_traffic(http, target=host2)`, `host2.execute(command)`, `host2.upload()`, etc.

## Quick Start

```python
from workload import create_workload, Protocol

# Create workload manager
with create_workload() as workload:
    # Get host objects
    host1 = workload.get_host("192.168.1.10")
    host2 = workload.get_host("192.168.1.11")
    
    # Execute commands
    result = host1.execute("ls -la")
    print(f"Output: {result.output}")
    
    # Send traffic
    traffic_result = host1.send_traffic(Protocol.HTTP, host2, port=80)
    print(f"Traffic test success: {traffic_result.success}")
    
    # Upload files
    upload_result = host1.upload("local_file.txt", "/tmp/remote_file.txt")
    print(f"Upload success: {upload_result.success}")
```

## Features

### Host-Specific Functions

Each host in your `config.yaml` gets its own workload object with the following methods:

#### Command Execution
- `host.execute(command, timeout=None, show_progress=None)` - Execute a command on the host
- `host.get_system_info()` - Get comprehensive system information
- `host.install_package(package)` - Install a package using the correct package manager for the Linux distribution
- `host.start_service(service)` - Start a service
- `host.stop_service(service)` - Stop a service

#### File Operations
- `host.upload(local_path, remote_path, show_progress=None)` - Upload a file to the host
- `host.download(remote_path, local_dir, show_progress=None)` - Download a file from the host

#### Network Testing
- `host.send_traffic(protocol, target, port=None, duration=60, **kwargs)` - Send traffic to a target
- `host.ping(target, count=4)` - Ping a target host
- `host.check_connectivity(target, port=22)` - Check connectivity to a target
- `host.run_iperf_test(target, protocol=Protocol.TCP, port=5201, duration=60, ...)` - Run iperf test from source host

#### Log Operations
- `host.tail(log_file, lines=10, follow=False, timeout=None, show_progress=None)` - Tail a log file
- `host.tail_realtime(log_file, lines=10, duration=60, filter_pattern=None, exclude_pattern=None)` - Real-time tail with filtering
- `host.grep_log(log_file, pattern, lines_before=0, lines_after=0, case_insensitive=False)` - Search for patterns in logs
- `host.get_log_stats(log_file)` - Get log file statistics

### Bulk Operations

The workload manager also provides bulk operations:

```python
# Execute command on all hosts
all_results = workload.execute_on_all("hostname")

# Upload file to all hosts
upload_all_results = workload.upload_to_all("file.txt", "/tmp/file.txt")

# Download file from all hosts
download_all_results = workload.download_from_all("/tmp/file.txt", "downloads/")

# Tail log files on all hosts
all_tail_results = workload.tail_on_all("/var/log/syslog", lines=10)

# Search for patterns in logs on all hosts
all_grep_results = workload.grep_log_on_all("/var/log/syslog", "error")

## API Reference

### WorkloadManager

#### Methods

- `get_host(host)` - Get a host workload object
- `get_all_hosts()` - Get all host workload objects
- `execute_on_all(command, timeout=None, show_progress=None)` - Execute command on all hosts
- `upload_to_all(local_path, remote_path, show_progress=None)` - Upload to all hosts
- `download_from_all(remote_path, local_dir, show_progress=None)` - Download from all hosts
- `run_traffic_test(source_host, target_host, protocol, port=None, duration=60, **kwargs)` - Run traffic test between hosts
- `tail_on_all(log_file, lines=10, follow=False, timeout=None, show_progress=None)` - Tail log files on all hosts
- `grep_log_on_all(log_file, pattern, lines_before=0, lines_after=0, case_insensitive=False)` - Search for patterns in logs on all hosts
- `get_log_stats_on_all(log_file)` - Get log statistics on all hosts

### HostWorkload

#### Methods

##### Command Execution
```python
result = host.execute("ls -la")
print(f"Success: {result.success}")
print(f"Output: {result.output}")
print(f"Error: {result.error}")
print(f"Exit code: {result.exit_code}")
```

##### File Operations
```python
# Upload
upload_result = host.upload("local_file.txt", "/tmp/remote_file.txt")

# Download
download_result = host.download("/tmp/remote_file.txt", "downloads/")
```

##### Network Testing
```python
# Send traffic
traffic_result = host.send_traffic(Protocol.HTTP, target_host, port=80, duration=30)

# Ping
ping_result = host.ping(target_host, count=4)

# Check connectivity
conn_result = host.check_connectivity(target_host, port=22)
```

##### System Operations
```python
# Get system info
sys_info = host.get_system_info()

# Install package
install_result = host.install_package("curl")

# Service management
start_result = host.start_service("ssh")
stop_result = host.stop_service("ssh")
```

##### Package Installation with Distribution Detection

The `install_package` method automatically detects the Linux distribution and uses the appropriate package manager:

```python
# The method automatically detects the distribution and uses the correct package manager:
# - Ubuntu/Debian: apt-get
# - CentOS/RHEL: yum or dnf (depending on version)
# - Fedora: dnf
# - SUSE: zypper
# - Arch: pacman
# - Alpine: apk

install_result = host.install_package("curl")
if install_result.success:
    print("Package installed successfully")
else:
    print(f"Installation failed: {install_result.error}")

# You can also check the distribution manually
distro_result = host.execute("cat /etc/os-release")
print(f"Distribution: {distro_result.output}")
```

##### Log Operations
```python
# Simple tail
tail_result = host.tail("/var/log/syslog", lines=10)

# Real-time tail with filtering
realtime_result = host.tail_realtime("/var/log/syslog", lines=10, duration=30, 
                                   filter_pattern="error", exclude_pattern="debug")

# Search for patterns
grep_result = host.grep_log("/var/log/syslog", "ssh", lines_before=2, lines_after=2)

# Get log statistics
stats_result = host.get_log_stats("/var/log/syslog")
```

### Supported Protocols

The workload module supports the following protocols for traffic testing:

- `Protocol.TCP` - TCP connectivity
- `Protocol.UDP` - UDP connectivity  
- `Protocol.HTTP` - HTTP requests
- `Protocol.HTTPS` - HTTPS requests
- `Protocol.SCP` - SCP file transfer
- `Protocol.FTP` - FTP file transfer
- `Protocol.DNS` - DNS resolution
- `Protocol.ICMP` - ICMP ping

## Configuration

The workload module uses the same configuration as ZTWorkload Manager. Make sure your `config.yaml` contains the hosts you want to work with:

```yaml
hosts:
  - "192.168.1.10"
  - "192.168.1.11"
  - "192.168.1.12"

user: "root"
password: ""  # or use key_file
key_file: "~/.ssh/id_rsa"
port: 22
timeout: 30
```

## Examples

### Basic Usage

```python
from workload import create_workload, Protocol

with create_workload() as workload:
    host1 = workload.get_host("192.168.1.10")
    host2 = workload.get_host("192.168.1.11")
    
    # Execute commands
    result = host1.execute("whoami")
    print(f"User: {result.output.strip()}")
    
    # Upload file
    upload_result = host1.upload("script.sh", "/tmp/script.sh")
    if upload_result.success:
        # Execute uploaded script
        exec_result = host1.execute("chmod +x /tmp/script.sh && /tmp/script.sh")
        print(f"Script execution: {exec_result.output}")
```

### Traffic Testing

```python
from workload import create_workload, Protocol

with create_workload() as workload:
    host1 = workload.get_host("192.168.1.10")
    host2 = workload.get_host("192.168.1.11")
    
    # HTTP traffic test
    http_result = host1.send_traffic(Protocol.HTTP, host2, port=80, duration=30)
    print(f"HTTP test: {http_result.success}")
    
    # TCP connectivity test
    tcp_result = host1.send_traffic(Protocol.TCP, host2, port=22, duration=10)
    print(f"TCP test: {tcp_result.success}")
    
    # Ping test
    ping_result = host1.ping(host2, count=5)
    print(f"Ping test: {ping_result.success}")
```

### Iperf Testing

```python
from workload import create_workload, Protocol

with create_workload() as workload:
    host1 = workload.get_host("192.168.1.10")
    host2 = workload.get_host("192.168.1.11")
    
    # Run TCP iperf test from host1 to host2
    tcp_result = host1.run_iperf_test(host2, protocol=Protocol.TCP, duration=30)
    print(f"TCP iperf test: {tcp_result.get('success', False)}")
    if tcp_result.get('success'):
        print(f"Average throughput: {tcp_result.get('average_throughput', 'N/A')} Gbits/sec")
    
    # Run UDP iperf test
    udp_result = host1.run_iperf_test(host2, protocol=Protocol.UDP, duration=30)
    print(f"UDP iperf test: {udp_result.get('success', False)}")
    
    # Custom iperf parameters
    custom_result = host1.run_iperf_test(
        host2, 
        protocol=Protocol.TCP,
        port=5202,
        duration=60,
        parallel_streams=4,
        mtu_size=1460,
        interval=5
    )
```

### Bulk Operations

```python
from workload import create_workload

with create_workload() as workload:
    # Execute command on all hosts
    all_results = workload.execute_on_all("hostname")
    for host, result in all_results.items():
        print(f"{host}: {result.output.strip()}")
    
    # Upload configuration to all hosts
    upload_results = workload.upload_to_all("config.conf", "/etc/app/config.conf")
    for host, result in upload_results.items():
        print(f"{host}: {'Success' if result.success else 'Failed'}")
```

### Service Management

```python
from workload import create_workload

with create_workload() as workload:
    host1 = workload.get_host("192.168.1.10")
    
    # Check service status
    status = host1.execute("systemctl is-active nginx")
    print(f"Nginx status: {status.output.strip()}")
    
    # Start service if not running
    if "inactive" in status.output:
        start_result = host1.start_service("nginx")
        print(f"Start nginx: {'Success' if start_result.success else 'Failed'}")
```

### Log Tailing and Analysis

```python
from workload import create_workload

with create_workload() as workload:
    host1 = workload.get_host("192.168.1.10")
    
    # Simple tail
    tail_result = host1.tail("/var/log/syslog", lines=20)
    print(f"Last 20 lines: {tail_result.output}")
    
    # Real-time tail with filtering
    realtime_result = host1.tail_realtime("/var/log/syslog", lines=10, duration=60,
                                        filter_pattern="error", exclude_pattern="debug")
    print(f"Real-time tail: {realtime_result.output}")
    
    # Search for specific patterns
    grep_result = host1.grep_log("/var/log/syslog", "ssh", lines_before=2, lines_after=2)
    print(f"SSH entries: {grep_result.output}")
    
    # Get log statistics
    stats_result = host1.get_log_stats("/var/log/syslog")
    print(f"Log stats: {stats_result.output}")
    
    # Bulk operations on all hosts
    all_tail_results = workload.tail_on_all("/var/log/syslog", lines=5)
    for host, result in all_tail_results.items():
        print(f"{host}: {result.output}")
```

## Error Handling

The workload module provides comprehensive error handling:

```python
from workload import create_workload

try:
    with create_workload() as workload:
        host1 = workload.get_host("192.168.1.10")
        
        result = host1.execute("some_command")
        if not result.success:
            print(f"Command failed: {result.error}")
            print(f"Exit code: {result.exit_code}")
            
except ValueError as e:
    print(f"Configuration error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Thread Safety

The workload module is thread-safe. Each `HostWorkload` object uses locks to ensure thread-safe operations when multiple threads access the same host.

## Logging

The workload module integrates with the ZTWorkload Manager logging system. All operations are logged with appropriate levels and can be configured through the workload configuration.

## Dependencies

The workload module depends on the following ZTWorkload Manager components:
- `ztw_manager.config.Config`
- `ztw_manager.ssh_manager.SSHManager`
- `ztw_manager.traffic_manager.TrafficManager`
- `ztw_manager.logger.StructuredLogger`

Make sure all dependencies are properly installed and configured. 