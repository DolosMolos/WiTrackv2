/*
 * ESP32 Soft AP Honeypot - Data Sender Version (FIXED)
 * Creates fake WiFi to attract smartphones, sends detection data to laptop
 * 
 * Compatible with Lolin32 Lite
 * FIXED: Removed non-existent esp_wifi_ap_get_sta_info function
 * 
 * HOW IT WORKS:
 * 1. ESP32 creates attractive open WiFi (e.g., "Free_WiFi")
 * 2. Smartphones automatically try to connect
 * 3. ESP32 captures MAC, RSSI, connection attempts
 * 4. Sends formatted data to laptop via Serial
 * 5. Python script on laptop visualizes everything
 * 
 * OUTPUT FORMAT:
 * [DEVICE] MAC:AA:BB:CC:DD:EE:FF | RSSI:-45 | STATUS:CONNECTED | IP:192.168.4.2
 * [DEVICE] MAC:11:22:33:44:55:66 | RSSI:-62 | STATUS:PROBING | IP:
 * 
 */

#include <WiFi.h>
#include "esp_wifi.h"
#include <map>
#include <string>

// ==================== SOFT AP CONFIGURATION ====================
const char* AP_SSID = "Free_WiFi";         // Attractive SSID name
const char* AP_PASSWORD = "";               // Empty = Open network
const int AP_CHANNEL = 6;
const int AP_MAX_CONNECTIONS = 20;

// Detection settings
#define RSSI_THRESHOLD -85
#define SERIAL_BAUD 115200
#define UPDATE_INTERVAL 1000  // Send updates every 1 second

// ==================== DEVICE TRACKING ====================
struct DeviceInfo {
    String mac;
    IPAddress ip;
    int rssi;
    unsigned long lastSeen;
    unsigned long firstSeen;
    int connectionAttempts;
    bool isConnected;
};

std::map<String, DeviceInfo> devices;
unsigned long lastUpdate = 0;
unsigned long totalProbes = 0;
unsigned long totalConnections = 0;

// DHCP server for IP assignment
WiFiServer server(80);

// ==================== HELPER FUNCTIONS ====================

String macToString(const uint8_t* mac) {
    char macStr[18];
    snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    return String(macStr);
}

void sendDeviceData(String mac, int rssi, String status, IPAddress ip) {
    // Format: [DEVICE] MAC:XX:XX:XX:XX:XX:XX | RSSI:-45 | STATUS:CONNECTED | IP:192.168.4.2
    Serial.printf("[DEVICE] MAC:%s | RSSI:%d | STATUS:%s | IP:%s\n",
                 mac.c_str(), rssi, status.c_str(), ip.toString().c_str());
}

void updateDevice(String mac, int rssi, bool connected, IPAddress ip = IPAddress(0,0,0,0)) {
    unsigned long now = millis();
    
    if (devices.find(mac) != devices.end()) {
        // Update existing device
        devices[mac].rssi = rssi;
        devices[mac].lastSeen = now;
        devices[mac].connectionAttempts++;
        
        if (connected && !devices[mac].isConnected) {
            devices[mac].isConnected = true;
            devices[mac].ip = ip;
            totalConnections++;
            sendDeviceData(mac, rssi, "CONNECTED", ip);
        } else if (!connected) {
            sendDeviceData(mac, rssi, "PROBING", IPAddress(0,0,0,0));
        }
    } else {
        // New device
        DeviceInfo info;
        info.mac = mac;
        info.ip = ip;
        info.rssi = rssi;
        info.lastSeen = now;
        info.firstSeen = now;
        info.connectionAttempts = 1;
        info.isConnected = connected;
        devices[mac] = info;
        
        totalProbes++;
        
        if (connected) {
            totalConnections++;
            sendDeviceData(mac, rssi, "CONNECTED", ip);
        } else {
            sendDeviceData(mac, rssi, "NEW", IPAddress(0,0,0,0));
        }
    }
}

// ==================== WIFI EVENT HANDLERS ====================

void WiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
    switch(event) {
        case ARDUINO_EVENT_WIFI_AP_STACONNECTED:
            {
                wifi_event_ap_staconnected_t* data = (wifi_event_ap_staconnected_t*) &info;
                String mac = macToString(data->mac);
                
                // Get RSSI from station list
                wifi_sta_list_t wifi_sta_list;
                esp_wifi_ap_get_sta_list(&wifi_sta_list);
                
                int rssi = -100;
                for (int i = 0; i < wifi_sta_list.num; i++) {
                    if (memcmp(wifi_sta_list.sta[i].mac, data->mac, 6) == 0) {
                        rssi = wifi_sta_list.sta[i].rssi;
                        break;
                    }
                }
                
                // IP will be assigned by DHCP, we'll update it later
                updateDevice(mac, rssi, true);
            }
            break;
            
        case ARDUINO_EVENT_WIFI_AP_STADISCONNECTED:
            {
                wifi_event_ap_stadisconnected_t* data = (wifi_event_ap_stadisconnected_t*) &info;
                String mac = macToString(data->mac);
                
                if (devices.find(mac) != devices.end()) {
                    devices[mac].isConnected = false;
                    sendDeviceData(mac, devices[mac].rssi, "DISCONNECTED", IPAddress(0,0,0,0));
                }
            }
            break;
            
        case ARDUINO_EVENT_WIFI_AP_PROBEREQRECVED:
            {
                wifi_event_ap_probe_req_rx_t* data = (wifi_event_ap_probe_req_rx_t*) &info;
                String mac = macToString(data->mac);
                int rssi = data->rssi;
                
                if (rssi >= RSSI_THRESHOLD) {
                    updateDevice(mac, rssi, false);
                }
            }
            break;
    }
}

