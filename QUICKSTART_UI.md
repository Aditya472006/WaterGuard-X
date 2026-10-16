# Quick Start — Streamlit Web UI

Get the OT Digital Twin web dashboard running in 5 minutes.

## Prerequisites

- Python 3.10+
- 500MB+ free disk space
- Modern web browser (Chrome/Firefox/Safari)

## Installation (3 steps)

### Step 1: Install Dependencies
```bash
cd ot-digital-twin
pip install -r requirements.txt
```

Takes ~2 minutes. You'll see package installations including:
- ✓ streamlit
- ✓ plotly
- ✓ tensorflow
- ✓ scikit-learn
- ✓ pandas

### Step 2: Configure Environment
```bash
# Copy example config
cp .env.example .env

# Edit .env (optional — defaults work for local demo)
# nano .env
```

Key variables (defaults should work):
```env
PLC_HOST=127.0.0.1
PLC_PORT=5020
SCADA_POLL_INTERVAL=2.0
```

### Step 3: Start Components

Open **3 separate terminals** (or tmux/screen):

**Terminal 1 — PLC Slave (Modbus Server)**:
```bash
python -m ot_twin.cli start-plc
```

Expected output:
```
Starting PLC Slave on 127.0.0.1:5020
Process: Water Treatment Plant simulation
Press Ctrl+C to stop
```

**Terminal 2 — SCADA Master (Data Collector)**:
```bash
python -m ot_twin.cli start-scada
```

Expected output:
```
SCADA connected to 127.0.0.1:5020
Polling every 2.0s. Press Ctrl+C to stop.
[Live process data displayed]
```

**Terminal 3 — Web Dashboard**:

**On Linux/Mac**:
```bash
chmod +x launch_ui.sh
./launch_ui.sh

# Or directly:
streamlit run streamlit_app.py
```

**On Windows**:
```cmd
launch_ui.bat

# Or directly:
streamlit run streamlit_app.py
```

Expected output:
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.1.x:8501
```

## Access Dashboard

Open browser: **http://localhost:8501**

You should see the **OT Digital Twin** dashboard with:
- ✓ Green status indicators (online)
- ✓ Live process charts updating
- ✓ Real-time SCADA data

## First Run Workflow

### 1. Observe Baseline (1 min)
- Stay on "🏭 SCADA HMI" tab
- Watch process variables stabilize
- All gauges should show green
- Pump/mixer running

### 2. Train ML Models (2-3 min)
Go to "⚙️ Settings" → "ML Models":
- Click "🔄 Retrain Models"
- Watch progress: Isolation Forest → LSTM
- When complete: ✅ "All models trained successfully"

### 3. Generate Attack (1 min)
Go to "🧪 Scenarios":
1. Enter attack description:
   ```
   Overflow the water tank by increasing inflow rate
   ```
2. Click "🚀 Generate Scenario"
3. Review generated attack steps
4. Review MITRE techniques mapped

### 4. Execute Attack (1 min)
Still on "🧪 Scenarios" → "Launch Attack" tab:
- Click "▶️ Execute Generated Scenario"
- Watch progress bar
- See "✅ Scenario execution complete"

### 5. Monitor Detection (1 min)
Go to "🤖 ML Detection":
- Tab 1: See anomalies detected by both methods
- Tab 2: Inspect Isolation Forest scores
- Tab 3: Check LSTM forecast deviations

Go to "🚨 Incidents":
- Red incidents appear (attack traffic)
- Flagged transactions listed
- Statistics updated

## Common Workflows

### Monitor Normal Operation
```
SCADA HMI → Analytics → Check trend charts
```

### Find What's Attacking
```
Incidents → Filter by Severity=Critical → Review details
```

### Understand Attack Techniques
```
MITRE Matrix → Click technique → See description
```

### Compare Detection Methods
```
ML Detection → Combined Analysis → Review "Confirmed by Both"
```

### Get Performance Report
```
Analytics → Select Time Range → Export or screenshot
```

## Dashboard Tour

### 🏭 SCADA HMI
**What you see**: Industrial process control panel
- Status row: 5 key metrics
- Multi-parameter chart: 3 sensor trends
- Secondary metrics: 4 detailed values

**What to do**:
- Monitor trends over time
- Check active alarms
- Track risk score (green = safe, red = critical)

### 🤖 ML Detection
**What you see**: Machine learning analysis
- Model status (Isolation Forest + LSTM loaded?)
- Anomaly score distribution charts
- Detailed anomaly log

**What to do**:
- Review high-confidence detections (red = critical)
- Inspect anomaly features (address, FC, etc.)
- Check forecast deviations

### 🚨 Incidents
**What you see**: Real-time security event log
- Color-coded severity (red/orange/yellow/green)
- Attack names, transaction details
- Timestamps

**What to do**:
- Filter by severity or type
- Review forensic details
- Trace attack progression

### 🗺️ MITRE Matrix
**What you see**: ICS attack technique grid
- Tactics as columns
- Techniques as rows
- Red = executed, Gray = not executed

**What to do**:
- Identify attack patterns
- Reference technique descriptions
- Plan defenses

### 🧪 Scenarios
**What you see**: Attack generator
- Natural language input field
- Generated attack steps
- MITRE mapping

**What to do**:
- Describe attack objective
- Review generated steps
- Execute with one click

### 📊 Analytics
**What you see**: Historical trends
- Process health charts
- Attack statistics
- Transaction analysis

**What to do**:
- Identify patterns
- Export for reporting
- Plan improvements

### ⚙️ Settings
**What you see**: Configuration panel
- ML model status
- Training controls
- System settings

**What to do**:
- Monitor model performance
- Retrain with new data
- Adjust detection thresholds

## Troubleshooting

### "No process state data available"
**Problem**: SCADA not collecting data
**Solution**:
```bash
# Check SCADA running in Terminal 2
# Should show live updates (Tank: XX%, pH: Y.Y, etc.)

