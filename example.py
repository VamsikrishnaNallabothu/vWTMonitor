#!/usr/bin/env python3
"""
Example script demonstrating vWT Monitor usage.
"""

import os
import sys
from pathlib import Path

# Add the ztgw_wrkld_conn_mgr package to the path
sys.path.insert(0, str(Path(__file__).parent))

from vwt_monitor import (
    SSHManager, Config, StructuredLogger, TrafficManager, TrafficTestConfig, ProtocolType, Direction
)


def example_basic_usage():
    """Example of basic SSH tool usage."""
    print("=== Basic SSH Tool Usage Example ===")
    
    # Create a simple configuration
    config = Config(
        hosts=["192.168.1.10", "192.168.1.11", "192.168.1.12"],
        user="root",
        password="password",  # In production, use key-based auth
        port=22,
        timeout=30,
        max_parallel=5
    )
    
    # Setup logger
    logger = StructuredLogger(
        level="info",
        log_file="logs/example.log",
        log_format="json"
    )
    
    # Use SSH manager
    with SSHManager(config, logger) as manager:
        # Execute a simple command
        print("Executing 'uptime' command...")
        results = manager.execute_command("uptime")
        
        # Display results
        for result in results:
            status = "✅ Success" if result.success else "❌ Failed"
            print(f"{result.host}: {status} (Exit: {result.exit_code}, Duration: {result.duration:.2f}s)")
            if result.output:
                print(f"  Output: {result.output.strip()}")
            if result.error:
                print(f"  Error: {result.error.strip()}")
        
        # Get metrics
        # metrics = manager.get_metrics_summary()
        # print(f"\nMetrics Summary:")
        # print(f"  Total Operations: {metrics['total_operations']}")
        # print(f"  Success Rate: {metrics['success_rate']:.1f}%")
        # print(f"  Average Duration: {metrics['avg_duration']:.2f}s")


def example_file_operations():
    """Example of file operations."""
    print("\n=== File Operations Example ===")
    
    # Create configuration
    config = Config(
        hosts=["192.168.1.10", "192.168.1.11"],
        user="root",
        password="password",
        port=22,
        timeout=30,
        max_parallel=3
    )
    
    logger = StructuredLogger(level="info")
    
    with SSHManager(config, logger) as manager:
        # Create a test file
        test_file = "test_upload.txt"
        with open(test_file, "w") as f:
            f.write("This is a test file for SSH Tool upload.\n")
        
        try:
            # Upload file
            print("Uploading test file...")
            upload_results = manager.upload_file(test_file, "/tmp/test_upload.txt")
            
            for result in upload_results:
                status = "✅ Success" if result.success else "❌ Failed"
                print(f"{result.host}: {status} (Size: {result.size} bytes, Duration: {result.duration:.2f}s)")
            
            # Download file
            print("\nDownloading file...")
            download_results = manager.download_file("/tmp/test_upload.txt", "downloads/")
            
            for result in download_results:
                status = "✅ Success" if result.success else "❌ Failed"
                print(f"{result.host}: {status} (Size: {result.size} bytes, Duration: {result.duration:.2f}s)")
        
        finally:
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)


def example_log_capture():
    """Example of real-time log capture."""
    print("\n=== Log Capture Example ===")
    
    config = Config(
        hosts=["192.168.1.10"],
        user="root",
        password="password",
        port=22,
        timeout=30,
        max_parallel=1
    )
    
    logger = StructuredLogger(level="info")
    
    with SSHManager(config, logger) as manager:
        print("Starting log capture (press Ctrl+C to stop)...")
        print("This will capture logs from /var/log/syslog")
        
        try:
            # Start log capture
            manager.start_log_capture("/var/log/syslog")
            
            # Keep running for a few seconds
            import time
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\nStopping log capture...")
            manager.stop_log_capture()


def example_advanced_configuration():
    """Example of advanced configuration."""
    print("\n=== Advanced Configuration Example ===")
    
    # Load configuration from file
    try:
        config = Config.load("config.yaml")
        print("Loaded configuration from config.yaml")
        print(f"  Hosts: {len(config.hosts)}")
        print(f"  User: {config.user}")
        print(f"  Max Parallel: {config.max_parallel}")
        print(f"  Log Level: {config.log_level}")
        
        if config.jumphost:
            print(f"  Jumphost: {config.jumphost.host}")
        
    except FileNotFoundError:
        print("config.yaml not found, using default configuration")
        config = Config(
            hosts=["192.168.1.10"],
            user="root",
            password="password"
        )
    
    # Use advanced features
    logger = StructuredLogger(
        level=config.log_level,
        log_file=config.log_file,
        log_format=config.log_format
    )
    
    with SSHManager(config, logger) as manager:
        # Execute command with advanced features
        results = manager.execute_command("echo 'Hello from SSH Tool!'")
        
        for result in results:
            print(f"{result.host}: {result.output.strip()}")
        



