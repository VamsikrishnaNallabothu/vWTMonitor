# vWT Monitor

**vWT Monitor** - A high-performance, parallel SSH tool written in Python 3.10+ with enhanced features for scalable remote command execution, real-time log capture, and advanced monitoring capabilities.

## Features

### Core Features
- **Parallel SSH Operations**: Execute commands on multiple hosts simultaneously with configurable concurrency limits
- **Chain Command Execution**: Execute sequences of dependent commands using persistent SSH channels
- **Interactive Commands**: Support for expect patterns and interactive command sequences
- **Advanced Connection Pooling**: Efficient connection management with automatic health monitoring and cleanup
- **Jumphost Support**: Connect to remote hosts through intermediate jump hosts with full SSH tunneling
- **Real-time Log Capture**: Monitor log files across multiple hosts in real-time with structured output
- **Enhanced File Transfers**: Upload and download files with progress tracking, checksum verification, and compression
- **Network Traffic Testing**: Comprehensive protocol testing (TCP, UDP, HTTP, HTTPS, SCP, FTP, DNS, ICMP) with detailed metrics
- **Comprehensive Metrics**: Detailed performance metrics with Prometheus integration
- **Structured Logging**: Advanced logging with multiple formats (JSON, text, structured) and real-time dashboards

### Advanced Features
- **Channel Management**: Persistent SSH channels for complex workflows and stateful operations
- **Connection Health Monitoring**: Automatic detection and cleanup of stale connections
- **Retry Logic**: Intelligent retry mechanisms with exponential backoff
- **Security Enhancements**: Support for multiple key types, cipher preferences, and host key verification
- **Performance Optimizations**: Connection reuse, efficient I/O handling, and memory management
- **Real-time Dashboards**: Live monitoring dashboards for operations and log capture
- **Export Capabilities**: Export results in multiple formats (JSON, CSV, Prometheus) with detailed metadata

## Installation

### Prerequisites

- Python 3.10 or later
- SSH access to target hosts
- pip package manager

### Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd vwt-monitor

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Quick Start

```bash
# Basic command execution
python main.py execute -h host1,host2,host3 -u root -p password "ls -la"

# Using configuration file
python main.py execute -c config.yaml "ps aux"

# File upload
python main.py upload -h host1,host2 -u root -p password local_script.sh /tmp/

# File download
python main.py download -h host1,host2 -u root -p password /var/log/app.log

# Real-time log capture
python main.py tail -h host1,host2 -u root -p password /var/log/app.log
```

## Configuration

The tool uses YAML configuration files for flexible setup. Here's a comprehensive example:

```yaml
# vWT Monitor Configuration
hosts:
  - "192.168.1.10"
  - "192.168.1.11"
  - "192.168.1.12"

# SSH connection settings
user: "root"
password: ""  # Leave empty if using key-based authentication
key_file: "~/.ssh/id_rsa"
port: 22
timeout: 30
max_parallel: 10

# Jumphost configuration (optional)
jumphost:
  host: "jumphost.example.com"
  user: "jumpuser"
  password: ""
  key_file: "~/.ssh/jump_key"
  port: 22
  timeout: 30

# Logging configuration
log_level: "info"
log_file: "logs/vwt_monitor.log"
log_format: "json"

# Advanced SSH settings
banner_timeout: 240
keep_alive: 30
compression: false
host_key_verification: true

# Performance and monitoring
connection_pool_size: 50
connection_idle_timeout: 300
max_retries: 3
retry_delay: 1
enable_metrics: true
metrics_port: 9090

# Real-time log capture settings
log_capture:
  enabled: true
  buffer_size: 8192
  flush_interval: 1.0
  max_file_size: "100MB"
  rotation_count: 5
  compression: true

# File transfer settings
file_transfer:
  chunk_size: 32768
  progress_bar: true
  verify_checksum: true
  preserve_permissions: true

# Security settings
security:
  strict_host_key_checking: true
  known_hosts_file: "~/.ssh/known_hosts"
  key_types: ["ssh-rsa", "ssh-ed25519", "ecdsa-sha2-nistp256"]
  cipher_preferences: ["aes256-gcm@openssh.com", "aes128-gcm@openssh.com"]
```

## Usage

### Command Execution

Execute commands on multiple hosts in parallel:

```bash
# Basic command execution
python main.py execute -h host1,host2,host3 -u root -p password "df -h"

# Using key-based authentication
python main.py execute -h host1,host2 -u root -k ~/.ssh/id_rsa "systemctl status nginx"

# With custom timeout and parallel limits
python main.py execute -h host1,host2,host3 -u root -p password --timeout 60 --parallel 5 "long_running_command"

# Using configuration file
python main.py execute -c config.yaml "ps aux | grep python"

# Export results to file
python main.py execute -h host1,host2 -u root -p password -o results --format json "ls -la"
```

### Network Traffic Testing

Test network connectivity and performance across various protocols:

```bash
# Test TCP connectivity between hosts
python main.py traffic -s host1,host2 -t host3,host4 -p 22,80,443 --protocol tcp --direction east_west

# Test HTTP connectivity
python main.py traffic -s host1,host2 -t host3,host4 -p 80,8080 --protocol http --duration 30

# Test HTTPS with SSL verification
python main.py traffic -s host1 -t host2 -p 443 --protocol https --verify-ssl

# Test UDP connectivity
python main.py traffic -s host1,host2 -t host3,host4 -p 53,123 --protocol udp --packet-size 512

# Test DNS resolution
python main.py traffic -s host1,host2 -t 8.8.8.8,1.1.1.1 -p 53 --protocol dns

# Test ICMP ping
python main.py traffic -s host1,host2 -t host3,host4 --protocol icmp --interval 2

# Test SCP file transfer
python main.py traffic -s host1 -t host2 -p 22 --protocol scp --scp-user user --scp-pass password

# Test FTP file transfer
python main.py traffic -s host1 -t host2 -p 21 --protocol ftp --ftp-user user --ftp-pass password

# North-South connectivity testing
python main.py traffic -s host1,host2 -t google.com,github.com -p 80,443 --protocol http --direction north_south

# Using configuration file
python main.py traffic -c config.yaml --protocol tcp --duration 60 --interval 0.5

# Export results in different formats
python main.py traffic -s host1 -t host2 -p 80 --protocol http --format json
python main.py traffic -s host1 -t host2 -p 80 --protocol http --format csv
```

Available protocols and metrics:
- **TCP**: Connection latency, throughput, packet loss, retransmissions
- **UDP**: Packet loss, jitter, throughput
- **HTTP**: Response times, status codes, throughput
- **HTTPS**: SSL handshake times, response times, status codes
- **DNS**: Resolution times, success rates
- **ICMP**: Ping latency, packet loss
- **SCP**: Transfer speeds, connection success rates
- **FTP**: Transfer speeds, connection success rates

### Chain Command Execution

Execute sequences of dependent commands using persistent SSH channels:

```bash
# Execute chain of commands
python main.py chain -h host1,host2,host3 -u root -p password "cd /tmp" "pwd" "mkdir test" "cd test" "echo 'Hello' > file.txt" "cat file.txt"

# Using configuration file
python main.py chain -c config.yaml "cd /opt/app" "git pull" "npm install" "systemctl restart app"

# Create new channel for each execution
python main.py chain -h host1,host2 -u root -p password --new-channel "cd /tmp" "pwd" "ls -la"

# With custom timeout
python main.py chain -h host1,host2 -u root -p password --timeout 60 "long_command1" "long_command2" "long_command3"
```

### Interactive Commands

Execute interactive commands with expect patterns:

```bash
# Create commands file (commands.txt)
echo "sudo -i|password:" > commands.txt
echo "mypassword" >> commands.txt
echo "whoami" >> commands.txt
echo "exit" >> commands.txt

# Execute interactive commands
python main.py interactive -h host1,host2 -u root -p password commands.txt

# With custom timeout
python main.py interactive -h host1,host2 -u root -p password --timeout 30 commands.txt
```

Commands file format:
```
command|expect_pattern1,expect_pattern2
response_to_pattern
next_command
```

### File Operations

Upload and download files with progress tracking:

```bash
# Upload file to multiple hosts
python main.py upload -h host1,host2,host3 -u root -p password deploy.sh /tmp/

# Download file from multiple hosts
python main.py download -h host1,host2,host3 -u root -p password /var/log/app.log

# Upload with custom configuration
python main.py upload -c config.yaml --no-progress script.py /opt/scripts/

# Download with specific output directory
python main.py download -h host1,host2 -u root -p password -o downloads /var/log/nginx/access.log
```