// ==================== PROMISCUOUS MODE CAPTURE ====================
typedef struct {
    unsigned frame_ctrl:16;
    unsigned duration_id:16;
    uint8_t addr1[6];
    uint8_t addr2[6];
    uint8_t addr3[6];
    unsigned sequence_ctrl:16;
} wifi_ieee80211_mac_hdr_t;

typedef struct {
    wifi_ieee80211_mac_hdr_t hdr;
    uint8_t payload[0];
} wifi_ieee80211_packet_t;

void packet_handler(void* buff, wifi_promiscuous_pkt_type_t type) {
    if (type != WIFI_PKT_MGMT) return;
    
    const wifi_promiscuous_pkt_t *ppkt = (wifi_promiscuous_pkt_t *)buff;
    const wifi_ieee80211_packet_t *ipkt = (wifi_ieee80211_packet_t *)ppkt->payload;
    const wifi_ieee80211_mac_hdr_t *hdr = &ipkt->hdr;
    
    int rssi = ppkt->rx_ctrl.rssi;
    if (rssi < RSSI_THRESHOLD) return;
    
    uint8_t frame_type = hdr->frame_ctrl & 0xFF;
    
    if (frame_type == 0x40) {  // Probe request
        const uint8_t *mac = hdr->addr2;
        if (mac[0] != 0xFF) {
            String macStr = macToString(mac);
            updateDevice(macStr, rssi, false);
        }
    }
}

// ==================== SEND STATISTICS ====================

void sendStatistics() {
    // Send statistics in format: [STATS] CONNECTED:5 | NEARBY:12 | TOTAL_PROBES:156 | TOTAL_CONNECTS:23
    int connected = 0;
    int nearby = 0;
    
    for (const auto& pair : devices) {
        if (pair.second.isConnected) {
            connected++;
        } else {
            nearby++;
        }
    }
    
    Serial.printf("[STATS] CONNECTED:%d | NEARBY:%d | TOTAL_PROBES:%lu | TOTAL_CONNECTS:%lu\n",
                 connected, nearby, totalProbes, totalConnections);
}

// ==================== GET CONNECTED DEVICES IPs ====================

void updateConnectedDevicesIPs() {
    // Get list of connected stations
    wifi_sta_list_t wifi_sta_list;
    esp_wifi_ap_get_sta_list(&wifi_sta_list);
    
    // For each connected station, check if we can get their IP
    for (int i = 0; i < wifi_sta_list.num; i++) {
        String mac = macToString(wifi_sta_list.sta[i].mac);
        int rssi = wifi_sta_list.sta[i].rssi;
        
        if (devices.find(mac) != devices.end() && devices[mac].isConnected) {
            // Try to get IP from ARP table or DHCP lease
            // Unfortunately, there's no direct API to get client IPs in Arduino
            // We'll use the gateway IP range and check
            
            IPAddress gateway = WiFi.softAPIP();
            
            // Assign IPs sequentially based on connection order
            // This is a workaround since we can't directly query DHCP leases
            static int ip_counter = 2;
            if (devices[mac].ip == IPAddress(0,0,0,0)) {
                devices[mac].ip = IPAddress(gateway[0], gateway[1], gateway[2], ip_counter);
                ip_counter++;
                if (ip_counter > 254) ip_counter = 2;
            }
            
            devices[mac].rssi = rssi;
            devices[mac].lastSeen = millis();
        }
    }
}

// ==================== SETUP ====================

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(1000);
    
    Serial.println("\n[INIT] ESP32 Soft AP Honeypot - Data Sender");
    Serial.println("[INIT] Will send detection data to laptop via Serial");
    Serial.println("[INIT] Compatible with Lolin32 Lite\n");
    
    // Register WiFi event handler
    WiFi.onEvent(WiFiEvent);
    
    // Configure Soft AP
    Serial.printf("[AP] Creating access point: %s\n", AP_SSID);
    Serial.printf("[AP] Channel: %d\n", AP_CHANNEL);
    Serial.printf("[AP] Security: %s\n", strlen(AP_PASSWORD) > 0 ? "WPA2" : "OPEN");
    
    // Start Soft AP
    WiFi.softAP(AP_SSID, AP_PASSWORD, AP_CHANNEL, 0, AP_MAX_CONNECTIONS);
    
    // Configure IP settings
    IPAddress local_IP(192, 168, 4, 1);
    IPAddress gateway(192, 168, 4, 1);
    IPAddress subnet(255, 255, 255, 0);
    WiFi.softAPConfig(local_IP, gateway, subnet);
    
    IPAddress IP = WiFi.softAPIP();
    Serial.printf("[AP] IP Address: %s\n", IP.toString().c_str());
    Serial.printf("[AP] MAC Address: %s\n", WiFi.softAPmacAddress().c_str());
    
    // Enable promiscuous mode for extra packet capture
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_promiscuous_rx_cb(&packet_handler);
    
    Serial.println("\n[READY] Honeypot active - sending data to laptop");
    Serial.println("[INFO] Waiting for devices to connect...\n");
}

// ==================== MAIN LOOP ====================

void loop() {
    unsigned long now = millis();
    
    // Update connected devices info
    updateConnectedDevicesIPs();
    
    // Send statistics update every UPDATE_INTERVAL
    if (now - lastUpdate >= UPDATE_INTERVAL) {
        sendStatistics();
        lastUpdate = now;
    }
    
    delay(100);
}
