"""
ESP32 Soft AP Honeypot - Live Dashboard with Analytics & Reporting
CORRECTED VERSION for Serial/USB connection

Fixed Issues:
- Device tracking now properly counts unique MACs
- Statistics accumulation corrected
- Connection success rate calculation fixed
- Better parsing of serial data
- Real-time updates work properly

Requirements:
    pip install matplotlib pyserial pandas numpy

Usage:
    1. Upload ESP32-SoftAP-Fixed.ino to your ESP32
    2. Close Arduino Serial Monitor
    3. Change COM_PORT below (currently COM3)
    4. Run: python softap_analytics_fixed.py
    5. Press 'G' to generate analytics report
"""

import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
from collections import deque, Counter
from datetime import datetime, timedelta
import threading
import time
import re
import csv
import os
import pandas as pd
import numpy as np

# ==================== CONFIGURATION ====================
COM_PORT = 'COM6'  # Change to your ESP32 port
BAUD_RATE = 115200
MAX_DATA_POINTS = 120  # Show last 2 minutes of data
UPDATE_INTERVAL = 1000  # Update every 1 second

# ==================== DATA STORAGE ====================
class CrowdAnalytics:
    def __init__(self):
        # Real-time data
        self.timestamps = deque(maxlen=MAX_DATA_POINTS)
        self.connected_counts = deque(maxlen=MAX_DATA_POINTS)
        self.nearby_counts = deque(maxlen=MAX_DATA_POINTS)
        self.total_devices = deque(maxlen=MAX_DATA_POINTS)
        
        # Device tracking by MAC address
        self.devices_by_mac = {}  # mac -> {first_seen, last_seen, rssi_history, status, connect_time}
        
        # Hourly statistics
        self.hourly_stats = {}  # hour -> count
        
        # Connection analytics (from ESP32 [STATS] messages)
        self.total_probes = 0
        self.total_connections = 0
        
        # Historical data for reporting
        self.all_timestamps = []
        self.all_device_counts = []
        self.all_connection_attempts = []
        
        # CSV logging
        self.csv_file = None
        self.csv_writer = None
        self.lock = threading.Lock()
        
        self.session_start = datetime.now()
    
    def start_logging(self):
        """Start CSV logging"""
        filename = f'crowd_analytics_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        self.csv_file = open(filename, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['Timestamp', 'Connected', 'Nearby', 'Total_Probes', 
                                  'Total_Connections', 'Connection_Rate%', 'Unique_Devices'])
        print(f"📝 Logging to: {filename}")
        return filename
    
    def add_device(self, mac, rssi, status):
        """Track individual device"""
        now = datetime.now()
        
        with self.lock:
            if mac not in self.devices_by_mac:
                # New device
                self.devices_by_mac[mac] = {
                    'first_seen': now,
                    'last_seen': now,
                    'rssi_history': [rssi],
                    'status': status,
                    'connect_time': now if status == 'CONNECTED' else None,
                    'dwell_time': 0
                }
                print(f"✅ NEW device: {mac} | {status} | RSSI: {rssi}")
            else:
                # Update existing device
                self.devices_by_mac[mac]['last_seen'] = now
                self.devices_by_mac[mac]['rssi_history'].append(rssi)
                
                # Track connection event
                if status == 'CONNECTED' and self.devices_by_mac[mac]['status'] != 'CONNECTED':
                    self.devices_by_mac[mac]['connect_time'] = now
                
                self.devices_by_mac[mac]['status'] = status
                
                # Calculate dwell time
                self.devices_by_mac[mac]['dwell_time'] = (now - self.devices_by_mac[mac]['first_seen']).total_seconds()
            
            # Update hourly stats
            hour_key = now.strftime('%Y-%m-%d %H:00')
            self.hourly_stats[hour_key] = self.hourly_stats.get(hour_key, 0) + 1
    
    def add_statistics(self, connected, nearby, total_probes, total_connects):
        """Add statistics data point from ESP32 [STATS] message"""
        with self.lock:
            now = datetime.now()
            
            # Update cumulative totals
            self.total_probes = total_probes
            self.total_connections = total_connects
            
            # Add to time series
            self.timestamps.append(now)
            self.connected_counts.append(connected)
            self.nearby_counts.append(nearby)
            self.total_devices.append(connected + nearby)
            
            # Historical data
            self.all_timestamps.append(now)
            self.all_device_counts.append(connected + nearby)
            self.all_connection_attempts.append(total_connects)
            
            # Calculate connection success rate
            connection_rate = (total_connects / total_probes * 100) if total_probes > 0 else 0
            
            # Log to CSV
            if self.csv_writer:
                self.csv_writer.writerow([
                    now.strftime('%Y-%m-%d %H:%M:%S'),
                    connected,
                    nearby,
                    total_probes,
                    total_connects,
                    f"{connection_rate:.1f}",
                    len(self.devices_by_mac)
                ])
                self.csv_file.flush()
            
            print(f"📊 STATS: Connected={connected}, Nearby={nearby}, Probes={total_probes}, Connects={total_connects}, Unique={len(self.devices_by_mac)}")
    
    def get_plot_data(self):
        """Get data for plotting"""
        with self.lock:
            return {
                'timestamps': list(self.timestamps),
                'connected': list(self.connected_counts),
                'nearby': list(self.nearby_counts),
                'total': list(self.total_devices),
                'total_probes': self.total_probes,
                'total_connections': self.total_connections,
                'total_unique': len(self.devices_by_mac),
                'hourly_stats': dict(self.hourly_stats),
                'devices': dict(self.devices_by_mac)
            }
    
    def generate_analytics_report(self):
        """Generate comprehensive analytics report"""
        with self.lock:
            session_duration = (datetime.now() - self.session_start).total_seconds() / 3600  # hours
            
            # Peak hour analysis
            peak_hour = max(self.hourly_stats.items(), key=lambda x: x[1]) if self.hourly_stats else (None, 0)
            
            # Average devices
            avg_devices = np.mean(self.all_device_counts) if self.all_device_counts else 0
            
            # Dwell time analysis
            dwell_times = [d['dwell_time'] for d in self.devices_by_mac.values()]
            avg_dwell = np.mean(dwell_times) if dwell_times else 0
            max_dwell = max(dwell_times) if dwell_times else 0
            
            # Connection success rate
            success_rate = (self.total_connections / self.total_probes * 100) if self.total_probes > 0 else 0
            
            # Signal strength distribution
            all_rssi = []
            for device in self.devices_by_mac.values():
                all_rssi.extend(device['rssi_history'])
            avg_rssi = np.mean(all_rssi) if all_rssi else -100
            
            report = {
                'session_start': self.session_start.strftime('%Y-%m-%d %H:%M:%S'),
                'session_duration_hours': session_duration,
                'total_unique_devices': len(self.devices_by_mac),
                'total_probes': self.total_probes,
                'successful_connections': self.total_connections,
                'connection_success_rate': success_rate,
                'peak_hour': peak_hour[0] if peak_hour[0] else 'N/A',
                'peak_hour_count': peak_hour[1],
                'avg_devices': avg_devices,
                'avg_dwell_time_seconds': avg_dwell,
                'max_dwell_time_seconds': max_dwell,
                'avg_rssi': avg_rssi,
                'hourly_breakdown': self.hourly_stats
            }
            
            return report

