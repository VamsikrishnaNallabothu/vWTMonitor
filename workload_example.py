#!/usr/bin/env python3
"""
Example usage of the workload module for ZTWorkload Manager.
"""

from workload import create_workload, Protocol

# Author: Vamsi


def main():
    """Example usage of the workload module."""
    
    # Create workload manager
    with create_workload() as workload:
        print("=== Workload Module Example ===\n")
        
        # Get host objects from config.yaml
        try:
            host1 = workload.get_host("192.168.1.10")
            host2 = workload.get_host("192.168.1.11")
            host3 = workload.get_host("192.168.1.12")
            
            print(f"Available hosts: {list(workload.get_all_hosts().keys())}\n")
            
            # Example 1: Execute commands on hosts
            print("=== Example 1: Execute Commands ===")
            result = host1.execute("whoami")
            print(f"Host1 whoami: {result.output.strip()}")
            
            result = host2.execute("pwd")
            print(f"Host2 pwd: {result.output.strip()}")
            
            # Example 2: Get system information
            print("\n=== Example 2: System Information ===")
            sys_info = host1.get_system_info()
            print(f"Host1 system info:\n{sys_info.output}")
            
            # Example 3: Upload and download files
            print("\n=== Example 3: File Operations ===")
            
            # Create a test file
            with open("test_file.txt", "w") as f:
                f.write("This is a test file for workload module\n")
            
            # Upload to host1
            upload_result = host1.upload("test_file.txt", "/tmp/test_file.txt")
            print(f"Upload to host1: {'Success' if upload_result.success else 'Failed'}")
            
            # Download from host1
            download_result = host1.download("/tmp/test_file.txt", "downloads/")
            print(f"Download from host1: {'Success' if download_result.success else 'Failed'}")
            
            # Example 4: Network connectivity tests
            print("\n=== Example 4: Network Tests ===")
            
            # Ping test
            ping_result = host1.ping(host2)
            print(f"Ping from host1 to host2: {'Success' if ping_result.success else 'Failed'}")
            
            # Connectivity check - uses nc to check if the port is open
            conn_result = host1.check_connectivity(host2, port=22)
            print(f"SSH connectivity from host1 to host2: {'Success' if conn_result.success else 'Failed'}")
            
            # Example 5: Traffic testing
            print("\n=== Example 5: Traffic Testing ===")
            
            # HTTP traffic test - uses curl to test the HTTP server on host2
            traffic_result = host1.send_traffic(Protocol.HTTP, host2, port=80, duration=10)
            print(f"HTTP traffic test from host1 to host2: {'Success' if traffic_result.success else 'Failed'}")
            
            # TCP traffic test - uses nc to test the TCP server on host2
            tcp_result = host1.send_traffic("tcp", host2, port=22, duration=5)
            print(f"TCP traffic test from host1 to host2: {'Success' if tcp_result.success else 'Failed'}")
            
            # Example 6: Service management
            print("\n=== Example 6: Service Management ===")
            
            # Check if SSH service is running - uses systemctl to check the status of the SSH service
            ssh_status = host1.execute("systemctl is-active ssh")
            print(f"SSH service status on host1: {ssh_status.output.strip()}")
            
            # Example 7: Package installation
            print("\n=== Example 7: Package Installation ===")
            
            # Detect Linux distribution first
            distro_result = host1.execute("cat /etc/os-release")
            print(f"Linux distribution detection: {'Success' if distro_result.success else 'Failed'}")
            if distro_result.success:
                print(f"Distribution info: {distro_result.output.strip()}")
            
            # Try to install a package (this might fail if not root or package not available)
            install_result = host1.install_package("curl")
            print(f"Package installation on host1: {'Success' if install_result.success else 'Failed'}")
            if not install_result.success:
                print(f"Installation error: {install_result.error}")
            
            # Try installing another common package
            install_result2 = host1.install_package("wget")
            print(f"Wget installation on host1: {'Success' if install_result2.success else 'Failed'}")
            
            # Example 8: Execute on all hosts
            print("\n=== Example 8: Execute on All Hosts ===")
            
            all_results = workload.execute_on_all("hostname")
            for host, result in all_results.items():
                print(f"{host}: {result.output.strip()}")
            
            # Example 9: Upload to all hosts
            print("\n=== Example 9: Upload to All Hosts ===")
            
            upload_all_results = workload.upload_to_all("test_file.txt", "/tmp/all_hosts_test.txt")
            for host, result in upload_all_results.items():
                print(f"{host}: {'Success' if result.success else 'Failed'}")
            
            # Example 10: Log tailing functionality
            print("\n=== Example 10: Log Tailing ===")
            
            # Simple tail
            tail_result = host1.tail("/var/log/syslog", lines=5)
            print(f"Tail syslog on host1: {'Success' if tail_result.success else 'Failed'}")
            if tail_result.success:
                print(f"Last 5 lines:\n{tail_result.output}")
            
            # Real-time tail with filtering
            realtime_result = host1.tail_realtime("/var/log/syslog", lines=10, duration=5, 
                                                filter_pattern="error", exclude_pattern="debug")
            print(f"Real-time tail with filtering: {'Success' if realtime_result.success else 'Failed'}")
            
            # Search for patterns in logs
            grep_result = host1.grep_log("/var/log/syslog", "ssh", lines_before=2, lines_after=2)
            print(f"Grep for SSH in syslog: {'Success' if grep_result.success else 'Failed'}")
            if grep_result.success:
                print(f"SSH entries:\n{grep_result.output}")
            
            # Get log statistics
            stats_result = host1.get_log_stats("/var/log/syslog")
            print(f"Log stats: {'Success' if stats_result.success else 'Failed'}")
            if stats_result.success:
                print(f"Log statistics:\n{stats_result.output}")
            
            # Example 11: Bulk log operations
            print("\n=== Example 11: Bulk Log Operations ===")
            
            # Tail on all hosts
            all_tail_results = workload.tail_on_all("/var/log/syslog", lines=3)
            for host, result in all_tail_results.items():
                print(f"{host} tail: {'Success' if result.success else 'Failed'}")
            
            # Search for patterns on all hosts
            all_grep_results = workload.grep_log_on_all("/var/log/syslog", "error", case_insensitive=True)
            for host, result in all_grep_results.items():
                print(f"{host} grep: {'Success' if result.success else 'Failed'}")
            
            # Get log stats on all hosts
            all_stats_results = workload.get_log_stats_on_all("/var/log/syslog")
            for host, result in all_stats_results.items():
                print(f"{host} stats: {'Success' if result.success else 'Failed'}")
            
            # Example 12: Iperf testing (proper source host execution)
            print("\n=== Example 12: Iperf Testing ===")
            
            # Run iperf test from host1 to host2
            iperf_result = host1.run_iperf_test(host2, protocol=Protocol.TCP, duration=10)
            print(f"Iperf TCP test from host1 to host2: {'Success' if iperf_result.get('success', False) else 'Failed'}")
            if iperf_result.get('success'):
                print(f"Average throughput: {iperf_result.get('average_throughput', 'N/A')} Gbits/sec")
            
            # Run UDP iperf test
            udp_result = host1.run_iperf_test(host2, protocol=Protocol.UDP, duration=10)
            print(f"Iperf UDP test from host1 to host2: {'Success' if udp_result.get('success', False) else 'Failed'}")
            
            print("\n=== Workload Example Completed ===")
            
        except ValueError as e:
            print(f"Error: {e}")
            print("Make sure the hosts in config.yaml match the ones you're trying to access.")
        except Exception as e:
            print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main() 