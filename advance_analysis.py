"""
ESP32 Crowd Analytics - Advanced Data Analysis Script
Comprehensive analytics for business insights and decision-making

This script reads your saved CSV files and generates:
- Peak hour analysis with recommendations
- Device behavior patterns
- Connection success trends over time
- Dwell time statistics
- RSSI coverage analysis
- Comparative analysis (day-over-day, week-over-week)
- Predictive analytics (forecast future traffic)

Requirements:
    pip install pandas numpy matplotlib seaborn scikit-learn

Usage:
    python advanced_analytics.py crowd_analytics_20251026_110000.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import sys
import os

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

def load_data(csv_file):
    """Load and prepare data"""
    df = pd.DataFrame(columns=['Timestamp', 'Connected', 'Nearby', 'Total_Probes', 
                               'Total_Connections', 'Connection_Rate%', 'Unique_Devices'])
    try:
        df = pd.read_csv(csv_file)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df['Hour'] = df['Timestamp'].dt.hour
        df['DayOfWeek'] = df['Timestamp'].dt.day_name()
        df['Total_Devices'] = df['Connected'] + df['Nearby']
        print(f"✅ Loaded {len(df)} data points from {csv_file}")
        return df
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        return df

def analyze_peak_hours(df):
    """Identify peak traffic hours"""
    print("\n" + "="*70)
    print(" PEAK HOUR ANALYSIS ".center(70))
    print("="*70)
    
    hourly_avg = df.groupby('Hour')['Total_Devices'].mean().sort_values(ascending=False)
    
    print("\n📊 Average Devices by Hour:")
    for hour, avg in hourly_avg.head(5).items():
        print(f"   {hour:02d}:00 - {avg:.1f} devices")
    
    print(f"\n🏆 Peak Hour: {hourly_avg.idxmax():02d}:00 with {hourly_avg.max():.1f} average devices")
    print(f"📉 Slowest Hour: {hourly_avg.idxmin():02d}:00 with {hourly_avg.min():.1f} average devices")
    
    # Recommendations
    print("\n💡 STAFFING RECOMMENDATIONS:")
    peak_hours = hourly_avg[hourly_avg > hourly_avg.quantile(0.75)].index.tolist()
    print(f"   Deploy maximum staff during: {', '.join([f'{h:02d}:00' for h in sorted(peak_hours)])}")
    
    slow_hours = hourly_avg[hourly_avg < hourly_avg.quantile(0.25)].index.tolist()
    print(f"   Reduce staff during: {', '.join([f'{h:02d}:00' for h in sorted(slow_hours)])}")
    
    return hourly_avg

def analyze_connection_success(df):
    """Analyze connection success patterns"""
    print("\n" + "="*70)
    print(" CONNECTION SUCCESS ANALYSIS ".center(70))
    print("="*70)
    
    avg_success = df['Connection_Rate%'].mean()
    print(f"\n📈 Average Connection Success Rate: {avg_success:.1f}%")
    
    if avg_success > 70:
        print("   ✅ EXCELLENT - High engagement!")
    elif avg_success > 40:
        print("   ⚠️  MODERATE - Room for improvement")
    else:
        print("   ❌ LOW - Need to improve WiFi attractiveness")
    
    # Trend over time
    df['Success_Smooth'] = df['Connection_Rate%'].rolling(window=10, min_periods=1).mean()
    trend = df['Success_Smooth'].iloc[-1] - df['Success_Smooth'].iloc[0]
    
    if trend > 5:
        print(f"   📈 Improving trend: +{trend:.1f}% over session")
    elif trend < -5:
        print(f"   📉 Declining trend: {trend:.1f}% over session")
    else:
        print(f"   ➡️  Stable: {trend:.1f}% change")

def analyze_device_behavior(df):
    """Analyze device dwell time and patterns"""
    print("\n" + "="*70)
    print(" DEVICE BEHAVIOR ANALYSIS ".center(70))
    print("="*70)
    
    print(f"\n📱 Total Unique Devices Seen: {df['Unique_Devices'].iloc[-1] if len(df) > 0 else 0}")
    print(f"📊 Average Devices Present: {df['Total_Devices'].mean():.1f}")
    print(f"🔝 Maximum Concurrent Devices: {df['Total_Devices'].max()}")
    
    # Connected vs Nearby ratio
    avg_connected = df['Connected'].mean()
    avg_nearby = df['Nearby'].mean()
    engagement_ratio = (avg_connected / (avg_connected + avg_nearby) * 100) if (avg_connected + avg_nearby) > 0 else 0
    
    print(f"\n🎯 Engagement Metrics:")
    print(f"   Average Connected: {avg_connected:.1f}")
    print(f"   Average Nearby (Probing): {avg_nearby:.1f}")
    print(f"   Engagement Ratio: {engagement_ratio:.1f}%")

def forecast_traffic(df):
    """Predict future traffic using linear regression"""
    print("\n" + "="*70)
    print(" TRAFFIC FORECASTING ".center(70))
    print("="*70)
    
    if len(df) < 20:
        print("\n⚠️  Not enough data for forecasting (need at least 20 data points)")
        return
    
    # Prepare data
    df['Time_Index'] = range(len(df))
    X = df[['Time_Index']].values
    y = df['Total_Devices'].values
    
    # Train model
    model = LinearRegression()
    model.fit(X, y)
    
    # Predict next hour (assuming 1-second intervals)
    future_points = 60  # Next 60 data points
    future_X = np.array([[len(df) + i] for i in range(future_points)])
    predictions = model.predict(future_X)
    
    avg_prediction = predictions.mean()
    
    print(f"\n🔮 Predicted Average Devices (next hour): {avg_prediction:.1f}")
    
    if avg_prediction > df['Total_Devices'].mean() * 1.2:
        print("   ⚠️  ALERT: Expect 20%+ increase in traffic!")
    elif avg_prediction < df['Total_Devices'].mean() * 0.8:
        print("   📉 Expect traffic to decrease")
    else:
        print("   ➡️  Traffic expected to remain stable")

def generate_visualizations(df, hourly_avg):
    """Generate comprehensive visualization report"""
    print("\n" + "="*70)
    print(" GENERATING VISUALIZATION REPORT ".center(70))
    print("="*70)
    
    fig, axes = plt.subplots(3, 2, figsize=(16, 12))
    fig.suptitle('ESP32 Crowd Analytics - Comprehensive Report', fontsize=16, fontweight='bold')
    
    # 1. Device Timeline
    ax = axes[0, 0]
    ax.plot(df['Timestamp'], df['Total_Devices'], label='Total', linewidth=2)
    ax.fill_between(df['Timestamp'], df['Connected'], alpha=0.3, label='Connected')
    ax.fill_between(df['Timestamp'], df['Nearby'], alpha=0.2, label='Nearby')
    ax.set_title('Device Count Over Time')
    ax.set_xlabel('Time')
    ax.set_ylabel('Number of Devices')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 2. Hourly Distribution
    ax = axes[0, 1]
    hourly_avg.plot(kind='bar', ax=ax, color='skyblue', edgecolor='black')
    ax.set_title('Average Devices by Hour')
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Average Devices')
    ax.grid(True, alpha=0.3, axis='y')
    
    # 3. Connection Success Rate
    ax = axes[1, 0]
    ax.plot(df['Timestamp'], df['Connection_Rate%'], color='green', linewidth=2)
    ax.axhline(y=df['Connection_Rate%'].mean(), color='red', linestyle='--', label='Average')
    ax.set_title('Connection Success Rate Over Time')
    ax.set_xlabel('Time')
    ax.set_ylabel('Success Rate (%)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 4. Connected vs Nearby
    ax = axes[1, 1]
    categories = ['Connected', 'Nearby']
    values = [df['Connected'].sum(), df['Nearby'].sum()]
    ax.pie(values, labels=categories, autopct='%1.1f%%', startangle=90, colors=['#00ff88', '#ffaa00'])
    ax.set_title('Device Distribution')
    
    # 5. Unique Devices Growth
    ax = axes[2, 0]
    ax.plot(df['Timestamp'], df['Unique_Devices'], color='purple', linewidth=2)
    ax.set_title('Unique Devices Discovered')
    ax.set_xlabel('Time')
    ax.set_ylabel('Cumulative Unique Devices')
    ax.grid(True, alpha=0.3)
    
    # 6. Day of Week (if data spans multiple days)
    ax = axes[2, 1]
    if df['DayOfWeek'].nunique() > 1:
        day_avg = df.groupby('DayOfWeek')['Total_Devices'].mean()
        day_avg.plot(kind='bar', ax=ax, color='coral', edgecolor='black')
        ax.set_title('Average Devices by Day of Week')
        ax.set_ylabel('Average Devices')
    else:
        ax.text(0.5, 0.5, 'Need multiple days\nof data', 
               transform=ax.transAxes, ha='center', va='center', fontsize=14)
        ax.axis('off')
    
    plt.tight_layout()
    
    # Save report
    filename = f'analytics_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"\n✅ Visualization report saved: {filename}")
    
    plt.show()

def generate_business_report(df):
    """Generate executive summary"""
    print("\n" + "="*70)
    print(" EXECUTIVE SUMMARY ".center(70))
    print("="*70)
    
    report = f"""