analytics = CrowdAnalytics()

# ==================== SERIAL READER ====================
def parse_device_line(line):
    """
    Parse: [DEVICE] MAC:AA:BB:CC:DD:EE:FF | RSSI:-45 | STATUS:CONNECTED | IP:192.168.4.2
    """
    try:
        if '[DEVICE]' not in line:
            return False
        
        mac_match = re.search(r'MAC:([0-9A-F:]+)', line, re.IGNORECASE)
        rssi_match = re.search(r'RSSI:(-?\d+)', line)
        status_match = re.search(r'STATUS:(\w+)', line)
        
        if mac_match and rssi_match and status_match:
            mac = mac_match.group(1).upper()
            rssi = int(rssi_match.group(1))
            status = status_match.group(1)
            
            analytics.add_device(mac, rssi, status)
            return True
    except Exception as e:
        print(f"Parse error (device): {e}")
    
    return False

def parse_stats_line(line):
    """
    Parse: [STATS] CONNECTED:5 | NEARBY:12 | TOTAL_PROBES:156 | TOTAL_CONNECTS:23
    """
    try:
        if '[STATS]' not in line:
            return False
        
        connected_match = re.search(r'CONNECTED:(\d+)', line)
        nearby_match = re.search(r'NEARBY:(\d+)', line)
        probes_match = re.search(r'TOTAL_PROBES:(\d+)', line)
        connects_match = re.search(r'TOTAL_CONNECTS:(\d+)', line)
        
        if all([connected_match, nearby_match, probes_match, connects_match]):
            connected = int(connected_match.group(1))
            nearby = int(nearby_match.group(1))
            total_probes = int(probes_match.group(1))
            total_connects = int(connects_match.group(1))
            
            analytics.add_statistics(connected, nearby, total_probes, total_connects)
            return True
    except Exception as e:
        print(f"Parse error (stats): {e}")
    
    return False