### Real-time Log Capture

Monitor log files across multiple hosts in real-time:

```bash
# Start log capture
python main.py tail -h host1,host2,host3 -u root -p password /var/log/app.log

# Using jumphost
python main.py tail -c config.yaml /var/log/nginx/error.log

# With custom configuration
python main.py tail -h host1,host2 -u root -p password --timeout 60 /var/log/syslog
```

### Metrics and Monitoring

Export metrics and view statistics:

```bash
# Export metrics
python main.py metrics -c config.yaml -o metrics --format json

# Validate configuration
python main.py config-validate -c config.yaml
```

## Advanced Usage

### Programmatic Usage

Use the SSH Tool as a Python library:

```python
from ssh_tool import SSHManager, Config

# Load configuration
config = Config.load('config.yaml')

# Create SSH manager
with SSHManager(config) as manager:
    # Execute command
    results = manager.execute_command("ls -la")
    
    # Upload file
    upload_results = manager.upload_file("local.txt", "/tmp/remote.txt")
    
    # Download file
    download_results = manager.download_file("/var/log/app.log", "downloads/")
    
    # Start log capture
    manager.start_log_capture("/var/log/app.log")
    
    # Get metrics
    metrics = manager.get_metrics_summary()
    conn_stats = manager.get_connection_stats()
    
    # Chain command execution
    chain_commands = [
        "cd /tmp",
        "pwd",
        "mkdir test_chain",
        "cd test_chain",
        "echo 'Hello from chain' > test.txt",
        "cat test.txt"
    ]
    
    chain_results = manager.execute_chain_commands(chain_commands)
    for host, results in chain_results.items():
        print(f"Host {host}: {len(results)} commands executed")
    
    # Interactive commands
    interactive_commands = [
        ("sudo -i", ["password:"]),
        ("mypassword", []),
        ("whoami", []),
        ("exit", [])
    ]
    
    interactive_results = manager.execute_interactive_commands(interactive_commands)
    
    # Get channel information
    channel_info = manager.get_channel_info()
    print(f"Active channels: {len(channel_info)}")
```

### Real-time Logging Dashboard

Start a live logging dashboard:

```python
from ssh_tool import StructuredLogger

# Create logger with dashboard
logger = StructuredLogger(
    level="info",
    log_file="logs/ssh_tool.log",
    log_format="json"
)

# Start live dashboard
logger.start_live_dashboard()
```

### Custom Log Capture

Configure advanced log capture:

```python
from ssh_tool import LogCapture, LogCaptureConfig

# Custom configuration
config = LogCaptureConfig(
    buffer_size=16384,
    flush_interval=0.5,
    max_file_size="200MB",
    rotation_count=10,
    compression=True,
    real_time_display=True,
    filter_patterns=["ERROR", "WARNING"],
    exclude_patterns=["DEBUG"]
)

# Create log capture
log_capture = LogCapture(config)

# Start capture
log_capture.start_capture(host, ssh_client, "/var/log/app.log")
```

## Performance Optimizations

### Connection Pooling

The tool uses advanced connection pooling to optimize performance:

- **Connection Reuse**: Reuses SSH connections when possible
- **Health Monitoring**: Automatically detects and removes stale connections
- **Idle Timeout**: Configurable idle connection cleanup
- **Connection Limits**: Prevents resource exhaustion

### Parallel Execution

Efficient parallel execution with configurable limits:

- **Semaphore-based Concurrency**: Limits parallel connections
- **Thread Pool Management**: Efficient thread pool for operations
- **Progress Tracking**: Real-time progress bars for long operations
- **Error Handling**: Robust error handling and recovery

### Memory Management

Optimized memory usage:

- **Streaming I/O**: Processes large files without loading into memory
- **Buffer Management**: Configurable buffer sizes for different operations
- **Garbage Collection**: Automatic cleanup of unused resources
- **Memory Monitoring**: Real-time memory usage tracking

## Security Features

### Authentication

Multiple authentication methods:

- **Password Authentication**: Standard SSH password authentication
- **Key-based Authentication**: Support for SSH private keys
- **Multiple Key Types**: RSA, Ed25519, ECDSA key support
- **Jumphost Authentication**: Separate authentication for jump hosts

