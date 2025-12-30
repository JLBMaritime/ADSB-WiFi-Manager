# ADS-B Output Modes Implementation Guide

## ✅ What's Been Completed

### Frontend (100% Complete)
- ✅ **index.html**: Added Output Format section with 3 radio buttons + explanations
- ✅ **main.js**: Added `toggleOutputFormat()`, updated `loadADSBConfig()` and `saveADSBConfig()` to handle output_format
- ✅ **UI**: Users can now select: SBS1, JSON, or JSON→SBS1

### Backend (100% Complete)  
- ✅ **app.py**: 
  - `get_adsb_config()` returns `output_format`
  - `update_adsb_config()` saves `output_format` to config
  - Default config creates `[Output]` section with `format = sbs1`

### What Remains
- ⏳ **adsb_server.py**: Implement the 3 output modes (this document)

---

## 📋 Implementation Overview

### Current State
The current `adsb_server.py` only supports **SBS1 mode** from port 30003.

### Required Changes
Add support for 3 output modes based on `config['Output']['format']`:

1. **SBS1** (`sbs1`) - Enhanced with altitude state tracking
2. **JSON** (`json`) - Poll JSON port, send individual JSON objects  
3. **JSON→SBS1** (`json_to_sbs1`) - Poll JSON, convert to SBS1 output

---

## 🔧 Mode 1: SBS1 with State Tracking

### Purpose
Real-time SBS1 streaming WITH altitude state tracking to fix incomplete message filtering.

### Changes Needed

#### 1. Add Aircraft State Tracking
```python
class ADSBServer:
    def __init__(self, config_file):
        # ... existing code ...
        self.aircraft_states = {}  # NEW: Track aircraft altitude

def update_aircraft_state(self, icao, altitude):
    """Update tracked aircraft altitude"""
    if altitude:
        self.aircraft_states[icao] = {
            'altitude': altitude,
            'last_seen': time.time()
        }

def cleanup_old_aircraft(self):
    """Remove aircraft not seen in 5 minutes"""
    current_time = time.time()
    to_remove = [icao for icao, state in self.aircraft_states.items()
                 if current_time - state['last_seen'] > 300]
    for icao in to_remove:
        del self.aircraft_states[icao]
```

#### 2. Update filter_message()
```python
def filter_message(self, message):
    """Check if message should be forwarded based on filter"""
    try:
        parts = message.split(',')
        
        # Extract ICAO
        icao = parts[4].strip().upper() if len(parts) > 4 else None
        
        # Extract altitude if present
        altitude_str = parts[11].strip() if len(parts) > 11 else ''
        current_altitude = None
        if altitude_str:
            try:
                current_altitude = int(altitude_str)
                # Update state tracking
                if icao:
                    self.update_aircraft_state(icao, current_altitude)
            except ValueError:
                pass
        
        # Get tracked altitude if current message doesn't have it
        if not current_altitude and icao and icao in self.aircraft_states:
            current_altitude = self.aircraft_states[icao]['altitude']
        
        # Check altitude filter
        if self.altitude_filter_enabled and current_altitude:
            if current_altitude > self.max_altitude:
                return False  # Reject aircraft above max altitude
        
        # Check ICAO filter
        if self.filter_all:
            return True
        
        if icao:
            return icao in self.filter_icao_list
                
    except:
        pass
        
    return False
```

#### 3. Add Periodic Cleanup
```python
def run(self):
    """Main server loop"""
    self.running = True
    self.logger.info("ADS-B Server starting in SBS1 mode...")
    
    last_cleanup = time.time()
    
    while self.running:
        # ... existing connection code ...
        
        try:
            while self.running:
                # Cleanup old aircraft every 60 seconds
                if time.time() - last_cleanup > 60:
                    self.cleanup_old_aircraft()
                    last_cleanup = time.time()
                
                # ... rest of existing code ...
```

---

## 🔧 Mode 2: JSON Objects

### Purpose
Poll JSON port (30047), send individual JSON objects per aircraft.

### Implementation

