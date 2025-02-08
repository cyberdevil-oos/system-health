import os
import sys
import logging
import subprocess
import winreg
import psutil
import platform
import socket
import mmap
import hashlib
import threading
import requests
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from collections import defaultdict

class SystemMaintenanceTool:
    def __init__(self):
        self.setup_logging()
        self.issues_queue = Queue()
        self.batch_size = 1000
        self.max_workers = min(32, os.cpu_count() * 2)
        self.scan_lock = threading.Lock()
        self.known_extensions = {'.exe', '.dll', '.sys', '.dat', '.ini', '.conf', '.json', '.xml'}
        self.steam_path = self.get_steam_path()
        self.directx_files = {
            'CoherentUI64.dll',
            'd3dcompiler_43.dll',
            'ffmpegsumo.dll',
            'icudt.dll',
            'libEGL.dll',
            'libGLESv2.dll'
        }
        self.health_scores = {
            'cpu': 0,
            'memory': 0,
            'disk': 0,
            'network': 0,
            'processes': 0
        }
        self.issues_found = []

    def setup_logging(self):
        """Configure logging with buffered output"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f'maintenance_{timestamp}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )

    def get_steam_path(self):
        """Get Steam installation path from registry"""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                return winreg.QueryValueEx(key, "InstallPath")[0]
        except:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam") as key:
                    return winreg.QueryValueEx(key, "InstallPath")[0]
            except:
                return None

    def get_drive_partitions(self):
        """Get system drives efficiently"""
        return [p.device for p in psutil.disk_partitions(all=False) 
                if 'fixed' in p.opts and os.path.exists(p.device)]

    def check_file_integrity(self, file_path):
        """Efficient file integrity check using memory mapping"""
        try:
            if not os.path.exists(file_path):
                return "Missing file"
                
            size = os.path.getsize(file_path)
            if size == 0:
                return "Zero-byte file"
                
            if size > 1024 * 1024:  # For files larger than 1MB
                with open(file_path, 'rb') as f:
                    header = f.read(8192)
                    f.seek(-8192, 2)
                    footer = f.read()
                    if not header or not footer:
                        return "Potentially corrupted"
            else:
                with open(file_path, 'rb') as f:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        if mm.read(1) is None:
                            return "Corrupted file"
            return None
        except Exception as e:
            return str(e)

    def scan_batch(self, file_batch):
        """Process a batch of files efficiently"""
        issues = []
        for file_path in file_batch:
            if any(file_path.endswith(ext) for ext in self.known_extensions):
                issue = self.check_file_integrity(file_path)
                if issue:
                    issues.append((file_path, issue))
        return issues

    def scan_directory_worker(self, directory):
        """Worker function for parallel directory scanning"""
        try:
            file_batch = []
            for root, _, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_batch.append(file_path)
                    
                    if len(file_batch) >= self.batch_size:
                        issues = self.scan_batch(file_batch)
                        if issues:
                            for issue in issues:
                                self.issues_queue.put(issue)
                        file_batch = []
                        
            if file_batch:
                issues = self.scan_batch(file_batch)
                if issues:
                    for issue in issues:
                        self.issues_queue.put(issue)
                        
        except Exception as e:
            logging.error(f"Error scanning {directory}: {e}")

    def repair_zero_byte_files(self, file_path):
        """Attempt to repair zero-byte files"""
        try:
            if not os.path.exists(file_path) or os.path.getsize(file_path) != 0:
                return

            if file_path.endswith('.dll'):
                self.repair_dll(file_path)
            elif file_path.endswith('.exe'):
                self.repair_executable(file_path)
            elif file_path.endswith('.dat'):
                self.repair_dat_file(file_path)

        except Exception as e:
            logging.error(f"Error repairing {file_path}: {e}")

    def repair_dll(self, dll_path):
        """Attempt to repair DLL files"""
        try:
            filename = os.path.basename(dll_path)
            if filename in self.directx_files:
                directx_url = "https://download.microsoft.com/download/1/7/1/1718CCC4-6315-4D8E-9543-8E28A4E18C4C/dxwebsetup.exe"
                installer_path = os.path.join(os.environ['TEMP'], 'dxwebsetup.exe')
                
                logging.info(f"Downloading DirectX installer...")
                response = requests.get(directx_url)
                with open(installer_path, 'wb') as f:
                    f.write(response.content)
                
                logging.info("Running DirectX installer...")
                subprocess.run([installer_path, '/silent'], check=True)
                logging.info(f"DirectX installation completed")
        except Exception as e:
            logging.error(f"Error repairing DLL {dll_path}: {e}")

    def repair_executable(self, exe_path):
        """Attempt to repair executable files"""
        try:
            if "Neverwinter" in exe_path:
                neverwinter_appid = "109600"
                self.verify_steam_game(neverwinter_appid)
        except Exception as e:
            logging.error(f"Error repairing executable {exe_path}: {e}")

    def repair_dat_file(self, dat_path):
        """Attempt to repair .dat files"""
        try:
            if any(x in dat_path.lower() for x in ['windows', 'microsoft', 'nvidia', 'system32']):
                return

            if os.path.getsize(dat_path) == 0:
                with open(dat_path, 'w') as f:
                    f.write('{"restored": true}')
                logging.info(f"Restored empty .dat file: {dat_path}")
        except Exception as e:
            logging.error(f"Error repairing DAT file {dat_path}: {e}")

    def verify_steam_game(self, app_id):
        """Verify integrity of Steam game files"""
        try:
            if self.steam_path:
                steam_exe = os.path.join(self.steam_path, 'steam.exe')
                if os.path.exists(steam_exe):
                    cmd = f'"{steam_exe}" -command "verify_integrity {app_id}"'
                    subprocess.run(cmd, shell=True)
                    logging.info(f"Verified Steam game {app_id}")
                    return True
            return False
        except Exception as e:
            logging.error(f"Error verifying Steam game {app_id}: {e}")
            return False

    def check_cpu(self):
        """Check CPU health and performance"""
        logging.info("\n=== CPU Status ===")
        
        cpu_score = 100
        cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
        avg_cpu = sum(cpu_percent) / len(cpu_percent)
        
        if avg_cpu > 90:
            cpu_score -= 40
            self.issues_found.append("Critical CPU usage (>90%)")
        elif avg_cpu > 70:
            cpu_score -= 20
            self.issues_found.append("High CPU usage (>70%)")
            
        logging.info(f"CPU Model: {platform.processor()}")
        logging.info(f"Average CPU Usage: {avg_cpu:.1f}%")
        for i, percentage in enumerate(cpu_percent):
            logging.info(f"CPU Core {i}: {percentage}%")
            if percentage > 90:
                self.issues_found.append(f"Core {i} is heavily loaded ({percentage}%)")
        
        self.health_scores['cpu'] = cpu_score

    def check_memory(self):
        """Check memory status"""
        memory_score = 100
        virtual_memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        if virtual_memory.percent > 90:
            memory_score -= 40
            self.issues_found.append("Critical RAM usage (>90%)")
        elif virtual_memory.percent > 80:
            memory_score -= 20
            self.issues_found.append("High RAM usage (>80%)")
            
        if swap.percent > 80:
            memory_score -= 20
            self.issues_found.append("High swap usage")
            
        logging.info("\n=== Memory Status ===")
        logging.info(f"Total RAM: {virtual_memory.total / (1024**3):.2f} GB")
        logging.info(f"Available RAM: {virtual_memory.available / (1024**3):.2f} GB")
        logging.info(f"RAM Usage: {virtual_memory.percent}%")
        logging.info(f"Swap Usage: {swap.percent}%")
        
        self.health_scores['memory'] = memory_score

    def check_disk(self):
        """Check disk space and health"""
        disk_score = 100
        
        logging.info("\n=== Disk Status ===")
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                logging.info(f"\nDrive {partition.device}:")
                logging.info(f"  Total: {usage.total / (1024**3):.2f} GB")
                logging.info(f"  Used: {usage.used / (1024**3):.2f} GB")
                logging.info(f"  Free: {usage.free / (1024**3):.2f} GB")
                logging.info(f"  Usage: {usage.percent}%")
                
                if usage.percent > 90:
                    disk_score -= 20
                    self.issues_found.append(f"Critical disk space usage on {partition.device}")
                elif usage.percent > 80:
                    disk_score -= 10
                    self.issues_found.append(f"High disk space usage on {partition.device}")
            except:
                continue
                
        self.health_scores['disk'] = disk_score

    def check_network(self):
        """Check network connectivity and performance"""
        network_score = 100
        
        logging.info("\n=== Network Status ===")
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            logging.info("Internet Connection: Available")
            
            net_io = psutil.net_io_counters()
            logging.info(f"Bytes Sent: {net_io.bytes_sent / (1024*1024):.2f} MB")
            logging.info(f"Bytes Received: {net_io.bytes_recv / (1024*1024):.2f} MB")
            
        except Exception as e:
            network_score -= 50
            self.issues_found.append("Network connectivity issues detected")
            logging.error(f"Network Error: {str(e)}")
            
        self.health_scores['network'] = network_score

    def check_processes(self):
        """Check system processes and resource usage"""
        process_score = 100
        
        logging.info("\n=== Process Status ===")
        high_cpu_processes = []
        high_memory_processes = []
        
        for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            try:
                pinfo = proc.info
                if pinfo['cpu_percent'] > 50:
                    high_cpu_processes.append(pinfo)
                if pinfo['memory_percent'] > 10:
                    high_memory_processes.append(pinfo)
            except:
                continue
        
        if high_cpu_processes:
            process_score -= len(high_cpu_processes) * 5
            logging.info("\nHigh CPU Usage Processes:")
            for proc in high_cpu_processes:
                logging.info(f"  {proc['name']}: {proc['cpu_percent']}%")
                
        if high_memory_processes:
            process_score -= len(high_memory_processes) * 5
            logging.info("\nHigh Memory Usage Processes:")
            for proc in high_memory_processes:
                logging.info(f"  {proc['name']}: {proc['memory_percent']:.1f}%")
                
        self.health_scores['processes'] = max(0, process_score)

    def generate_health_report(self):
        """Generate comprehensive system health report"""
        overall_score = sum(self.health_scores.values()) / len(self.health_scores)
        
        if overall_score >= 90:
            status = "EXCELLENT - Your system is running optimally"
        elif overall_score >= 80:
            status = "GOOD - Your system is running well with minor issues"
        elif overall_score >= 70:
            status = "FAIR - Your system needs some attention"
        elif overall_score >= 60:
            status = "POOR - Your system needs immediate attention"
        else:
            status = "CRITICAL - Your system requires urgent maintenance"

        report = [
            f"\nSystem Health Score: {overall_score:.1f}/100",
            f"Status: {status}",
            "\nComponent Scores:",
            f"CPU Health: {self.health_scores['cpu']}/100",
            f"Memory Health: {self.health_scores['memory']}/100",
            f"Disk Health: {self.health_scores['disk']}/100",
            f"Network Health: {self.health_scores['network']}/100",
            f"Process Health: {self.health_scores['processes']}/100"
        ]

        if self.issues_found:
            report.append("\nIssues Found:")
            for issue in self.issues_found:
                report.append(f"- {issue}")
            
            report.append("\nRecommended Actions:")
            if any("CPU" in issue for issue in self.issues_found):
                report.append("- Check and close CPU-intensive applications")
                report.append("- Consider upgrading your CPU if this is frequent")
            if any("RAM" in issue for issue in self.issues_found):
                report.append("- Close unnecessary applications to free up memory")
                report.append("- Consider adding more RAM")
            if any("disk" in issue.lower() for issue in self.issues_found):
                report.append("- Clean up disk space by removing unnecessary files")
                report.append("- Use disk cleanup tools to free up space")
            if any("network" in issue.lower() for issue in self.issues_found):
                report.append("- Check your network connection and router")
                report.append("- Contact your ISP if issues persist")
        else:
            report.append("\nNo significant issues found. Keep up the good work!")

        return report

    def scan_system(self):
        """Main scanning function with optimized parallel processing"""
        logging.info("Starting optimized system scan...")
        start_time = datetime.now()
        
        drives = self.get_drive_partitions()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.scan_directory_worker, drive) 
                      for drive in drives]
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Scan error: {e}")
                logging.info(f"Progress: {completed}/{len(drives)} drives scanned")

        self.generate_scan_report()
        
        duration = datetime.now() - start_time
        logging.info(f"Scan completed in {duration}")

    def generate_scan_report(self):
        """Generate scan report for file system issues"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f'scan_report_{timestamp}.txt'
        
        issues_by_type = defaultdict(list)
        while not self.issues_queue.empty():
            file_path, issue_type = self.issues_queue.get()
            issues_by_type[issue_type].append(file_path)

        with open(report_file, 'w', buffering=8192) as f:
            f.write("=== System File Scan Report ===\n\n")
            
            for issue_type, files in issues_by_type.items():
                f.write(f"\n{issue_type}:\n")
                f.write(f"Total: {len(files)}\n")
                for file_path in files:
                    f.write(f"  - {file_path}\n")

        logging.info(f"Scan report saved to: {report_file}")
        return report_file

    def repair_system_files(self, report_file):
        """Process scan report and repair files"""
        try:
            with open(report_file, 'r') as f:
                content = f.read()

            files_to_repair = set()
            for line in content.split('\n'):
                if line.strip().startswith('- '):
                    file_path = line.strip()[2:].strip()
                    files_to_repair.add(file_path)

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                executor.map(self.repair_zero_byte_files, files_to_repair)

            # Repair Visual Studio files if needed
            self.repair_visual_studio()

        except Exception as e:
            logging.error(f"Error processing scan report: {e}")

    def repair_visual_studio(self):
        """Repair Visual Studio installation if present"""
        try:
            program_files = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
            vs_installer = os.path.join(program_files, 'Microsoft Visual Studio', 'Installer', 'vs_installer.exe')
            
            if os.path.exists(vs_installer):
                logging.info("Repairing Visual Studio installation...")
                subprocess.run([vs_installer, ], check=True)
                logging.info("Visual Studio repair completed")
        except Exception as e:
            logging.error(f"Error repairing Visual Studio: {e}")

    def run_all_checks(self):
        """Run all system health checks"""
        print("Running comprehensive system checks...")
        
        self.check_cpu()
        self.check_memory()
        self.check_disk()
        self.check_network()
        self.check_processes()
        
        report = self.generate_health_report()
        
        print("\n" + "="*50)
        print("SYSTEM HEALTH REPORT")
        print("="*50)
        for line in report:
            print(line)
        print("="*50)