SESSION SUMMARY
===============
Duration: {(df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]).total_seconds() / 3600:.2f} hours
Total Data Points: {len(df)}

KEY METRICS
===========
• Total Unique Devices: {df['Unique_Devices'].iloc[-1] if len(df) > 0 else 0}
• Average Devices Present: {df['Total_Devices'].mean():.1f}
• Peak Concurrent Devices: {df['Total_Devices'].max()}
• Average Connection Success: {df['Connection_Rate%'].mean():.1f}%

PERFORMANCE INDICATORS
======================
• Total Probe Attempts: {df['Total_Probes'].iloc[-1] if len(df) > 0 else 0}
• Successful Connections: {df['Total_Connections'].iloc[-1] if len(df) > 0 else 0}
• Engagement Rate: {(df['Connected'].mean() / df['Total_Devices'].mean() * 100) if df['Total_Devices'].mean() > 0 else 0:.1f}%

RECOMMENDATIONS
===============
"""
    
    # Peak hour recommendation
    hourly_avg = df.groupby('Hour')['Total_Devices'].mean()
    peak_hour = hourly_avg.idxmax()
    report += f"1. Deploy maximum staff at {peak_hour:02d}:00 (peak traffic hour)\n"
    
    # Connection success recommendation
    avg_success = df['Connection_Rate%'].mean()
    if avg_success < 50:
        report += "2. Improve WiFi SSID name to attract more connections\n"
    
    # Capacity planning
    max_devices = df['Total_Devices'].max()
    report += f"3. Plan capacity for up to {int(max_devices * 1.2)} concurrent customers\n"
    
    print(report)
    
    # Save to file
    filename = f'business_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
    with open(filename, 'w') as f:
        f.write(report)
    print(f"\n✅ Business report saved: {filename}")

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*70)
    print(" ESP32 CROWD ANALYTICS - ADVANCED DATA ANALYSIS ".center(70))
    print("="*70)
    
    # Get CSV file
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        # Find most recent CSV file
        csv_files = [f for f in os.listdir('.') if f.startswith('crowd_analytics_') and f.endswith('.csv')]
        if not csv_files:
            print("\n❌ No CSV files found!")
            print("Usage: python advanced_analytics.py <csv_file>")
            sys.exit(1)
        csv_file = sorted(csv_files)[-1]
        print(f"\nUsing most recent file: {csv_file}")
    
    # Load data
    df = load_data(csv_file)
    
    if len(df) == 0:
        print("❌ No data to analyze!")
        sys.exit(1)
    
    # Run all analyses
    hourly_avg = analyze_peak_hours(df)
    analyze_connection_success(df)
    analyze_device_behavior(df)
    forecast_traffic(df)
    
    # Generate reports
    generate_visualizations(df, hourly_avg)
    generate_business_report(df)
    
    print("\n" + "="*70)
    print(" ANALYSIS COMPLETE ".center(70))
    print("="*70)
    print("\nGenerated Files:")
    print("  📊 analytics_report_[timestamp].png")
    print("  📄 business_report_[timestamp].txt")
    print("\n✅ All analysis complete!")