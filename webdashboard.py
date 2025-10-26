"""
ESP32 Crowd Analytics - Enhanced Web Dashboard (FIXED)
Fixed for Dash 2.x compatibility

Changes:
- app.run_server() → app.run()
- Updated for latest Dash version

Requirements:
    pip install dash plotly pandas pyserial

Usage:
    python web_dashboard_fixed.py
"""

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import plotly.express as px
from collections import deque
from datetime import datetime
import pandas as pd
import serial
import threading
import time
import re

# ==================== CONFIGURATION ====================
COM_PORT = 'COM6'
BAUD_RATE = 115200
MAX_DATA_POINTS = 300
UPDATE_INTERVAL = 2000  # Update every 2 seconds

# ==================== DATA STORAGE ====================
class CrowdData:
    def __init__(self):
        self.timestamps = deque(maxlen=MAX_DATA_POINTS)
        self.connected = deque(maxlen=MAX_DATA_POINTS)
        self.nearby = deque(maxlen=MAX_DATA_POINTS)
        
        self.devices = {}
        self.total_probes = 0
        self.total_connections = 0
        
        self.rssi_history = deque(maxlen=1000)
        self.hourly_counts = {}
        
    def add_device(self, mac, rssi, status):
        now = datetime.now()
        
        if mac not in self.devices:
            self.devices[mac] = {
                'first_seen': now,
                'last_seen': now,
                'rssi': rssi,
                'status': status,
                'detections': 1
            }
        else:
            self.devices[mac]['last_seen'] = now
            self.devices[mac]['rssi'] = rssi
            self.devices[mac]['status'] = status
            self.devices[mac]['detections'] += 1
        
        self.rssi_history.append(rssi)
        
        hour_key = now.strftime('%H:00')
        self.hourly_counts[hour_key] = self.hourly_counts.get(hour_key, 0) + 1
    
    def add_stats(self, connected, nearby, probes, connects):
        now = datetime.now()
        self.timestamps.append(now)
        self.connected.append(connected)
        self.nearby.append(nearby)
        self.total_probes = probes
        self.total_connections = connects
    
    def get_dataframe(self):
        df = pd.DataFrame({
            'timestamp': list(self.timestamps),
            'connected': list(self.connected),
            'nearby': list(self.nearby),
            'total': [c + n for c, n in zip(self.connected, self.nearby)]
        })
        return df
    
    def get_device_table(self):
        devices_list = []
        now = datetime.now()
        
        for mac, info in self.devices.items():
            dwell = (now - info['first_seen']).total_seconds() / 60
            devices_list.append({
                'MAC': mac[-8:],
                'Status': info['status'],
                'RSSI': info['rssi'],
                'Detections': info['detections'],
                'Dwell (min)': f"{dwell:.1f}",
                'Last Seen': info['last_seen'].strftime('%H:%M:%S')
            })
        
        return pd.DataFrame(devices_list).sort_values('Last Seen', ascending=False) if devices_list else pd.DataFrame()

data = CrowdData()

# ==================== SERIAL READER ====================
def parse_device(line):
    if '[DEVICE]' not in line:
        return False
    
    mac_match = re.search(r'MAC:([0-9A-F:]+)', line, re.IGNORECASE)
    rssi_match = re.search(r'RSSI:(-?\d+)', line)
    status_match = re.search(r'STATUS:(\w+)', line)
    
    if all([mac_match, rssi_match, status_match]):
        data.add_device(
            mac_match.group(1).upper(),
            int(rssi_match.group(1)),
            status_match.group(1)
        )
        return True
    return False

def parse_stats(line):
    if '[STATS]' not in line:
        return False
    
    connected_match = re.search(r'CONNECTED:(\d+)', line)
    nearby_match = re.search(r'NEARBY:(\d+)', line)
    probes_match = re.search(r'TOTAL_PROBES:(\d+)', line)
    connects_match = re.search(r'TOTAL_CONNECTS:(\d+)', line)
    
    if all([connected_match, nearby_match, probes_match, connects_match]):
        data.add_stats(
            int(connected_match.group(1)),
            int(nearby_match.group(1)),
            int(probes_match.group(1)),
            int(connects_match.group(1))
        )
        return True
    return False

def serial_reader():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"✅ Connected to {COM_PORT}")
        
        while True:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    parse_device(line)
                    parse_stats(line)
            time.sleep(0.01)
    except Exception as e:
        print(f"❌ Serial error: {e}")

threading.Thread(target=serial_reader, daemon=True).start()

# ==================== DASH APP ====================
app = dash.Dash(__name__, update_title=None)
app.title = "ESP32 Crowd Analytics"

colors = {
    'background': '#0a0a0a',
    'text': '#ffffff',
    'primary': '#00d4ff',
    'success': '#00ff88',
    'warning': '#ffaa00',
    'danger': '#ff4444'
}

