# Streamlit Web UI — OT Digital Twin

Professional industrial SCADA HMI dashboard with ML anomaly detection integration.

## Features

### 🏭 Live SCADA HMI & Process Charts
- Real-time multi-parameter monitoring (Tank Level, pH, Pressure)
- Synchronized time-series visualization using Plotly
- Live pump/mixer status indicators
- Active alarm display
- Process risk scoring

### 🤖 ML Anomaly Detection Engine
- **Hybrid Detection**: Combines rule-based + ML-based approaches
- **Isolation Forest**: Detects outlier transactions in multi-dimensional feature space
- **LSTM Forecasting**: Identifies temporal anomalies and process drift
- Confidence scoring and cross-validation between models
- Real-time anomaly visualization with severity coloring

### 🚨 Real-Time Incident Feed
- Live attack & anomaly log with severity filtering
- Transaction flagging and attack detection
- Incident statistics and trend analysis
- Type-based filtering (attacks, transactions, anomalies)

### 🗺️ MITRE ATT&CK Matrix View
- ICS technique mapping for all executed attacks
- Tactic-based organization
- Visual execution tracking (Red = Executed, Gray = Not Executed)
- Technique descriptions and references

### 🧪 Attack Scenario Generator
- Natural language scenario description input
- LLM-powered Modbus payload generation
- MITRE technique auto-mapping
- Step-by-step attack planning
- One-click scenario execution

### 📊 Analytics & Reporting
- Process health trending
- Attack success/failure analysis
- Transaction distribution analysis
- Alarm frequency tracking
- Function code distribution

### ⚙️ Settings & Model Management
- ML model training interface
- Sample size and hyperparameter configuration
- Model status monitoring
- Database management
- System configuration

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Verify streamlit installation
streamlit --version
```

## Quick Start

### Terminal 1: Start PLC Simulation
```bash
python -m ot_twin.cli start-plc
```

### Terminal 2: Start SCADA Master
```bash
python -m ot_twin.cli start-scada
```

### Terminal 3: Launch Streamlit Web UI
```bash
streamlit run streamlit_app.py
```

The dashboard will open at `http://localhost:8501`

## Configuration

### .env Settings
```env
# PLC Connection
PLC_HOST=127.0.0.1
PLC_PORT=5020
SCADA_POLL_INTERVAL=2.0

# LLM Configuration (for scenario generation)
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-4o

# Optional: Azure OpenAI
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
```

### Streamlit Settings (`.streamlit/config.toml`)
```toml
[theme]
primaryColor = "#10b981"
backgroundColor = "#0f172a"
secondaryBackgroundColor = "#1e293b"
textColor = "#f1f5f9"
font = "sans serif"

[logger]
level = "warning"

[client]
showErrorDetails = false
```

## Architecture

### State Management
- **Historian**: SQLite database for persistent transaction/state logging
- **Cache**: Streamlit session state for performance
- **Real-time Data**: Live polling from PLC via async Modbus client

### ML Integration
```
┌─────────────────────────────────────────────┐
│     Streamlit Web UI                        │
├─────────────────────────────────────────────┤
│  ┌──────────────────────────────────────┐   │
│  │ Enhanced Anomaly Detector            │   │
│  │  • Rule-based (AnomalyDetector)      │   │
│  │  • ML-based (MLAnomalyDetector)      │   │
│  └──────────────────────────────────────┘   │
│        ↓              ↓              ↓       │
│   Rule Engine    Isolation Forest   LSTM    │
│        ↓              ↓              ↓       │
│   Analysis Results & Visualization         │
└─────────────────────────────────────────────┘
```

### Data Flow
1. **PLC Slave**: Simulates water treatment plant
2. **SCADA Master**: Polls PLC every 2 seconds
3. **Historian**: Logs transactions, states, and attacks
4. **ML Detector**: Analyzes historian data in real-time
5. **Streamlit UI**: Visualizes results and provides controls

## Usage Workflows

### Workflow 1: Monitor Baseline Operation
1. Navigate to "🏭 SCADA HMI"
2. View live process variables
3. Monitor pump/mixer status and alarms
4. Track process risk score

### Workflow 2: Detect Anomalies with ML
1. Navigate to "🤖 ML Detection"
2. Review combined rule + ML analysis
3. Inspect Isolation Forest transaction anomalies
4. Check LSTM forecast deviations
5. Cross-validate findings between methods