def example_chain_commands():
    """Example of chain command execution."""
    print("\n=== Chain Command Execution Example ===")
    
    config = Config(
        hosts=["192.168.1.10", "192.168.1.11"],
        user="root",
        password="password",
        port=22,
        timeout=30,
        max_parallel=3
    )
    
    logger = StructuredLogger(level="info")
    
    with SSHManager(config, logger) as manager:
        # Execute a chain of commands that depend on each other
        chain_commands = [
            "cd /tmp",
            "pwd",
            "mkdir -p test_chain",
            "cd test_chain",
            "echo 'Hello from chain execution' > test.txt",
            "ls -la",
            "cat test.txt",
            "cd ..",
            "rm -rf test_chain"
        ]
        
        print("Executing chain of commands...")
        chain_results = manager.execute_chain_commands(chain_commands)
        
        # Display results
        for host, host_results in chain_results.items():
            print(f"\nHost: {host}")
            for i, result in enumerate(host_results, 1):
                status = "✅ Success" if result.success else "❌ Failed"
                print(f"  {status} Command {i}: {result.command}")
                if result.output:
                    print(f"    Output: {result.output.strip()}")
                if result.error:
                    print(f"    Error: {result.error}")
                print(f"    Duration: {result.duration:.2f}s")


def example_interactive_commands():
    """Example of interactive commands with expect patterns."""
    print("\n=== Interactive Commands Example ===")
    
    config = Config(
        hosts=["192.168.1.10"],
        user="root",
        password="password",
        port=22,
        timeout=30,
        max_parallel=1
    )
    
    logger = StructuredLogger(level="info")
    
    with SSHManager(config, logger) as manager:
        # Interactive commands that require responses
        interactive_commands = [
            ("sudo -i", ["password:"]),
            ("password", []),  # Response to password prompt
            ("whoami", []),
            ("pwd", []),
            ("exit", [])  # Exit sudo
        ]
        
        print("Executing interactive commands...")
        interactive_results = manager.execute_interactive_commands(
            interactive_commands, timeout=30.0
        )
        
        # Display results
        for host, host_results in interactive_results.items():
            print(f"\nHost: {host}")
            for i, result in enumerate(host_results, 1):
                status = "✅ Success" if result.success else "❌ Failed"
                print(f"  {status} Command {i}: {result.command}")
                if result.output:
                    print(f"    Output: {result.output.strip()}")
                if result.error:
                    print(f"    Error: {result.error}")


def example_programmatic_usage():
    """Example of programmatic usage."""
    print("\n=== Programmatic Usage Example ===")
    
    from vwt_monitor import LogCapture, LogCaptureConfig, MetricsCollector
    
    # Create custom log capture configuration
    log_config = LogCaptureConfig(
        buffer_size=16384,
        flush_interval=0.5,
        max_file_size="50MB",
        rotation_count=3,
        compression=True,
        real_time_display=True
    )
    
    # Create metrics collector
    # metrics = MetricsCollector(enable_prometheus=False)
    
    # Create SSH manager with custom components
    config = Config(
        hosts=["192.168.1.10"],
        user="root",
        password="password"
    )
    
    logger = StructuredLogger(level="debug")
    
    with SSHManager(config, logger) as manager:
        # Execute multiple commands
        commands = ["whoami", "pwd", "date"]
        
        for cmd in commands:
            print(f"Executing: {cmd}")
            results = manager.execute_command(cmd)
            
            for result in results:
                if result.success:
                    print(f"  {result.host}: {result.output.strip()}")
                else:
                    print(f"  {result.host}: Error - {result.error}")
        
        # Get channel information
        channel_info = manager.get_channel_info()
        print(f"\nChannel Information:")
        for host, info in channel_info.items():
            print(f"  {host}: {info}")