app.layout = html.Div(style={'backgroundColor': colors['background'], 'color': colors['text']}, children=[
    html.Div([
        html.H1('📡 ESP32 Crowd Analytics Dashboard', 
                style={'textAlign': 'center', 'color': colors['primary'], 'marginBottom': '10px'}),
        html.H4('Real-Time Device Tracking & Analysis', 
                style={'textAlign': 'center', 'color': colors['text'], 'opacity': '0.7'}),
    ], style={'padding': '20px'}),
    
    # Stats Cards
    html.Div([
        html.Div([
            html.Div([
                html.H3('Total Devices', style={'color': colors['text'], 'fontSize': '14px'}),
                html.H2(id='stat-total', children='0', style={'color': colors['primary'], 'fontSize': '36px', 'margin': '10px 0'}),
                html.P('Currently Present', style={'fontSize': '12px', 'opacity': '0.7'})
            ], style={'backgroundColor': '#1a1a1a', 'padding': '20px', 'borderRadius': '10px', 'textAlign': 'center'})
        ], style={'width': '23%', 'display': 'inline-block', 'margin': '0 1%'}),
        
        html.Div([
            html.Div([
                html.H3('Connected', style={'color': colors['text'], 'fontSize': '14px'}),
                html.H2(id='stat-connected', children='0', style={'color': colors['success'], 'fontSize': '36px', 'margin': '10px 0'}),
                html.P('Active Connections', style={'fontSize': '12px', 'opacity': '0.7'})
            ], style={'backgroundColor': '#1a1a1a', 'padding': '20px', 'borderRadius': '10px', 'textAlign': 'center'})
        ], style={'width': '23%', 'display': 'inline-block', 'margin': '0 1%'}),
        
        html.Div([
            html.Div([
                html.H3('Unique Devices', style={'color': colors['text'], 'fontSize': '14px'}),
                html.H2(id='stat-unique', children='0', style={'color': colors['warning'], 'fontSize': '36px', 'margin': '10px 0'}),
                html.P('Total Detected', style={'fontSize': '12px', 'opacity': '0.7'})
            ], style={'backgroundColor': '#1a1a1a', 'padding': '20px', 'borderRadius': '10px', 'textAlign': 'center'})
        ], style={'width': '23%', 'display': 'inline-block', 'margin': '0 1%'}),
        
        html.Div([
            html.Div([
                html.H3('Success Rate', style={'color': colors['text'], 'fontSize': '14px'}),
                html.H2(id='stat-success', children='0%', style={'color': colors['success'], 'fontSize': '36px', 'margin': '10px 0'}),
                html.P('Connection Rate', style={'fontSize': '12px', 'opacity': '0.7'})
            ], style={'backgroundColor': '#1a1a1a', 'padding': '20px', 'borderRadius': '10px', 'textAlign': 'center'})
        ], style={'width': '23%', 'display': 'inline-block', 'margin': '0 1%'}),
    ], style={'padding': '10px 20px'}),
    
    # Timeline Chart
    html.Div([
        html.Div([
            dcc.Graph(id='live-timeline', config={'displayModeBar': True})
        ], style={'width': '100%', 'display': 'inline-block'}),
    ], style={'padding': '10px 20px'}),
    
    # Pie and Hourly Charts
    html.Div([
        html.Div([
            dcc.Graph(id='pie-chart', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'margin': '0 1%'}),
        
        html.Div([
            dcc.Graph(id='hourly-chart', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'margin': '0 1%'}),
    ], style={'padding': '10px 20px'}),
    
    # RSSI and Device Table
    html.Div([
        html.Div([
            dcc.Graph(id='rssi-histogram', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'margin': '0 1%'}),
        
        html.Div([
            html.H3('📱 Active Devices', style={'color': colors['primary'], 'marginBottom': '15px'}),
            html.Div(id='device-table', style={'maxHeight': '400px', 'overflowY': 'auto'})
        ], style={'width': '48%', 'display': 'inline-block', 'margin': '0 1%', 'backgroundColor': '#1a1a1a', 
                 'padding': '20px', 'borderRadius': '10px'}),
    ], style={'padding': '10px 20px'}),
    
    dcc.Interval(id='interval-component', interval=UPDATE_INTERVAL, n_intervals=0),
    
    html.Div([
        html.P(f'🔄 Auto-refresh every {UPDATE_INTERVAL/1000}s | 📊 Showing last {MAX_DATA_POINTS} data points', 
               style={'textAlign': 'center', 'opacity': '0.5', 'fontSize': '12px', 'padding': '20px'})
    ])
])

@app.callback(
    [Output('stat-total', 'children'),
     Output('stat-connected', 'children'),
     Output('stat-unique', 'children'),
     Output('stat-success', 'children'),
     Output('live-timeline', 'figure'),
     Output('pie-chart', 'figure'),
     Output('hourly-chart', 'figure'),
     Output('rssi-histogram', 'figure'),
     Output('device-table', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    df = data.get_dataframe()
    
    current_total = df['total'].iloc[-1] if len(df) > 0 else 0
    current_connected = df['connected'].iloc[-1] if len(df) > 0 else 0
    total_unique = len(data.devices)
    success_rate = (data.total_connections / data.total_probes * 100) if data.total_probes > 0 else 0
    
    # Timeline
    timeline_fig = go.Figure()
    if len(df) > 0:
        timeline_fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['connected'],
            name='Connected', fill='tozeroy',
            line=dict(color=colors['success'], width=2),
            fillcolor=f"rgba(0, 255, 136, 0.3)"
        ))
        timeline_fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['nearby'],
            name='Nearby', fill='tozeroy',
            line=dict(color=colors['warning'], width=2),
            fillcolor=f"rgba(255, 170, 0, 0.2)"
        ))
        timeline_fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['total'],
            name='Total', mode='lines',
            line=dict(color=colors['primary'], width=3)
        ))
    
    timeline_fig.update_layout(
        title='📈 Real-Time Device Detection',
        xaxis_title='Time',
        yaxis_title='Number of Devices',
        hovermode='x unified',
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font=dict(color=colors['text']),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        height=400
    )
    
    # Pie Chart
    pie_fig = go.Figure(data=[go.Pie(
        labels=['Connected', 'Probe Only'],
        values=[data.total_connections, max(data.total_probes - data.total_connections, 0)],
        marker=dict(colors=[colors['success'], colors['danger']]),
        hole=0.4,
        textfont=dict(size=14, color='white')
    )])
    pie_fig.update_layout(
        title='Connection Success Rate',
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font=dict(color=colors['text']),
        height=300
    )
    
    # Hourly Chart
    hourly_df = pd.DataFrame(list(data.hourly_counts.items()), columns=['Hour', 'Count'])
    if len(hourly_df) > 0:
        hourly_fig = px.bar(hourly_df, x='Hour', y='Count', 
                            title='📊 Hourly Traffic Distribution',
                            color='Count',
                            color_continuous_scale='Viridis')
    else:
        hourly_fig = go.Figure()
        hourly_fig.add_annotation(text="No data yet", xref="paper", yref="paper", 
                                 x=0.5, y=0.5, showarrow=False, font=dict(size=20, color=colors['text']))
    
    hourly_fig.update_layout(
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font=dict(color=colors['text']),
        height=300
    )
    
    # RSSI Histogram
    if len(data.rssi_history) > 0:
        rssi_fig = px.histogram(
            x=list(data.rssi_history),
            nbins=30,
            title='📡 Signal Strength Distribution (RSSI)',
            labels={'x': 'RSSI (dBm)', 'y': 'Count'},
            color_discrete_sequence=[colors['primary']]
        )
    else:
        rssi_fig = go.Figure()
        rssi_fig.add_annotation(text="No RSSI data yet", xref="paper", yref="paper",
                               x=0.5, y=0.5, showarrow=False, font=dict(size=20, color=colors['text']))
    
    rssi_fig.update_layout(
        plot_bgcolor='#1a1a1a',
        paper_bgcolor='#1a1a1a',
        font=dict(color=colors['text']),
        height=300
    )
    
    # Device Table
    device_df = data.get_device_table()
    if len(device_df) > 0:
        table = html.Table([
            html.Thead(html.Tr([html.Th(col, style={'padding': '10px', 'borderBottom': '2px solid #00d4ff'}) 
                               for col in device_df.columns])),
            html.Tbody([
                html.Tr([
                    html.Td(device_df.iloc[i][col], style={'padding': '8px', 'borderBottom': '1px solid #333'}) 
                    for col in device_df.columns
                ]) for i in range(min(10, len(device_df)))
            ])
        ], style={'width': '100%', 'color': colors['text']})
    else:
        table = html.P('No devices detected yet...', style={'textAlign': 'center', 'opacity': '0.5'})
    
    return (
        f"{current_total:.0f}",
        f"{current_connected:.0f}",
        f"{total_unique}",
        f"{success_rate:.1f}%",
        timeline_fig,
        pie_fig,
        hourly_fig,
        rssi_fig,
        table
    )

if __name__ == '__main__':
    import socket
    
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "127.0.0.1"
    
    print("\n" + "="*70)
    print(" ESP32 CROWD ANALYTICS - WEB DASHBOARD (FIXED) ".center(70))
    print("="*70)
    print(f"\n📡 Serial Port: {COM_PORT}")
    print(f"🌐 Starting web server...")
    print(f"\n✅ Dashboard will be available at:")
    print(f"   Local: http://localhost:8050")
    print(f"   Network: http://{local_ip}:8050")
    print(f"\n💡 Features:")
    print(f"   ✓ Interactive charts (zoom, pan, hover)")
    print(f"   ✓ Mobile-friendly design")
    print(f"   ✓ Real-time updates every {UPDATE_INTERVAL/1000}s")
    print(f"   ✓ Device tracking table")
    print(f"   ✓ RSSI signal strength analysis")
    print(f"\n📱 Access from phone:")
    print(f"   http://{local_ip}:8050")
    print("\n" + "-"*70 + "\n")
    
    time.sleep(2)
    
    # FIXED: Changed from app.run_server() to app.run()
    app.run(debug=False, host='0.0.0.0', port=8050)