#### 1. Add JSON Polling Function
```python
import json
import urllib.request

def fetch_json_data(self):
    """Fetch JSON data from dump1090"""
    try:
        host = self.config.get('Dump1090', 'host', fallback='127.0.0.1')
        json_port = self.config.getint('Dump1090', 'json_port', fallback=30047)
        
        url = f"http://{host}:{json_port}/data/aircraft.json"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('aircraft', [])
    except Exception as e:
        self.logger.error(f"Error fetching JSON: {e}")
        return []
```

#### 2. Add JSON Filtering
```python
def filter_json_aircraft(self, aircraft):
    """Filter JSON aircraft object"""
    try:
        icao = aircraft.get('hex', '').upper()
        altitude = aircraft.get('alt_baro') or aircraft.get('alt_geom')
        
        # Check altitude filter
        if self.altitude_filter_enabled and altitude:
            if altitude > self.max_altitude:
                return False
        
        # Check ICAO filter
        if self.filter_all:
            return True
        
        return icao in self.filter_icao_list
    except:
        return False
```

#### 3. Add JSON Mode Run Loop
```python
def run_json_mode(self):
    """Run in JSON polling mode"""
    self.logger.info("ADS-B Server starting in JSON mode...")
    
    while self.running:
        # Connect to endpoints
        self.connect_to_endpoints()
        
        try:
            while self.running:
                # Reload config periodically
                if time.time() - reconnect_time > 30:
                    self.load_config()
                    reconnect_time = time.time()
                
                # Fetch JSON data
                aircraft_list = self.fetch_json_data()
                
                # Filter and forward each aircraft
                for aircraft in aircraft_list:
                    if self.filter_json_aircraft(aircraft):
                        # Send as individual JSON object
                        json_str = json.dumps(aircraft) + '\n'
                        self.forward_message(json_str)
                
                # Poll every 1 second
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"JSON mode error: {e}")
            time.sleep(5)
```

---

## 🔧 Mode 3: JSON→SBS1 Hybrid

### Purpose
Poll JSON (complete data) but convert to SBS1 format for compatibility.

### Implementation

#### 1. Add JSON to SBS1 Converter
```python
from datetime import datetime

def json_to_sbs1(self, aircraft):
    """Convert JSON aircraft object to SBS1 format"""
    try:
        icao = aircraft.get('hex', '').upper()
        callsign = aircraft.get('flight', '').strip()
        altitude = aircraft.get('alt_baro') or aircraft.get('alt_geom') or ''
        speed = aircraft.get('gs') or ''
        track = aircraft.get('track') or ''
        lat = aircraft.get('lat') or ''
        lon = aircraft.get('lon') or ''
        
        # Get current timestamp
        now = datetime.utcnow()
        date_str = now.strftime('%Y/%m/%d')
        time_str = now.strftime('%H:%M:%S.%f')[:-3]
        
        # SBS1 format: MSG,3,sessionID,aircraftID,ICAO,flightID,date,time,date,time,callsign,altitude,speed,track,lat,lon...
        sbs1_line = f"MSG,3,1,1,{icao},1,{date_str},{time_str},{date_str},{time_str},{callsign},{altitude},{speed},{track},{lat},{lon}"
        
        return sbs1_line + '\n'
    except Exception as e:
        self.logger.error(f"JSON→SBS1 conversion error: {e}")
        return None
```

#### 2. Add JSON→SBS1 Mode Run Loop
```python
def run_json_to_sbs1_mode(self):
    """Run in JSON→SBS1 conversion mode"""
    self.logger.info("ADS-B Server starting in JSON→SBS1 mode...")
    
    while self.running:
        # Connect to endpoints
        self.connect_to_endpoints()
        
        reconnect_time = time.time()
        
        try:
            while self.running:
                # Reload config periodically
                if time.time() - reconnect_time > 30:
                    self.load_config()
                    reconnect_time = time.time()
                
                # Fetch JSON data
                aircraft_list = self.fetch_json_data()
                
                # Filter and convert each aircraft
                for aircraft in aircraft_list:
                    if self.filter_json_aircraft(aircraft):
                        # Convert to SBS1 and send
                        sbs1_message = self.json_to_sbs1(aircraft)
                        if sbs1_message:
                            self.forward_message(sbs1_message)
                
                # Poll every 1 second
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"JSON→SBS1 mode error: {e}")
            time.sleep(5)
```