def serial_reader_thread():
    """Read data from ESP32"""
    print(f"\n📡 Connecting to {COM_PORT}...")
    
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"✅ Connected to ESP32 on {COM_PORT}\n")
        print("="*70)
        
        analytics.start_logging()
        
        while True:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                
                if line:
                    # Try to parse as device or stats
                    is_device = parse_device_line(line)
                    is_stats = parse_stats_line(line)
                    
                    # Print line if not parsed (for debugging)
                    if not is_device and not is_stats:
                        print(f"   {line}")
            
            time.sleep(0.01)
    
    except serial.SerialException as e:
        print(f"\n❌ Serial Error: {e}")
        print("\nTroubleshooting:")
        print(f"  1. Check ESP32 is connected to {COM_PORT}")
        print("  2. Close Arduino Serial Monitor if open")
        print("  3. Install CH340 drivers if needed")
        print("  4. Try different COM port")
    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user")
        if analytics.csv_file:
            analytics.csv_file.close()

# ==================== REPORT GENERATION ====================
def generate_text_report():
    """Generate detailed text report"""
    report = analytics.generate_analytics_report()
    
    filename = f'crowd_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
    
    with open(filename, 'w') as f:
        f.write("="*80 + "\n")
        f.write(" ESP32 SOFT AP HONEYPOT - CROWD ANALYTICS REPORT ".center(80) + "\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"Session Start: {report['session_start']}\n")
        f.write(f"Session Duration: {report['session_duration_hours']:.2f} hours\n\n")
        
        f.write("="*80 + "\n")
        f.write(" DEVICE STATISTICS ".center(80) + "\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"Total Unique Devices Detected: {report['total_unique_devices']}\n")
        f.write(f"Total Connection Attempts (Probes): {report['total_probes']}\n")
        f.write(f"Successful Connections: {report['successful_connections']}\n")
        f.write(f"Connection Success Rate: {report['connection_success_rate']:.1f}%\n")
        f.write(f"Average Devices Present: {report['avg_devices']:.1f}\n\n")
        
        f.write("="*80 + "\n")
        f.write(" CROWD BEHAVIOR ANALYSIS ".center(80) + "\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"Peak Hour: {report['peak_hour']} ({report['peak_hour_count']} detections)\n")
        f.write(f"Average Dwell Time: {report['avg_dwell_time_seconds']:.0f} seconds ({report['avg_dwell_time_seconds']/60:.1f} minutes)\n")
        f.write(f"Maximum Dwell Time: {report['max_dwell_time_seconds']:.0f} seconds ({report['max_dwell_time_seconds']/60:.1f} minutes)\n")
        f.write(f"Average Signal Strength (RSSI): {report['avg_rssi']:.1f} dBm\n\n")
        
        f.write("="*80 + "\n")
        f.write(" HOURLY BREAKDOWN ".center(80) + "\n")
        f.write("="*80 + "\n\n")
        
        for hour, count in sorted(report['hourly_breakdown'].items()):
            f.write(f"{hour}: {count} detections\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write(" BUSINESS INSIGHTS & RECOMMENDATIONS ".center(80) + "\n")
        f.write("="*80 + "\n\n")
        
        # Business insights
        if report['connection_success_rate'] > 70:
            f.write("✅ HIGH ENGAGEMENT: Connection success rate is excellent (>70%)\n")
            f.write("   → Strong WiFi attraction, good for customer engagement\n\n")
        elif report['connection_success_rate'] > 40:
            f.write("⚠️  MODERATE ENGAGEMENT: Connection success rate is moderate (40-70%)\n")
            f.write("   → Consider improving WiFi naming or reducing barriers\n\n")
        else:
            f.write("❌ LOW ENGAGEMENT: Connection success rate is low (<40%)\n")
            f.write("   → Review WiFi setup and attractiveness\n\n")
        
        if report['avg_dwell_time_seconds'] > 300:  # 5 minutes
            f.write("✅ GOOD DWELL TIME: Customers staying longer than 5 minutes average\n")
            f.write("   → Indicates good customer engagement\n\n")
        else:
            f.write("⚠️  SHORT DWELL TIME: Customers leaving quickly\n")
            f.write("   → Consider improving experience or layout\n\n")
        
        f.write(f"📊 STAFFING RECOMMENDATION:\n")
        f.write(f"   Peak Hour ({report['peak_hour']}): Deploy maximum staff\n")
        f.write(f"   Average Load: Plan for {int(report['avg_devices'])} concurrent customers\n\n")
        
        f.write("="*80 + "\n\n")
    
    print(f"\n✅ Report generated: {filename}")
    return filename

# ==================== MATPLOTLIB DASHBOARD ====================
def create_dashboard():
    """Create live analytics dashboard"""
    
    plt.style.use('dark_background')
    
    fig = plt.figure(figsize=(18, 11))
    fig.canvas.manager.set_window_title('ESP32 Crowd Analytics Dashboard - CORRECTED')
    fig.patch.set_facecolor('#0a0a0a')
    
    gs = GridSpec(3, 3, figure=fig, hspace=0.35, wspace=0.35)
    
    # Create subplots
    ax_main = fig.add_subplot(gs[0, :])      # Main device count timeline
    ax_connection = fig.add_subplot(gs[1, 0]) # Connection success pie
    ax_hourly = fig.add_subplot(gs[1, 1:])    # Hourly distribution
    ax_dwell = fig.add_subplot(gs[2, 0])      # Dwell time
    ax_stats = fig.add_subplot(gs[2, 1:])     # Statistics panel
    
    # Style axes
    for ax in [ax_main, ax_hourly, ax_dwell]:
        ax.set_facecolor('#1a1a1a')
        ax.grid(True, alpha=0.15, linestyle='--', color='cyan')
    
    ax_connection.set_facecolor('#1a1a1a')
    ax_stats.axis('off')
    
    # Instructions text
    fig.text(0.99, 0.01, 'Press G to generate report | Press Q to quit', 
             ha='right', va='bottom', fontsize=9, color='yellow', alpha=0.7)
    
    stats_text = ax_stats.text(0.5, 0.5, '', transform=ax_stats.transAxes,
                               fontsize=11, verticalalignment='center',
                               horizontalalignment='center', family='monospace',
                               bbox=dict(boxstyle='round', facecolor='#1a1a1a', 
                                        alpha=0.9, pad=15, linewidth=2, edgecolor='cyan'))
    
    def on_key(event):
        """Handle keyboard events"""
        if event.key == 'g' or event.key == 'G':
            print("\n📊 Generating analytics report...")
            generate_text_report()
        elif event.key == 'q' or event.key == 'Q':
            print("\n🛑 Closing dashboard...")
            plt.close()
    
    fig.canvas.mpl_connect('key_press_event', on_key)
    
    def update_plot(frame):
        """Update all plots"""
        data = analytics.get_plot_data()
        
        if not data['timestamps']:
            return
        
        time_labels = [t.strftime('%H:%M:%S') for t in data['timestamps']]
        
        # Main timeline
        ax_main.clear()
        ax_main.set_facecolor('#1a1a1a')
        ax_main.grid(True, alpha=0.15, linestyle='--', color='cyan')
        
        ax_main.fill_between(range(len(data['connected'])), data['connected'], 
                             alpha=0.6, color='#00ff00', label='Connected')
        ax_main.fill_between(range(len(data['nearby'])), data['nearby'], 
                             alpha=0.4, color='#ffaa00', label='Nearby (Probing)')
        ax_main.plot(data['total'], 'c-', linewidth=2.5, label='Total Devices', alpha=0.9)
        
        ax_main.set_title('📱 Real-Time Device Detection', fontsize=15, fontweight='bold', 
                         color='cyan', pad=15)
        ax_main.set_ylabel('Number of Devices', fontsize=11, color='white')
        ax_main.legend(loc='upper left', fontsize=10, framealpha=0.8)
        ax_main.tick_params(colors='white', labelsize=9)
        if len(time_labels) > 0:
            step = max(1, len(time_labels) // 10)
            ax_main.set_xticks(range(0, len(time_labels), step))
            ax_main.set_xticklabels([time_labels[i] for i in range(0, len(time_labels), step)], 
                                   rotation=45, ha='right')
        
        # Connection success pie
        ax_connection.clear()
        ax_connection.set_facecolor('#1a1a1a')
        
        if data['total_probes'] > 0:
            success_rate = data['total_connections'] / data['total_probes'] * 100
            failed_rate = 100 - success_rate
            
            colors = ['#00ff00', '#ff4444']
            explode = (0.05, 0)
            
            ax_connection.pie([success_rate, failed_rate], 
                            labels=['Connected', 'Probe Only'],
                            autopct='%1.1f%%',
                            colors=colors,
                            explode=explode,
                            shadow=True,
                            startangle=90,
                            textprops={'color': 'white', 'fontsize': 10})
        
        ax_connection.set_title('Connection Success Rate', fontsize=13, fontweight='bold', 
                              color='lightgreen', pad=10)
        
        # Hourly distribution
        ax_hourly.clear()
        ax_hourly.set_facecolor('#1a1a1a')
        ax_hourly.grid(True, alpha=0.15, linestyle='--', color='cyan', axis='y')
        
        if data['hourly_stats']:
            hours = list(data['hourly_stats'].keys())
            counts = list(data['hourly_stats'].values())
            
            bars = ax_hourly.bar(range(len(hours)), counts, color='#ff6b6b', alpha=0.8, 
                                edgecolor='white', linewidth=1.5)
            
            # Highlight peak hour
            if counts:
                peak_idx = counts.index(max(counts))
                bars[peak_idx].set_color('#00ff00')
                bars[peak_idx].set_alpha(1.0)
            
            ax_hourly.set_xticks(range(len(hours)))
            ax_hourly.set_xticklabels([h.split()[1] for h in hours], 
                                     rotation=45, ha='right', fontsize=9)
        
        ax_hourly.set_title('📊 Hourly Traffic Distribution', fontsize=13, fontweight='bold', 
                          color='#ff6b6b', pad=10)
        ax_hourly.set_ylabel('Device Count', fontsize=10, color='white')
        ax_hourly.tick_params(colors='white', labelsize=9)
        
        # Dwell time distribution
        ax_dwell.clear()
        ax_dwell.set_facecolor('#1a1a1a')
        ax_dwell.grid(True, alpha=0.15, linestyle='--', color='cyan', axis='y')
        
        dwell_times = [d['dwell_time'] / 60 for d in data['devices'].values()]  # Convert to minutes
        
        if dwell_times:
            bins = [0, 1, 5, 10, 30, max(dwell_times) + 5]
            hist, _ = np.histogram(dwell_times, bins=bins)
            labels = ['<1m', '1-5m', '5-10m', '10-30m', '>30m']
            
            bars = ax_dwell.bar(range(len(hist)), hist, color='#9b59b6', alpha=0.8, 
                               edgecolor='white', linewidth=1.5)
            ax_dwell.set_xticks(range(len(labels)))
            ax_dwell.set_xticklabels(labels, fontsize=9)
        
        ax_dwell.set_title('⏱️ Customer Dwell Time', fontsize=13, fontweight='bold', 
                          color='#9b59b6', pad=10)
        ax_dwell.set_ylabel('Device Count', fontsize=10, color='white')
        ax_dwell.tick_params(colors='white', labelsize=9)
        
        # Statistics panel
        current_devices = data['total'][-1] if data['total'] else 0
        current_connected = data['connected'][-1] if data['connected'] else 0
        success_rate = (data['total_connections'] / data['total_probes'] * 100) if data['total_probes'] > 0 else 0
        
        avg_dwell = np.mean([d['dwell_time'] for d in data['devices'].values()]) if data['devices'] else 0
        
        stats_str = f"""
╔══════════════════════════════════════════════════════════════╗
║                  LIVE ANALYTICS DASHBOARD                    ║
╚══════════════════════════════════════════════════════════════╝

  CURRENT STATUS
  ├─ Devices Present: {current_devices}
  ├─ Connected: {current_connected}
  └─ Nearby (Probing): {current_devices - current_connected}

  CUMULATIVE STATISTICS
  ├─ Total Unique Devices: {data['total_unique']}
  ├─ Total Probes: {data['total_probes']}
  ├─ Successful Connections: {data['total_connections']}
  └─ Success Rate: {success_rate:.1f}%

  CROWD BEHAVIOR
  ├─ Average Dwell Time: {avg_dwell:.0f}s ({avg_dwell/60:.1f} min)
  └─ Status: {'🟢 ACTIVE' if current_devices > 0 else '🔴 IDLE'}

╔══════════════════════════════════════════════════════════════╗
║  INSIGHTS: {'HIGH TRAFFIC ✅' if current_devices > 5 else 'MODERATE 🟡' if current_devices > 2 else 'LOW ⚪'}  │  {'GOOD ENGAGEMENT ✅' if success_rate > 50 else 'IMPROVING 🟡'}  ║
╚══════════════════════════════════════════════════════════════╝
        """
        
        stats_text.set_text(stats_str)
        stats_text.set_color('white')
    
    ani = animation.FuncAnimation(fig, update_plot, interval=UPDATE_INTERVAL, 
                                 cache_frame_data=False, blit=False)
    
    plt.tight_layout()
    plt.show()

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*80)
    print(" ESP32 SOFT AP HONEYPOT - LIVE ANALYTICS DASHBOARD (CORRECTED) ".center(80))
    print("="*80)
    print("\n📋 Configuration:")
    print(f"   Serial Port: {COM_PORT}")
    print(f"   Baud Rate: {BAUD_RATE}")
    print(f"   Update Interval: {UPDATE_INTERVAL}ms")
    print(f"   Data Points: {MAX_DATA_POINTS}")
    print("\n📊 Dashboard Features:")
    print("   ✓ Real-time device tracking")
    print("   ✓ Connection success analysis")
    print("   ✓ Hourly traffic patterns")
    print("   ✓ Dwell time distribution")
    print("   ✓ Auto-generated analytics reports")
    print("   ✓ Fixed device counting and statistics")
    print("\n💡 Keyboard Commands:")
    print("   [G] - Generate detailed analytics report")
    print("   [Q] - Quit dashboard")
    print("\n🔧 Fixes Applied:")
    print("   ✓ Unique device counting corrected")
    print("   ✓ Connection success rate calculation fixed")
    print("   ✓ Statistics accumulation improved")
    print("   ✓ Better error handling and debugging")
    print("\n" + "-"*80 + "\n")
    
    # Start serial reader
    reader_thread = threading.Thread(target=serial_reader_thread, daemon=True)
    reader_thread.start()
    
    time.sleep(3)
    
    # Start dashboard
    try:
        create_dashboard()
    except KeyboardInterrupt:
        print("\n\n🛑 Dashboard closed")
    finally:
        if analytics.csv_file:
            analytics.csv_file.close()
            print("💾 Data saved to CSV")
        
        # Auto-generate final report
        print("\n📊 Generating final session report...")
        generate_text_report()