### Security Settings

Configurable security options:

- **Host Key Verification**: Strict host key checking
- **Known Hosts Management**: Custom known hosts file
- **Cipher Preferences**: Configurable cipher algorithms
- **Key Type Preferences**: Preferred key types for authentication

### Network Security

Enhanced network security:

- **Connection Timeouts**: Configurable timeouts for all operations
- **Banner Timeouts**: SSH banner timeout configuration
- **Keep-alive Settings**: SSH keep-alive configuration
- **Compression**: Optional SSH compression

## Monitoring and Metrics

### Prometheus Integration

Built-in Prometheus metrics:

- **Operation Counters**: Total operations, successful/failed operations
- **Connection Metrics**: Connection attempts, failures, active connections
- **Performance Metrics**: Operation duration histograms and summaries
- **Transfer Metrics**: Bytes transferred, file transfer statistics

### Real-time Dashboards

Live monitoring dashboards:

- **Operation Dashboard**: Real-time operation status and progress
- **Log Dashboard**: Live log capture with filtering and search
- **Metrics Dashboard**: Performance metrics and statistics
- **Connection Dashboard**: Connection pool status and health

### Export Capabilities

Multiple export formats:

- **JSON Export**: Structured JSON output with metadata
- **CSV Export**: Comma-separated values for analysis
- **Metrics Export**: Prometheus-compatible metrics
- **Log Export**: Structured log export with timestamps

## Troubleshooting

### Common Issues

1. **Connection Timeouts**
   - Increase timeout values in configuration
   - Check network connectivity
   - Verify SSH service status on target hosts

2. **Authentication Failures**
   - Verify credentials or key files
   - Check key file permissions (should be 600)
   - Ensure user has SSH access

3. **Permission Denied**
   - Check user permissions on target hosts
   - Verify file paths and permissions
   - Ensure sufficient disk space

4. **Jumphost Issues**
   - Verify jumphost configuration
   - Check jumphost connectivity
   - Ensure proper SSH tunneling setup

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
# Enable verbose logging
python main.py execute -h host1 -u root -p password -v "test_command"

# Check logs
tail -f logs/ssh_tool.log
```

### Performance Tuning

Optimize performance for your environment:

```yaml
# Performance tuning
max_parallel: 20          # Increase for high-bandwidth networks
connection_pool_size: 100 # Increase for many hosts
chunk_size: 65536         # Increase for large files
buffer_size: 16384        # Increase for high-volume logs
```

## Examples

### System Administration

```bash
# Check disk usage on all servers
python main.py execute -h web1,web2,db1 -u admin -k ~/.ssh/admin_key "df -h"

# Monitor system load
python main.py execute -h web1,web2,db1 -u admin -k ~/.ssh/admin_key "uptime"

# Check running services
python main.py execute -h web1,web2,db1 -u admin -k ~/.ssh/admin_key "systemctl status nginx"
```

### Log Monitoring

```bash
# Monitor application logs
python main.py tail -h app1,app2,app3 -u deploy -p deploypass /var/log/myapp/app.log

# Monitor system logs
python main.py tail -h web1,web2 -u admin -k ~/.ssh/admin_key /var/log/syslog
```

### Deployment

```bash
# Upload deployment script
python main.py upload -h prod1,prod2,prod3 -u deploy -k ~/.ssh/deploy_key deploy.sh /tmp/

# Execute deployment
python main.py execute -h prod1,prod2,prod3 -u deploy -k ~/.ssh/deploy_key "chmod +x /tmp/deploy.sh && /tmp/deploy.sh"

# Download logs after deployment
python main.py download -h prod1,prod2,prod3 -u deploy -k ~/.ssh/deploy_key /var/log/deploy.log
```

### Batch Operations

```bash
# Execute multiple commands
for cmd in "uptime" "df -h" "free -m"; do
    python main.py execute -h host1,host2,host3 -u root -p password "$cmd"
done

# Upload multiple files
for file in script1.sh script2.py config.yaml; do
    python main.py upload -h host1,host2,host3 -u root -p password "$file" /opt/scripts/
done
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:

- Check the documentation
- Review the examples
- Enable verbose logging for debugging 