---

## 🔀 Main run() Switch Logic

### Update run() Method

```python
def run(self):
    """Main server loop - routes to appropriate mode"""
    self.running = True
    
    # Determine output format
    output_format = self.config.get('Output', 'format', fallback='sbs1')
    
    self.logger.info(f"Starting ADS-B Server in {output_format} mode")
    
    # Route to appropriate mode
    if output_format == 'json':
        self.run_json_mode()
    elif output_format == 'json_to_sbs1':
        self.run_json_to_sbs1_mode()
    else:  # Default to sbs1
        self.run_sbs1_mode()  # Rename existing run() logic to this
```

---

## 📝 Configuration File Changes

### Update create_default_config()

```python
def create_default_config(self):
    """Create default configuration file"""
    self.config['Dump1090'] = {
        'host': '127.0.0.1',
        'sbs1_port': '30003',
        'json_port': '30047'
    }
    self.config['Output'] = {
        'format': 'sbs1'  # or 'json' or 'json_to_sbs1'
    }
    self.config['Filter'] = {
        'mode': 'specific',
        'icao_list': 'A92F2D,A932E4,A9369B,A93A52',
        'altitude_filter_enabled': 'false',
        'max_altitude': '10000'
    }
    self.config['Endpoints'] = {
        'count': '0'
    }
    
    with open(self.config_file, 'w') as f:
        self.config.write(f)
```

---

## 🧪 Testing Each Mode

### Test SBS1 Mode
1. Set Output Format to "SBS1 Streaming" in web UI
2. Save Configuration
3. Run Windows listener
4. Monitor for aircraft data with state tracking
5. Verify altitude filter works even with incomplete messages

### Test JSON Mode
1. Set Output Format to "JSON Objects" in web UI  
2. Save Configuration
3. Update Windows listener to handle JSON:
   ```python
   data = json.loads(line)
   print(f"ICAO: {data.get('hex')}, Alt: {data.get('alt_baro')}")
   ```
4. Verify individual JSON objects received

### Test JSON→SBS1 Mode
1. Set Output Format to "JSON→SBS1 Hybrid" in web UI
2. Save Configuration
3. Run Windows listener (expects SBS1 format)
4. Verify data is SBS1 format but has complete altitude data
5. Altitude filter should work perfectly

---

## 🚀 Deployment Steps

1. **Backup Current adsb_server.py**
   ```bash
   cp ~/ADSB-WiFi-Manager/adsb_server/adsb_server.py ~/adsb_server.py.backup
   ```

2. **Update adsb_server.py** with all 3 modes

3. **Test Locally** on Raspberry Pi

4. **Push to GitHub**
   ```bash
   cd ~/ADSB-WiFi-Manager
   git add .
   git commit -m "Add 3 output modes: SBS1, JSON, JSON→SBS1"
   git push origin main
   ```

5. **Restart Service**
   ```bash
   sudo systemctl restart adsb-server
   sudo systemctl restart web-manager
   ```

---

## 📊 Summary

### What Each Mode Provides

| Mode | Source | Output | Altitude Filter | Best For |
|------|--------|--------|-----------------|----------|
| **SBS1** | Port 30003 | SBS1 text | ✅ With state tracking | Existing systems, real-time |
| **JSON** | Port 30047 | Individual JSON | ✅ Complete data | Modern apps, easier parsing |
| **JSON→SBS1** | Port 30047 | Converted SBS1 | ✅ Perfect filtering | Best of both worlds |

### Files Modified
- ✅ `index.html` - UI for mode selection
- ✅ `main.js` - Frontend handling
- ✅ `app.py` - Backend config save/load
- ⏳ `adsb_server.py` - Core implementation (use this guide)

**Estimated Implementation Time:** 2-3 hours

**Ready to implement? Follow this guide section by section!** 🎯