### Workflow 3: Generate & Execute Attacks
1. Navigate to "🧪 Scenarios"
2. Describe attack objective in natural language
3. LLM generates step-by-step attack plan
4. Review MITRE technique mapping
5. Execute scenario with one click
6. View incident feed for forensics

### Workflow 4: Analyze & Report
1. Navigate to "📊 Analytics"
2. Select time range (Last Hour → All Time)
3. Review process health trends
4. Analyze attack success rates
5. Export data for compliance reporting

## Key Components

### Dashboard Panels

**Status Row**: 5-column layout
- Pump Status (RUNNING/STOPPED)
- Mixer Status (RUNNING/STOPPED)
- Active Alarms (count)
- Anomaly Rate (%)
- Process Risk (0-100 score)

**Multi-Parameter Chart**: Plotly dual/triple Y-axis
- Tank Level (%) — Primary axis
- pH Level — Secondary axis
- Pressure (PSI) — Tertiary axis
- Real-time updates with hover details

**Incident Feed**: Color-coded severity log
- 🔴 Critical (Red)
- 🟠 High (Orange)
- 🟡 Medium (Yellow)
- 🟢 Low (Green)

**ML Detection Tabs**:
1. **Combined Analysis**: Hybrid results, severity breakdown
2. **Isolation Forest**: Transaction outlier visualization
3. **LSTM Forecasting**: Sensor prediction vs. actual

### Controls

**Attack Launcher**:
- Scenario generator with LLM integration
- Predefined attack selector
- Target address & register count inputs
- Duration & intensity sliders
- Confirmation-guarded execution

**Model Management**:
- Training sample size configuration
- LSTM epoch tuning
- Model status display
- One-click retraining

## Performance Notes

### Data Limits
- Recent transactions: 500-2000 (configurable)
- Process states: 500-1000 (configurable)
- Attack history: 50-100 (configurable)
- Incident feed: 30-100 (configurable)

### Rendering Performance
- Charts auto-resize to container width
- Template: `plotly_dark` for consistency
- Caching enabled for historian/detector instances
- Lazy loading for analytics tabs

### ML Model Performance
- Isolation Forest: <100ms inference on 500 transactions
- LSTM: <500ms for 10-step forecast
- Combined analysis: <2s for full detection cycle

## Troubleshooting

### Models Not Loading
```bash
# Train models from CLI
python -m ot_twin.cli train-models --samples 10000

# Or use web UI: Settings → ML Models → Retrain
```

### PLC Connection Failed
```bash
# Verify PLC is running
ps aux | grep start-plc

# Check port availability
netstat -an | grep 5020

# Restart with explicit host/port
python -m ot_twin.cli start-plc --host 127.0.0.1 --port 5020
```

### Streamlit Issues
```bash
# Clear cache
streamlit cache clear

# Run with debug logging
streamlit run streamlit_app.py --logger.level=debug
```

### High CPU/Memory Usage
- Reduce data limits in Analytics tab
- Increase refresh interval (manual → 5m)
- Close browser tabs
- Restart Streamlit process

## Development Notes

### Adding New Visualizations
```python
# In render_<component>() function:
fig = px.line(df, x='timestamp', y='value', title='Title')
fig.update_layout(
    template="plotly_dark",
    paper_bgcolor='#0f172a',
    plot_bgcolor='#1e293b',
    font=dict(color='#f1f5f9'),
    height=350
)
st.plotly_chart(fig, use_container_width=True)
```

### Custom CSS Classes
```html
<div class="alert-box" style="border-left-color: #ef4444;">
    <strong>Alert Title</strong>
    Alert message
</div>
```

### Caching Best Practices
```python
@st.cache_resource
def get_historian():
    return Historian()  # Singleton instance

@st.cache_data(ttl=60)
def get_recent_data():
    return historian.get_recent_transactions(500)
```

## Security Notes

⚠️ **This is a security research tool. Do not use in production without proper hardening:**
- No authentication/authorization implemented
- All Modbus operations are unencrypted
- Web UI accessible on local network
- No rate limiting or request validation

For production deployments:
- Add authentication layer
- Implement TLS/HTTPS
- Add input validation and sanitization
- Use read-only database replicas
- Implement audit logging

## License

MIT — Same as main project

## Support

For issues and questions:
1. Check `.env` configuration
2. Verify all dependencies installed: `pip install -r requirements.txt`
3. Review console output for error messages
4. Test individual components via CLI first