# If not, restart:
# Kill Terminal 2, run again: python -m ot_twin.cli start-scada
```

### "ML models not loaded"
**Problem**: Streamlit warning in yellow box
**Solution**:
```bash
# Go to Settings → ML Models → Click "🔄 Retrain Models"
# Wait 2-3 minutes for training to complete

# Or via CLI:
python -m ot_twin.cli train-models --samples 10000
```

### Page won't load / crashes
**Problem**: Streamlit app freezes or error page
**Solution**:
```bash
# In Terminal 3:
# Press Ctrl+C

# Clear cache:
streamlit cache clear

# Restart:
streamlit run streamlit_app.py
```

### "PLC connection refused"
**Problem**: SCADA can't connect to PLC
**Solution**:
```bash
# Check Terminal 1 is running: python -m ot_twin.cli start-plc
# Should show: "Starting PLC Slave on 127.0.0.1:5020"

# Verify port not in use:
# macOS/Linux: lsof -i :5020
# Windows: netstat -ano | findstr :5020

# If in use, kill and restart
```

### Scenario generation fails
**Problem**: "Error generating scenario"
**Solution**:
```bash
# Use predefined attacks instead:
# Scenarios → Launch Attack tab → Choose from dropdown

# Or configure LLM keys in .env:
OPENROUTER_API_KEY=your_key_here
```

## Tips & Tricks

### Keyboard Shortcuts
- `r` — Restart app
- `c` — Clear cache
- `?` — Show keyboard help

### Performance Tips
- Close browser tabs (saves memory)
- Use "Manual" refresh in Analytics (vs. 30s auto-refresh)
- Reduce transaction limit when analyzing large datasets

### Data Viewing
- Hover over charts for detailed values
- Click legend items to toggle series visibility
- Drag to pan, scroll to zoom

### Exporting Results
- Screenshot charts (right-click → Save)
- Copy table data (select → Ctrl+C)
- Export via Analytics tab

## Next Steps

### After 5-Minute Tour

1. **Read Full Docs**:
   - `STREAMLIT_UI.md` — Detailed feature guide
   - `ML_INTEGRATION_GUIDE.md` — Model documentation
   - `DEPLOYMENT_SUMMARY.md` — Technical overview

2. **Try Advanced Workflows**:
   - Generate custom scenarios with natural language
   - Retrain models with production data
   - Compare attack detection methods
   - Export analytics for compliance

3. **Integrate with Your Systems**:
   - Replace PLC host/port with real device
   - Configure LLM API keys
   - Customize detection thresholds
   - Deploy to network (see deployment guide)

## Support Resources

**If something breaks**:
1. Check browser console: F12 → Console tab
2. Check terminal output: Look for red error text
3. Try clearing cache: `streamlit cache clear`
4. Review `.env` configuration
5. Restart all components

**Getting Help**:
- Check `STREAMLIT_UI.md` troubleshooting section
- Review error messages in console
- Search GitHub issues (if open source)
- Ask on security research forums

## Quick Reference

| Task | Where | How |
|------|-------|-----|
| **View live data** | SCADA HMI | Just watch — auto-updates |
| **Detect anomalies** | ML Detection | Tab 1: Combined results |
| **Find attacks** | Incidents | Filter by Red severity |
| **See techniques** | MITRE Matrix | Red = executed |
| **Generate attack** | Scenarios | Write description, click button |
| **Get statistics** | Analytics | Pick time range |
| **Train models** | Settings | Click retrain button |
| **Configure system** | Settings → System | Edit settings |

---

## Success Checklist ✓

After quick start, verify:
- [ ] PLC running (Terminal 1)
- [ ] SCADA collecting (Terminal 2)
- [ ] Dashboard accessible (http://localhost:8501)
- [ ] Charts updating live (every 2 seconds)
- [ ] ML models trained (green checkmarks)
- [ ] Attack generated successfully
- [ ] Anomalies detected in detection tab
- [ ] Incidents appear in feed

**All checked?** You're ready to explore advanced features!

---

**Total Time**: ~5 minutes
**Difficulty**: Beginner
**Next Level**: Read `STREAMLIT_UI.md` for advanced usage
