#!/usr/bin/env python3
"""
Example usage of ZTWorkload Manager
This demonstrates various features of the ZTWorkload Manager tool.
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

from ztw_manager import (
    SSHManager, Config, StructuredLogger, IperfManager, IperfTestConfig,
    TrafficManager, TrafficTestConfig, ProtocolType, Direction
)

# Author: Vamsi


def example_basic_usage():
    """
    Basic usage example - execute commands on multiple hosts.
    
    :return: None
    """
    print("=== Basic Usage Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    
    # Setup logger
    logger = StructuredLogger(
        level="info",
        log_file="logs/example.log",
        log_format="json"
    )
    
    # Create SSH manager
    ssh_manager = SSHManager(config, logger)
    
    try:
        # Execute a simple command on all hosts
        print("Executing 'whoami' on all hosts...")
        results = ssh_manager.execute_command("whoami")
        
        print(f"Results: {len(results)} hosts responded")
        for result in results:
            print(f"  {result.host}: {result.output.strip()}")
        
        # Execute a command with timeout
        print("\nExecuting 'sleep 5 && echo done' with timeout...")
        results = ssh_manager.execute_command("sleep 5 && echo done", timeout=10)
        
        for result in results:
            print(f"  {result.host}: {'Success' if result.success else 'Failed'}")
        
    finally:
        ssh_manager.close()


def example_file_operations():
    """
    File operations example - upload and download files.
    
    :return: None
    """
    print("\n=== File Operations Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    logger = StructuredLogger(level="info", log_file="logs/file_ops.log")
    ssh_manager = SSHManager(config, logger)
    
    try:
        # Create a test file
        test_file = "test_upload.txt"
        with open(test_file, "w") as f:
            f.write("This is a test file for upload\n")
        
        # Upload file to all hosts
        print("Uploading test file to all hosts...")
        upload_results = ssh_manager.upload_file(test_file, "/tmp/test_upload.txt")
        
        for result in upload_results:
            print(f"  {result.host}: {'Success' if result.success else 'Failed'}")
            if result.success:
                print(f"    Size: {result.size} bytes, Duration: {result.duration:.2f}s")
        
        # Download file from all hosts
        print("\nDownloading file from all hosts...")
        download_results = ssh_manager.download_file("/tmp/test_upload.txt", "downloads/")
        
        for result in download_results:
            print(f"  {result.host}: {'Success' if result.success else 'Failed'}")
            if result.success:
                print(f"    Local path: {result.local_path}")
        
        # Clean up
        os.remove(test_file)
        
    finally:
        ssh_manager.close()


def example_log_capture():
    """
    Log capture example - real-time log monitoring.
    
    :return: None
    """
    print("\n=== Log Capture Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    logger = StructuredLogger(level="info", log_file="logs/log_capture.log")
    ssh_manager = SSHManager(config, logger)
    
    try:
        # Start log capture on all hosts
        print("Starting log capture on all hosts...")
        ssh_manager.start_log_capture("/var/log/syslog")
        
        # Let it run for a few seconds
        print("Capturing logs for 10 seconds...")
        time.sleep(10)
        
        # Stop log capture
        print("Stopping log capture...")
        ssh_manager.stop_log_capture()
        
        print("Log capture completed")
        
    finally:
        ssh_manager.close()


def example_advanced_configuration():
    """
    Advanced configuration example.
    
    :return: None
    """
    print("\n=== Advanced Configuration Example ===")
    
    # Create configuration programmatically
    config = Config(
        hosts=["192.168.1.10", "192.168.1.11", "192.168.1.12"],
        user="admin",
        password="password123",
        port=22,
        timeout=30,
        max_parallel=5,
        log_level="debug",
        log_file="logs/advanced.log",
        log_format="json",
        banner_timeout=240,
        keep_alive=30,
        compression=False,
        host_key_verification=True,
        connection_pool_size=20,
        connection_idle_timeout=300,
        max_retries=3,
        retry_delay=1
    )
    
    # Setup logger with custom configuration
    logger = StructuredLogger(
        level=config.log_level,
        log_file=config.log_file,
        log_format=config.log_format,
        enable_console=True,
        enable_file=True
    )
    
    # Create SSH manager with advanced configuration
    ssh_manager = SSHManager(config, logger)
    
    try:
        # Test the configuration
        print("Testing advanced configuration...")
        results = ssh_manager.execute_command("echo 'Advanced config test'")
        
        for result in results:
            print(f"  {result.host}: {result.output.strip()}")
        
    finally:
        ssh_manager.close()


def example_chain_commands():
    """
    Chain commands example - execute multiple commands in sequence.
    
    :return: None
    """
    print("\n=== Chain Commands Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    logger = StructuredLogger(level="info", log_file="logs/chain_commands.log")
    ssh_manager = SSHManager(config, logger)
    
    try:
        # Define a chain of commands
        commands = [
            "pwd",
            "cd /tmp",
            "pwd",
            "ls -la",
            "echo 'Chain completed'"
        ]
        
        print("Executing chain of commands...")
        chain_results = ssh_manager.execute_chain_commands(commands)
        
        for host, results in chain_results.items():
            print(f"\nHost: {host}")
            for i, result in enumerate(results):
                print(f"  Command {i+1}: {result.command}")
                print(f"    Success: {result.success}")
                print(f"    Output: {result.output.strip()}")
                if result.error:
                    print(f"    Error: {result.error}")
        
    finally:
        ssh_manager.close()


def example_interactive_commands():
    """
    Interactive commands example - commands that require user input.
    
    :return: None
    """
    print("\n=== Interactive Commands Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    logger = StructuredLogger(level="info", log_file="logs/interactive.log")
    ssh_manager = SSHManager(config, logger)
    
    try:
        # Define interactive commands
        commands = [
            ("sudo -l", ["[sudo] password for admin:"]),
            ("echo 'password123'", []),
            ("whoami", [])
        ]
        
        print("Executing interactive commands...")
        interactive_results = ssh_manager.execute_interactive_commands(commands)
        
        for host, results in interactive_results.items():
            print(f"\nHost: {host}")
            for i, result in enumerate(results):
                print(f"  Step {i+1}: {result.command}")
                print(f"    Success: {result.success}")
                print(f"    Output: {result.output.strip()}")
        
    finally:
        ssh_manager.close()


def example_programmatic_usage():
    """
    Programmatic usage example - using the API directly.
    
    :return: None
    """
    print("\n=== Programmatic Usage Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    logger = StructuredLogger(level="info", log_file="logs/programmatic.log")
    
    # Create managers
    ssh_manager = SSHManager(config, logger)
    traffic_manager = TrafficManager(ssh_manager, config, logger)
    
    try:
        # Execute commands and collect metrics
        print("Executing commands and collecting metrics...")
        
        # System information
        sys_info_results = ssh_manager.execute_command("uname -a")
        for result in sys_info_results:
            print(f"  {result.host}: {result.output.strip()}")
        
        # Disk usage
        disk_results = ssh_manager.execute_command("df -h /")
        for result in disk_results:
            print(f"  {result.host} disk usage: {result.output.strip()}")
        
        # Memory usage
        memory_results = ssh_manager.execute_command("free -h")
        for result in memory_results:
            print(f"  {result.host} memory: {result.output.strip()}")
        
        # Get metrics summary
        metrics = ssh_manager.get_metrics_summary()
        print(f"\nMetrics Summary:")
        print(f"  Total commands executed: {metrics.get('total_commands', 0)}")
        print(f"  Successful commands: {metrics.get('successful_commands', 0)}")
        print(f"  Failed commands: {metrics.get('failed_commands', 0)}")
        print(f"  Average command duration: {metrics.get('avg_duration', 0):.2f}s")
        
    finally:
        ssh_manager.close()


def example_traffic_testing():
    """
    Traffic testing example - network connectivity tests.
    
    :return: None
    """
    print("\n=== Traffic Testing Example ===")
    
    # Load configuration
    config = Config.load("config.yaml")
    logger = StructuredLogger(level="info", log_file="logs/traffic_tests.log")
    ssh_manager = SSHManager(config, logger)
    traffic_manager = TrafficManager(ssh_manager, config, logger)
    
    try:
        # Define test pairs
        test_pairs = [
            {
                'source_host': '192.168.1.10',
                'target_host': '192.168.1.11',
                'target_port': 80
            },
            {
                'source_host': '192.168.1.11',
                'target_host': '192.168.1.10',
                'target_port': 22
            }
        ]
        
        # Create test configuration
        test_config = TrafficTestConfig(
            protocol=ProtocolType.TCP,
            direction=Direction.EAST_WEST,
            source_hosts=['192.168.1.10', '192.168.1.11'],
            target_hosts=['192.168.1.11', '192.168.1.10'],
            target_ports=[80, 22],
            duration=30,
            interval=1.0,
            packet_size=1024,
            concurrent_connections=5,
            timeout=10,
            retries=2
        )
        
        print("Running traffic tests...")
        results = traffic_manager.run_traffic_test(test_pairs, test_config)
        
        # Display results
        for test_id, result in results.items():
            print(f"\nTest: {test_id}")
            print(f"  Protocol: {result.protocol}")
            print(f"  Source: {result.source_host}")
            print(f"  Target: {result.target_host}:{result.target_port}")
            print(f"  Success: {result.success}")
            print(f"  Duration: {result.duration_seconds:.2f}s")
            
            if result.latency:
                print(f"  Latency: {result.latency.avg_latency_ms:.2f}ms avg")
            
            if result.throughput:
                print(f"  Throughput: {result.throughput.avg_throughput_mbps:.2f} Mbps avg")
            
            if result.packets:
                print(f"  Packet Loss: {result.packets.packet_loss_percent:.2f}%")
        
        # Export results
        traffic_manager.export_results(results, "traffic_test_results.json", "json")
        print("\nResults exported to traffic_test_results.json")
        
    finally:
        ssh_manager.close()


def main():
    """
    Main function to run all examples.
    
    :return: None
    """
    print("ZTWorkload Manager Examples")
    print("===================")
    
    try:
        # Run examples
        example_basic_usage()
        example_file_operations()
        example_log_capture()
        example_advanced_configuration()
        example_chain_commands()
        example_interactive_commands()
        example_programmatic_usage()
        example_traffic_testing()
        
        print("\nAll examples completed successfully!")
        
    except Exception as e:
        print(f"Error running examples: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 