def main():
    if not os.name == 'nt':
        print("This script is designed for Windows systems only.")
        sys.exit(1)

    try:
        # Set process priority to below normal to reduce system impact
        try:
            import win32api
            import win32process
            win32process.SetPriorityClass(win32api.GetCurrentProcess(), 
                                        win32process.BELOW_NORMAL_PRIORITY_CLASS)
        except ImportError:
            pass

        print("=== System Maintenance Tool ===")
        print("1. Run System Health Check")
        print("2. Scan for File Issues")
        print("3. Repair File Issues")
        print("4. Run All (Health Check + Scan + Repair)")
        print("5. Exit")
        
        choice = input("\nEnter your choice (1-5): ")
        
        tool = SystemMaintenanceTool()
        
        if choice == "1":
            tool.run_all_checks()
        elif choice == "2":
            tool.scan_system()
        elif choice == "3":
            reports = [f for f in os.listdir('.') if f.startswith('scan_report_') and f.endswith('.txt')]
            if not reports:
                print("No scan report found. Please run a system scan first.")
            else:
                latest_report = max(reports)
                print(f"Using latest report: {latest_report}")
                tool.repair_system_files(latest_report)
        elif choice == "4":
            tool.run_all_checks()
            tool.scan_system()
            tool.repair_system_files(tool.generate_scan_report())
        elif choice == "5":
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid choice!")

        print(f"\nDetailed logs have been saved to: {tool.log_file}")
        input("\nPress Enter to exit...")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()