def example_traffic_testing():
    """Example of traffic testing."""
    print("\n=== Traffic Testing Example ===")
    
    # Load configuration
    try:
        config = Config.load("config.yaml")
        print("Loaded configuration from config.yaml")
    except FileNotFoundError:
        print("config.yaml not found, using default configuration")
        config = Config(
            hosts=["192.168.1.10", "192.168.1.11", "192.168.1.12"],
            user="root",
            password="password"
        )
    
    # Setup logger
    logger = StructuredLogger(level="info")
    
    # Use SSH manager and traffic manager
    with SSHManager(config, logger) as manager:
        traffic_manager = TrafficManager(manager, config, logger)
        
        # Test TCP connectivity
        print("Testing TCP connectivity...")
        tcp_config = TrafficTestConfig(
            protocol=ProtocolType.TCP,
            direction=Direction.EAST_WEST,
            source_hosts=["192.168.1.10", "192.168.1.11"],
            target_hosts=["192.168.1.12"],
            target_ports=[22, 80, 443],
            duration=30,
            interval=1.0,
            packet_size=1024,
            concurrent_connections=5,
            timeout=10
        )
        # Build test_pairs for TCP
        test_pairs = []
        for s in tcp_config.source_hosts:
            for t in tcp_config.target_hosts:
                test_pairs.append({s: t})
        tcp_results = traffic_manager.run_traffic_test(test_pairs, tcp_config)
        
        # Display results
        for test_id, result in tcp_results.items():
            print(f"\nTest: {test_id}")
            print(f"  Protocol: {result.protocol.value}")
            print(f"  Source: {result.source_host} → Target: {result.target_host}:{result.target_port}")
            print(f"  Success: {result.success}")
            
            if result.success and result.latency:
                print(f"  Avg Latency: {result.latency.avg_latency_ms:.1f}ms")
                print(f"  Min Latency: {result.latency.min_latency_ms:.1f}ms")
                print(f"  Max Latency: {result.latency.max_latency_ms:.1f}ms")
            
            if result.success and result.throughput:
                print(f"  Avg Throughput: {result.throughput.avg_throughput_mbps:.2f} MB/s")
                print(f"  Peak Throughput: {result.throughput.peak_throughput_mbps:.2f} MB/s")
            
            if result.success and result.packets:
                print(f"  Packet Loss: {result.packets.packet_loss_percent:.2f}%")
        
        # Test HTTP connectivity
        print("\nTesting HTTP connectivity...")
        http_config = TrafficTestConfig(
            protocol=ProtocolType.HTTP,
            direction=Direction.EAST_WEST,
            source_hosts=["192.168.1.10"],
            target_hosts=["192.168.1.12"],
            target_ports=[80, 8080],
            duration=20,
            interval=2.0,
            timeout=15
        )
        # Build test_pairs for HTTP
        http_test_pairs = []
        for s in http_config.source_hosts:
            for t in http_config.target_hosts:
                http_test_pairs.append({s: t})
        http_results = traffic_manager.run_traffic_test(http_test_pairs, http_config)
        
        # Display HTTP results
        for test_id, result in http_results.items():
            print(f"\nHTTP Test: {test_id}")
            print(f"  Success: {result.success}")
            
            if result.success and result.protocol_specific:
                if result.protocol_specific.http_status_codes:
                    print("  HTTP Status Codes:")
                    for status_code, count in result.protocol_specific.http_status_codes.items():
                        print(f"    {status_code}: {count}")
        
        # Export results
        print("\nExporting results...")
        traffic_manager.export_results(tcp_results, "tcp_test_results.json", "json")
        traffic_manager.export_results(http_results, "http_test_results.json", "json")
        print("Results exported to JSON files")


def main():
    """Main example function."""
    print("vWT Monitor - Usage Examples")
    print("=" * 50)
    
    # Check if we have a config file
    if not os.path.exists("config.yaml"):
        print("Note: config.yaml not found. Examples will use default configuration.")
        print("Create a config.yaml file for more advanced examples.\n")
    
    try:
        # Run examples
        example_basic_usage()
        example_file_operations()
        example_chain_commands()
        example_interactive_commands()
        example_advanced_configuration()
        example_programmatic_usage()
        example_traffic_testing()
        
        # Log capture example (commented out as it requires real hosts)
        # example_log_capture()
        
        print("\n" + "=" * 50)
        print("Examples completed successfully!")
        print("\nTo run with real hosts:")
        print("1. Create a config.yaml file with your host details")
        print("2. Update the host IPs in the examples")
        print("3. Use key-based authentication for security")
        print("\nvWT Monitor features:")
        print("- Chain command execution: Commands that depend on each other")
        print("- Interactive commands: Commands with expect patterns")
        print("- Channel management: Persistent SSH channels for complex workflows")
        print("- Traffic testing: Network protocol testing with detailed metrics")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        print("Make sure you have the required dependencies installed:")
        print("  pip install -r requirements.txt")


if __name__ == "__main__":
    main() 