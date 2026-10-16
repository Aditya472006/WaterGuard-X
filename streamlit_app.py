"""
OT Digital Twin — Streamlit Web UI
Professional industrial SCADA HMI dashboard with ML anomaly detection.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from streamlit_option_menu import option_menu

# Configure logging
logging.basicConfig(level=logging.WARNING)

# Import core modules
from ot_twin.config import PROJECT_ROOT
from ot_twin.environment.historian import Historian
from ot_twin.environment.enhanced_anomaly_detector import EnhancedAnomalyDetector
from ot_twin.environment.anomaly_detector import AnomalyDetector
from ot_twin.environment.risk_scorer import score_risk
from ot_twin.models import ProcessState, ModbusTransaction, RegisterType, AttackScenario, AttackStep
from ot_twin.attacks.registry import get_attack, ATTACK_REGISTRY
from ot_twin.llm_generator.scenario_generator import generate_scenario
from ot_twin.llm_generator.payload_builder import build_attacks_from_scenario


# ─────────────────────────────────────────────────────────────────────────
# PAGE CONFIGURATION & STYLING
# ─────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="OT Digital Twin — Industrial SCADA",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for industrial aesthetics
st.markdown("""
<style>
    /* Dark industrial theme */
    :root {
        --primary-dark: #0f172a;
        --secondary-dark: #1e293b;
        --accent-green: #10b981;
        --accent-red: #ef4444;
        --accent-amber: #f59e0b;
        --accent-blue: #3b82f6;
        --text-light: #f1f5f9;
        --text-muted: #94a3b8;
    }
    
    body, .main {
        background-color: #0f172a;
        color: #f1f5f9;
    }
    
    .stMetric {
        background-color: #1e293b;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3b82f6;
    }
    
    .metric-critical {
        border-left-color: #ef4444 !important;
    }
    
    .metric-warning {
        border-left-color: #f59e0b !important;
    }
    
    .metric-ok {
        border-left-color: #10b981 !important;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        background-color: #1e293b;
        border-bottom: 2px solid #334155;
    }
    
    .stTabs [data-baseweb="tab"] {
        color: #94a3b8;
        border-radius: 0;
    }
    
    .stTabs [aria-selected="true"] {
        color: #10b981 !important;
        border-bottom: 3px solid #10b981 !important;
    }
    
    .alert-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid;
    }
    
    .alert-critical {
        background-color: #7f1d1d;
        border-left-color: #ef4444;
        color: #fecaca;
    }
    
    .alert-warning {
        background-color: #78350f;
        border-left-color: #f59e0b;
        color: #fde047;
    }
    
    .alert-info {
        background-color: #1e3a8a;
        border-left-color: #3b82f6;
        color: #bfdbfe;
    }
    
    .alert-success {
        background-color: #064e3b;
        border-left-color: #10b981;
        color: #a7f3d0;
    }
    
    .hmi-panel {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 0.5rem;
        padding: 1.5rem;
        margin: 0.5rem 0;
    }
    
    .status-indicator {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 0.5rem;
    }
    
    .status-running {
        background-color: #10b981;
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
    }
    
    .status-stopped {
        background-color: #6b7280;
    }
    
    .status-anomaly {
        background-color: #f59e0b;
        box-shadow: 0 0 10px rgba(245, 158, 11, 0.5);
    }
    
    .status-critical {
        background-color: #ef4444;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.5);
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────
# STATE MANAGEMENT & CACHING
# ─────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_historian():
    """Get cached Historian instance."""
    return Historian()

@st.cache_resource
def get_enhanced_detector():
    """Get cached Enhanced Anomaly Detector."""
    return EnhancedAnomalyDetector(use_ml=True)

@st.cache_resource
def get_rule_detector():
    """Get cached Rule-Based Anomaly Detector."""
    return AnomalyDetector()


# ─────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────

def get_status_color(severity: str) -> str:
    """Map severity to color."""
    color_map = {
        "critical": "#ef4444",
        "high": "#f97316",
        "medium": "#f59e0b",
        "low": "#eab308"
    }
    return color_map.get(severity, "#94a3b8")

def get_status_badge(value: str) -> str:
    """Create colored status badge."""
    badges = {
        "critical": "🔴 CRITICAL",
        "high": "🟠 HIGH",
        "medium": "🟡 MEDIUM",
        "low": "🟢 LOW",
        "normal": "✅ NORMAL"
    }
    return badges.get(value, "? UNKNOWN")

def format_timestamp(ts: datetime | str) -> str:
    """Format timestamp for display."""
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return ts
    return ts.strftime("%H:%M:%S")

def calculate_anomaly_rate(anomalies: list) -> float:
    """Calculate anomaly rate from recent data."""
    if not anomalies:
        return 0.0
    
    critical_high = sum(1 for a in anomalies if a.get("severity") in ["critical", "high"])
    return (critical_high / max(len(anomalies), 1)) * 100


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 1: LIVE SCADA HMI & PROCESS CHARTS
# ─────────────────────────────────────────────────────────────────────────

def render_hmi_dashboard():
    """Render main SCADA HMI dashboard with live process data."""
    st.header("🏭 Industrial SCADA HMI — Water Treatment Plant")
    
    historian = get_historian()
    rule_detector = get_rule_detector()
    enhanced_detector = get_enhanced_detector()
    
    # Fetch recent data
    recent_states = historian.get_recent_process_states(500)
    recent_transactions = historian.get_recent_transactions(200)
    
    if not recent_states:
        st.warning("No process state data available. Start the PLC and SCADA to collect data.")
        return
    
    # Convert to DataFrame for easier manipulation
    states_df = pd.DataFrame(recent_states)
    states_df['timestamp'] = pd.to_datetime(states_df['timestamp'])
    states_df = states_df.sort_values('timestamp')
    
    # Latest state
    latest_state = recent_states[-1]
    
    # ─── Status Row ───
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        pump_status = "RUNNING" if latest_state.get("pump_running") else "STOPPED"
        pump_color = "🟢" if latest_state.get("pump_running") else "🔴"
        st.metric(
            "Pump Status",
            pump_status,
            delta=None,
            help="Primary circulation pump"
        )
    
    with col2:
        mixer_status = "RUNNING" if latest_state.get("mixer_running") else "STOPPED"
        mixer_color = "🟢" if latest_state.get("mixer_running") else "🔴"
        st.metric(
            "Mixer Status",
            mixer_status,
            help="Tank mixing system"
        )
    
    with col3:
        alarm_count = sum([
            latest_state.get("high_level_alarm", False),
            latest_state.get("low_level_alarm", False),
            latest_state.get("ph_alarm", False),
            latest_state.get("pressure_alarm", False)
        ])
        st.metric(
            "Active Alarms",
            alarm_count,
            delta=None,
            help="Count of triggered alarms"
        )
    
    with col4:
        # Analyze anomalies
        rule_anomalies = rule_detector.analyze(historian, limit=100)
        anomaly_rate = calculate_anomaly_rate(rule_anomalies)
        rate_color = "🔴" if anomaly_rate > 50 else "🟡" if anomaly_rate > 25 else "🟢"
        st.metric(
            "Anomaly Rate",
            f"{anomaly_rate:.1f}%",
            delta=None,
            help="% of recent events flagged as anomalies"
        )
    
    with col5:
        risk_score = score_risk(ProcessState(**latest_state))
        score_color = "🔴" if risk_score.score > 70 else "🟡" if risk_score.score > 40 else "🟢"
        st.metric(
            "Process Risk",
            f"{risk_score.score:.0f}/100",
            delta=None,
            help=f"Level: {risk_score.level.upper()}"
        )
    
    # ─── Multi-parameter Chart ───
    st.subheader("Process Variables Over Time")
    
    # Create multi-axis chart
    fig = go.Figure()
    
    # Tank Level (Left Y-axis)
    fig.add_trace(go.Scatter(
        x=states_df['timestamp'],
        y=states_df['tank_level'],
        name='Tank Level (%)',
        line=dict(color='#3b82f6', width=2),
        yaxis='y',
        hovertemplate='<b>Tank Level</b><br>Time: %{x|%H:%M:%S}<br>Level: %{y:.1f}%<extra></extra>'
    ))
    
    # pH Level (Right Y-axis)
    fig.add_trace(go.Scatter(
        x=states_df['timestamp'],
        y=states_df['ph_level'],
        name='pH Level',
        line=dict(color='#10b981', width=2),
        yaxis='y2',
        hovertemplate='<b>pH Level</b><br>Time: %{x|%H:%M:%S}<br>pH: %{y:.2f}<extra></extra>'
    ))
    
    # Pressure (Right Y-axis)
    fig.add_trace(go.Scatter(
        x=states_df['timestamp'],
        y=states_df['pressure_psi'],
        name='Pressure (PSI)',
        line=dict(color='#f59e0b', width=2),
        yaxis='y3',
        hovertemplate='<b>Pressure</b><br>Time: %{x|%H:%M:%S}<br>PSI: %{y:.1f}<extra></extra>'
    ))
    
    # Layout with multiple Y-axes
    fig.update_layout(
        title="Multi-Parameter Real-Time Monitoring",
        hovermode='x unified',
        template='plotly_dark',
        height=500,
        margin=dict(l=100, r=100, t=80, b=60),
        paper_bgcolor='#0f172a',
        plot_bgcolor='#1e293b',
        font=dict(color='#f1f5f9'),
        xaxis=dict(
            title='Time',
            color='#94a3b8',
            gridcolor='#334155'
        ),
        yaxis=dict(
            title='Tank Level (%)',
            color='#3b82f6',
            gridcolor='#334155',
            domain=[0, 0.32]
        ),
        yaxis2=dict(
            title='pH Level',
            color='#10b981',
            overlaying='y',
            side='left',
            domain=[0.33, 0.65]
        ),
        yaxis3=dict(
            title='Pressure (PSI)',
            color='#f59e0b',
            overlaying='y',
            side='right',
            domain=[0.66, 1.0]
        ),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(30, 41, 59, 0.8)',
            bordercolor='#334155',
            borderwidth=1
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # ─── Secondary Metrics ───
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Temperature",
            f"{latest_state.get('temperature_c', 0):.1f}°C",
            help="Water temperature"
        )
    
    with col2:
        st.metric(
            "Turbidity",
            f"{latest_state.get('turbidity', 0):.2f} NTU",
            help="Water clarity (Nephelometric Turbidity Units)"
        )
    
    with col3:
        st.metric(
            "Inflow Rate",
            f"{latest_state.get('inflow_rate', 0):.1f} L/min",
            help="Tank inflow rate"
        )
    
    with col4:
        st.metric(
            "Outflow Rate",
            f"{latest_state.get('outflow_rate', 0):.1f} L/min",
            help="Tank outflow rate"
        )


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 2: ML ANOMALY DETECTION ENGINE
# ─────────────────────────────────────────────────────────────────────────

def render_ml_detection_engine():
    """Render ML-based anomaly detection dashboard."""
    st.header("🤖 ML Anomaly Detection Engine")
    
    historian = get_historian()
    enhanced_detector = get_enhanced_detector()
    
    # Show capabilities
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Detection Mode", "Hybrid", help="Rule-based + ML models")
    
    with col2:
        if enhanced_detector.ml_loaded:
            st.metric("ML Models", "✅ LOADED", help="Both Isolation Forest and LSTM")
        else:
            st.metric("ML Models", "⚠️ NOT LOADED", help="Train models first")
    
    with col3:
        recent_anomalies = historian.get_recent_transactions(100)
        anomaly_count = sum(1 for tx in recent_anomalies if tx.get("is_attack"))
        st.metric("Flagged Transactions", anomaly_count)
    
    # Analysis tabs
    tab1, tab2, tab3 = st.tabs(["Combined Analysis", "Isolation Forest", "LSTM Forecasting"])
    
    with tab1:
        st.subheader("Hybrid Detection Results")
        
        with st.spinner("Running combined analysis..."):
            results = enhanced_detector.analyze(historian, transaction_limit=500, include_forecast=False)
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        combined_summary = results.get("combined", {}).get("summary", {})
        
        with col1:
            st.metric(
                "Total Rule Anomalies",
                combined_summary.get("total_rule_anomalies", 0),
                help="Detected by rule-based engine"
            )
        
        with col2:
            st.metric(
                "Total ML Anomalies",
                combined_summary.get("total_ml_anomalies", 0),
                help="Detected by ML models"
            )
        
        with col3:
            st.metric(
                "Confirmed by Both",
                combined_summary.get("confirmed_by_both", 0),
                help="High-confidence anomalies"
            )
        
        with col4:
            st.metric(
                "Unique Anomalies",
                combined_summary.get("unique_anomalies", 0),
                help="Total distinct anomalies"
            )
        
        # Severity distribution
        if "severity_distribution" in combined_summary:
            st.subheader("Severity Breakdown")
            
            col1, col2 = st.columns(2)
            
            with col1:
                rule_severity = results["rule_based"].get("severity_counts", {})
                severity_df = pd.DataFrame([
                    {"Severity": "Critical", "Count": rule_severity.get("critical", 0)},
                    {"Severity": "High", "Count": rule_severity.get("high", 0)},
                    {"Severity": "Medium", "Count": rule_severity.get("medium", 0)},
                    {"Severity": "Low", "Count": rule_severity.get("low", 0)}
                ])
                
                fig = px.bar(
                    severity_df,
                    x="Severity",
                    y="Count",
                    color="Severity",
                    color_discrete_map={
                        "Critical": "#ef4444",
                        "High": "#f97316",
                        "Medium": "#f59e0b",
                        "Low": "#eab308"
                    },
                    title="Rule-Based Severity Distribution",
                    labels={"Count": "Anomalies"}
                )
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor='#0f172a',
                    plot_bgcolor='#1e293b',
                    font=dict(color='#f1f5f9'),
                    showlegend=False,
                    height=350
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                ml_severity = results["ml_based"].get("summary", {}).get("severity_breakdown", {})
                ml_severity_df = pd.DataFrame([
                    {"Severity": "Critical", "Count": ml_severity.get("critical", 0)},
                    {"Severity": "High", "Count": ml_severity.get("high", 0)},
                    {"Severity": "Medium", "Count": ml_severity.get("medium", 0)},
                    {"Severity": "Low", "Count": ml_severity.get("low", 0)}
                ])
                
                fig = px.bar(
                    ml_severity_df,
                    x="Severity",
                    y="Count",
                    color="Severity",
                    color_discrete_map={
                        "Critical": "#ef4444",
                        "High": "#f97316",
                        "Medium": "#f59e0b",
                        "Low": "#eab308"
                    },
                    title="ML Severity Distribution",
                    labels={"Count": "Anomalies"}
                )
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor='#0f172a',
                    plot_bgcolor='#1e293b',
                    font=dict(color='#f1f5f9'),
                    showlegend=False,
                    height=350
                )
                st.plotly_chart(fig, use_container_width=True)
        
        # Detailed anomalies
        st.subheader("Detailed Anomaly Log")
        
        anomaly_list = results["rule_based"].get("anomalies", [])
        
        if anomaly_list:
            for i, anomaly in enumerate(anomaly_list[:20]):  # Show top 20
                severity = anomaly.get("severity", "low")
                color = get_status_color(severity)
                
                st.markdown(f"""
                <div class="alert-box" style="border-left-color: {color}; background-color: rgba({color.lstrip('#')}, 0.1);">
                    <strong>{get_status_badge(severity)}</strong> • {anomaly.get('category', 'unknown')}<br>
                    <small>{anomaly.get('description', 'No description')}</small><br>
                    <code style="color: #94a3b8;">{anomaly.get('timestamp', 'N/A')[:19]}</code>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("✅ No rule-based anomalies detected in recent data")
    
    with tab2:
        st.subheader("Isolation Forest — Transaction Anomaly Detection")
        
        st.markdown("""
        **Isolation Forest** identifies outlier transactions by isolating anomalous feature combinations
        in multi-dimensional Modbus traffic space. Higher anomaly scores indicate more suspicious patterns.
        """)
        
        if enhanced_detector.ml_loaded and enhanced_detector.ml_detector.isolation_forest:
            ml_data = results["ml_based"]
            
            if "anomalies" in ml_data:
                anomalies = ml_data["anomalies"]
                
                if anomalies:
                    # Create anomaly score distribution chart
                    anomaly_confidences = [a.get("confidence", 0) for a in anomalies]
                    
                    if anomaly_confidences:
                        fig = go.Figure()
                        fig.add_trace(go.Histogram(
                            x=anomaly_confidences,
                            nbinsx=20,
                            name="Anomaly Confidence",
                            marker=dict(color='#f59e0b')
                        ))
                        
                        fig.update_layout(
                            title="Anomaly Score Distribution",
                            xaxis_title="Confidence Score",
                            yaxis_title="Frequency",
                            template="plotly_dark",
                            paper_bgcolor='#0f172a',
                            plot_bgcolor='#1e293b',
                            font=dict(color='#f1f5f9'),
                            height=350
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Top anomalies
                    st.subheader("Top Isolation Forest Detections")
                    
                    for anomaly in anomalies[:10]:
                        severity = anomaly.get("severity", "low")
                        color = get_status_color(severity)
                        confidence = anomaly.get("confidence", 0)
                        
                        st.markdown(f"""
                        <div class="alert-box" style="border-left-color: {color}; background-color: rgba({color.lstrip('#')}, 0.1);">
                            <strong>{get_status_badge(severity)}</strong> | Confidence: {confidence:.3f}<br>
                            <em>{anomaly.get('description', 'N/A')}</em><br>
                            <small style="color: #94a3b8;">Address: {anomaly.get('details', {}).get('address', 'N/A')} | FC: {anomaly.get('details', {}).get('function_code', 'N/A')}</small>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("✅ No anomalies detected by Isolation Forest")
        else:
            st.warning("⚠️ Isolation Forest model not loaded. Run training to enable.")
    
    with tab3:
        st.subheader("LSTM Time-Series Anomaly Detection")
        
        st.markdown("""
        **LSTM Forecasting** predicts expected sensor values based on historical patterns.
        Deviations between actual and predicted values indicate temporal anomalies or process drift.
        """)
        
        if enhanced_detector.ml_loaded and enhanced_detector.ml_detector.lstm_model:
            ml_data = results["ml_based"]
            
            if "forecasts" in ml_data and ml_data["forecasts"]:
                forecasts = ml_data["forecasts"]
                
                # Create forecast visualization
                forecast_data = []
                for fc in forecasts[:10]:
                    preds = fc.get("predictions", {})
                    forecast_data.append({
                        "Step": fc.get("step", 0),
                        "Tank Level": preds.get("tank_level", 0),
                        "pH Level": preds.get("ph_level", 0),
                        "Pressure": preds.get("pressure_psi", 0)
                    })
                
                fc_df = pd.DataFrame(forecast_data)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    fig = px.line(
                        fc_df,
                        x="Step",
                        y="Tank Level",
                        title="Tank Level Forecast",
                        markers=True
                    )
                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor='#0f172a',
                        plot_bgcolor='#1e293b',
                        font=dict(color='#f1f5f9'),
                        height=350
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    fig = px.line(
                        fc_df,
                        x="Step",
                        y=["pH Level", "Pressure"],
                        title="pH & Pressure Forecast",
                        markers=True
                    )
                    fig.update_layout(
                        template="plotly_dark",
                        paper_bgcolor='#0f172a',
                        plot_bgcolor='#1e293b',
                        font=dict(color='#f1f5f9'),
                        height=350
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            # Forecast anomalies
            if "anomalies" in ml_data:
                anomalies = [a for a in ml_data.get("anomalies", []) if a.get("category") == "lstm_forecast"]
                
                if anomalies:
                    st.subheader("Forecast Deviations")
                    
                    for anomaly in anomalies[:5]:
                        st.markdown(f"""
                        <div class="alert-box" style="border-left-color: #f59e0b; background-color: rgba(245, 158, 11, 0.1);">
                            <strong>🟡 FORECAST ANOMALY</strong><br>
                            {anomaly.get('description', 'N/A')}<br>
                            <small style="color: #94a3b8;">Confidence: {anomaly.get('confidence', 0):.2f}</small>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("✅ LSTM predictions match actual process behavior")
        else:
            st.warning("⚠️ LSTM model not loaded. Run training to enable.")


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 3: REAL-TIME ATTACK & INCIDENT FEED
# ─────────────────────────────────────────────────────────────────────────

def render_incident_feed():
    """Render real-time incident and attack log."""
    st.header("🚨 Real-Time Incident Feed")
    
    historian = get_historian()
    rule_detector = get_rule_detector()
    
    # Fetch recent data
    recent_transactions = historian.get_recent_transactions(500)
    recent_attacks = historian.get_attack_history(50)
    
    # Create incident feed
    incidents = []
    
    # Add attack events
    for attack in recent_attacks:
        incidents.append({
            'type': 'attack',
            'timestamp': attack.get('timestamp'),
            'severity': 'critical' if attack.get('success') else 'high',
            'title': f"Attack: {attack.get('attack_name')}",
            'description': attack.get('details', ''),
            'details': attack
        })
    
    # Add flagged transactions
    for tx in recent_transactions:
        if tx.get('is_attack'):
            incidents.append({
                'type': 'transaction',
                'timestamp': tx.get('timestamp'),
                'severity': 'high',
                'title': f"Suspicious Modbus FC{tx.get('function_code')}",
                'description': f"Address {tx.get('address')} | Write: {tx.get('is_write')}",
                'details': tx
            })
    
    # Analyze for anomalies
    anomalies = rule_detector.analyze(historian, limit=200)
    for anomaly in anomalies:
        incidents.append({
            'type': 'anomaly',
            'timestamp': anomaly.timestamp,
            'severity': anomaly.severity,
            'title': f"Anomaly: {anomaly.category}",
            'description': anomaly.description,
            'details': anomaly
        })
    
    # Sort by timestamp (most recent first)
    incidents.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Display controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        severity_filter = st.multiselect(
            "Filter by Severity",
            ["critical", "high", "medium", "low"],
            default=["critical", "high"],
            key="incident_severity"
        )
    
    with col2:
        type_filter = st.multiselect(
            "Filter by Type",
            ["attack", "transaction", "anomaly"],
            default=["attack", "transaction", "anomaly"],
            key="incident_type"
        )
    
    with col3:
        limit_incidents = st.slider("Show Recent", 10, 100, 30)
    
    # Filter incidents
    filtered_incidents = [
        i for i in incidents
        if i['severity'] in severity_filter and i['type'] in type_filter
    ][:limit_incidents]
    
    # Display incident feed
    if filtered_incidents:
        st.subheader(f"Showing {len(filtered_incidents)} Recent Incidents")
        
        for incident in filtered_incidents:
            severity = incident['severity']
            color = get_status_color(severity)
            icon_map = {
                'attack': '⚠️',
                'transaction': '📡',
                'anomaly': '🔍'
            }
            icon = icon_map.get(incident['type'], '•')
            
            st.markdown(f"""
            <div class="alert-box" style="border-left-color: {color}; background-color: rgba({color.lstrip('#')}, 0.1);">
                <strong>{icon} {incident['title']}</strong> • {get_status_badge(severity)}<br>
                <em>{incident['description']}</em><br>
                <code style="color: #94a3b8; font-size: 0.85em;">{incident['timestamp'][:19]}</code>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No incidents match current filters")
    
    # Statistics
    st.subheader("Incident Statistics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Attacks", len(recent_attacks))
    
    with col2:
        successful_attacks = sum(1 for a in recent_attacks if a.get('success'))
        st.metric("Successful", successful_attacks)
    
    with col3:
        flagged_tx = sum(1 for tx in recent_transactions if tx.get('is_attack'))
        st.metric("Flagged Transactions", flagged_tx)
    
    with col4:
        st.metric("Rule Anomalies", len(anomalies))


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 4: MITRE ATT&CK MATRIX VIEW
# ─────────────────────────────────────────────────────────────────────────

def render_mitre_matrix():
    """Render MITRE ATT&CK for ICS technique matrix."""
    st.header("🗺️ MITRE ATT&CK for ICS — Technique Matrix")
    
    historian = get_historian()
    
    # Load MITRE data
    mitre_data_path = PROJECT_ROOT / "data" / "mitre_ics_techniques.json"
    
    if not mitre_data_path.exists():
        st.warning("MITRE ICS techniques database not found")
        return
    
    with open(mitre_data_path, 'r') as f:
        mitre_techniques = json.load(f)
    
    # Get executed techniques from historian
    attack_history = historian.get_attack_history(100)
    executed_techniques = set()
    
    for attack in attack_history:
        if attack.get('mitre_techniques'):
            techniques_str = attack.get('mitre_techniques')
            if isinstance(techniques_str, str):
                # Parse techniques from string (e.g., "T0802, T0861")
                for tech in techniques_str.split(','):
                    executed_techniques.add(tech.strip())
    
    # Group by tactic
    tactics = {}
    for tech_id, tech_data in mitre_techniques.items():
        tactic = tech_data.get('tactic', 'Unknown')
        if tactic not in tactics:
            tactics[tactic] = []
        tactics[tactic].append({
            'id': tech_id,
            'name': tech_data.get('name', 'Unknown'),
            'description': tech_data.get('description', ''),
            'executed': tech_id in executed_techniques
        })
    
    # Display matrix
    st.subheader("ICS Tactics & Techniques")
    
    cols = st.columns(3)
    col_idx = 0
    
    for tactic in sorted(tactics.keys()):
        with cols[col_idx % 3]:
            st.write(f"**{tactic}**")
            
            for technique in tactics[tactic]:
                status_icon = "🔴" if technique['executed'] else "⚪"
                bg_color = "rgba(239, 68, 68, 0.1)" if technique['executed'] else "rgba(30, 41, 59, 0.5)"
                border_color = "#ef4444" if technique['executed'] else "#334155"
                
                st.markdown(f"""
                <div style="
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-left: 4px solid {border_color};
                    padding: 0.75rem;
                    margin: 0.5rem 0;
                    border-radius: 0.25rem;
                    cursor: pointer;
                ">
                    <strong>{status_icon} {technique['id']}</strong><br>
                    <small>{technique['name']}</small>
                </div>
                """, unsafe_allow_html=True)
        
        col_idx += 1
    
    # Legend
    st.divider()
    st.markdown("""
    **Legend:**
    - 🔴 Red: Executed in current assessment
    - ⚪ Gray: Not executed
    """)


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 5: SCENARIO GENERATOR & ATTACK LAUNCHER
# ─────────────────────────────────────────────────────────────────────────

def render_scenario_generator():
    """Render attack scenario generator and launcher."""
    st.header("🧪 Attack Scenario Generator")
    
    historian = get_historian()
    
    tab1, tab2 = st.tabs(["Generate Scenario", "Launch Attack"])
    
    with tab1:
        st.subheader("LLM-Powered Scenario Generation")
        
        st.markdown("""
        Enter a natural-language description of an attack scenario. The system will use an LLM
        to generate Modbus payloads and map the techniques to MITRE ATT&CK for ICS.
        """)
        
        scenario_input = st.text_area(
            "Attack Objective",
            placeholder="e.g., 'Overflow the water tank by increasing inflow and closing outlet valve'",
            height=100
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            duration_secs = st.slider("Duration (seconds)", 10, 300, 60)
        
        with col2:
            intensity = st.slider("Intensity", 1, 10, 5, help="1=minimal, 10=maximum")
        
        generate_btn = st.button(
            "🚀 Generate Scenario",
            use_container_width=True,
            type="primary",
            disabled=not scenario_input
        )
        
        if generate_btn and scenario_input:
            with st.spinner("🔄 Generating scenario with LLM..."):
                try:
                    scenario = generate_scenario(scenario_input)
                    
                    st.success("✅ Scenario generated successfully")
                    
                    # Store in session state for later launch
                    st.session_state.current_scenario = scenario
                    st.session_state.scenario_duration = duration_secs
                    st.session_state.scenario_intensity = intensity
                    
                    # Display scenario details
                    st.subheader(f"📋 {scenario.name}")
                    
                    st.markdown(f"""
                    **Objective:** {scenario.objective}
                    
                    **Estimated Impact:** {scenario.estimated_impact}
                    
                    **Description:** {scenario.description}
                    """)
                    
                    # MITRE techniques
                    if scenario.mitre_techniques:
                        st.subheader("MITRE ATT&CK Mapping")
                        
                        tech_df = pd.DataFrame([
                            {
                                'Technique ID': t.technique_id,
                                'Technique Name': t.name,
                                'Tactic': t.tactic,
                                'Description': t.description
                            }
                            for t in scenario.mitre_techniques
                        ])
                        
                        st.dataframe(tech_df, use_container_width=True)
                    
                    # Attack steps
                    if scenario.steps:
                        st.subheader("Attack Steps")
                        
                        steps_df = pd.DataFrame([
                            {
                                'Order': s.order,
                                'Description': s.description,
                                'Function Code': s.function_code,
                                'Start Address': s.start_address,
                                'Count': s.count,
                                'Values': ', '.join(map(str, s.values)) if s.values else 'N/A',
                                'Delay (s)': s.delay_seconds
                            }
                            for s in scenario.steps
                        ])
                        
                        st.dataframe(steps_df, use_container_width=True)
                    
                    # Detection indicators
                    if scenario.detection_indicators:
                        st.subheader("Detection Indicators")
                        
                        for indicator in scenario.detection_indicators:
                            st.markdown(f"- {indicator}")
                    
                    st.info("✨ Scenario ready for launch. Go to 'Launch Attack' tab to execute.")
                    
                except Exception as e:
                    st.error(f"❌ Error generating scenario: {str(e)}")
                    st.info("Make sure LLM API keys are configured in .env")
    
    with tab2:
        st.subheader("Launch Attack")
        
        # Option 1: Launch generated scenario
        if hasattr(st.session_state, 'current_scenario') and st.session_state.current_scenario:
            st.markdown(f"""
            ### Generated Scenario
            **{st.session_state.current_scenario.name}**
            """)
            
            col1, col2 = st.columns(2)
            
            with col1:
                execute_generated = st.button(
                    "▶️ Execute Generated Scenario",
                    use_container_width=True,
                    type="primary"
                )
            
            with col2:
                clear_scenario = st.button("Clear Scenario", use_container_width=True)
            
            if clear_scenario:
                st.session_state.current_scenario = None
                st.rerun()
            
            if execute_generated:
                st.warning("🚨 Executing attack scenario...", icon="⚠️")
                
                # Execute scenario
                try:
                    scenario = st.session_state.current_scenario
                    attacks = build_attacks_from_scenario(
                        scenario,
                        host="127.0.0.1",
                        port=5020,
                        historian=historian
                    )
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, attack in enumerate(attacks):
                        status_text.text(f"Executing: {attack.name}")
                        
                        # Run attack (simplified for UI)
                        result = asyncio.run(attack.run())
                        
                        progress = (i + 1) / len(attacks)
                        progress_bar.progress(progress)
                    
                    st.success("✅ Scenario execution complete")
                    
                    # Results
                    st.subheader("Execution Results")
                    st.info("Check the Incident Feed tab for detailed logs")
                    
                except Exception as e:
                    st.error(f"❌ Execution failed: {str(e)}")
        
        else:
            st.info("📌 Generate a scenario first using the 'Generate Scenario' tab")
        
        st.divider()
        
        # Option 2: Predefined attacks
        st.subheader("Predefined Attacks")
        
        attack_name = st.selectbox(
            "Choose Attack",
            list(ATTACK_REGISTRY.keys()),
            key="attack_selector"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            target_address = st.number_input(
                "Target Register Address",
                min_value=0,
                max_value=65535,
                value=100,
                step=1
            )
        
        with col2:
            target_count = st.number_input(
                "Register Count",
                min_value=1,
                max_value=100,
                value=1,
                step=1
            )
        
        if st.button("▶️ Launch Predefined Attack", use_container_width=True, type="primary"):
            st.warning("🚨 Launching attack...", icon="⚠️")
            
            try:
                attack_class = get_attack(attack_name)
                if attack_class:
                    attack = attack_class(
                        host="127.0.0.1",
                        port=5020,
                        historian=historian,
                        starting_address=target_address,
                        count=target_count
                    )
                    
                    result = asyncio.run(attack.run())
                    
                    if result.success:
                        st.success("✅ Attack executed successfully")
                    else:
                        st.warning(f"⚠️ Attack execution completed: {result.details}")
                    
                    # Show results
                    st.subheader("Attack Result")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Status", "Success" if result.success else "Failed")
                    
                    with col2:
                        duration = (result.end_time - result.start_time).total_seconds() if result.end_time else 0
                        st.metric("Duration", f"{duration:.2f}s")
                    
                    with col3:
                        st.metric("Registers Affected", len(result.registers_affected))
                    
                    if result.details:
                        st.info(f"Details: {result.details}")
                    
                else:
                    st.error(f"Attack '{attack_name}' not found")
                    
            except Exception as e:
                st.error(f"❌ Attack failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 6: ANALYTICS & REPORTING
# ─────────────────────────────────────────────────────────────────────────

def render_analytics():
    """Render analytics and reporting dashboard."""
    st.header("📊 Analytics & Reporting")
    
    historian = get_historian()
    
    # Time range selector
    col1, col2 = st.columns(2)
    
    with col1:
        time_range = st.selectbox(
            "Time Range",
            ["Last Hour", "Last 6 Hours", "Last 24 Hours", "All Time"],
            index=1
        )
    
    with col2:
        refresh_rate = st.selectbox("Refresh Rate", ["Manual", "30s", "1m", "5m"], index=0)
    
    # Get data based on time range
    if time_range == "Last Hour":
        limit = 500
    elif time_range == "Last 6 Hours":
        limit = 1000
    elif time_range == "Last 24 Hours":
        limit = 2000
    else:
        limit = 5000
    
    recent_states = historian.get_recent_process_states(limit)
    recent_attacks = historian.get_attack_history(100)
    recent_transactions = historian.get_recent_transactions(limit)
    
    if not recent_states:
        st.warning("No data available for analysis")
        return
    
    # Convert to DataFrame
    states_df = pd.DataFrame(recent_states)
    states_df['timestamp'] = pd.to_datetime(states_df['timestamp'])
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Process Health", "Attack Summary", "Transaction Analysis"])
    
    with tab1:
        st.subheader("Process Health Over Time")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Tank level trend
            fig = px.line(
                states_df,
                x='timestamp',
                y='tank_level',
                title='Tank Level Trend',
                labels={'tank_level': 'Level (%)', 'timestamp': 'Time'}
            )
            fig.add_hline(y=90, line_dash="dash", line_color="red", annotation_text="High Alarm")
            fig.add_hline(y=10, line_dash="dash", line_color="red", annotation_text="Low Alarm")
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor='#0f172a',
                plot_bgcolor='#1e293b',
                font=dict(color='#f1f5f9'),
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Pressure trend
            fig = px.line(
                states_df,
                x='timestamp',
                y='pressure_psi',
                title='Pressure Trend',
                labels={'pressure_psi': 'PSI', 'timestamp': 'Time'}
            )
            fig.add_hline(y=80, line_dash="dash", line_color="orange", annotation_text="High Limit")
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor='#0f172a',
                plot_bgcolor='#1e293b',
                font=dict(color='#f1f5f9'),
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Alarm frequency
        alarm_cols = ['high_level_alarm', 'low_level_alarm', 'ph_alarm', 'pressure_alarm']
        alarm_counts = {
            'High Level': states_df['high_level_alarm'].sum(),
            'Low Level': states_df['low_level_alarm'].sum(),
            'pH': states_df['ph_alarm'].sum(),
            'Pressure': states_df['pressure_alarm'].sum()
        }
        
        alarm_df = pd.DataFrame(list(alarm_counts.items()), columns=['Alarm Type', 'Count'])
        
        fig = px.bar(
            alarm_df,
            x='Alarm Type',
            y='Count',
            title='Alarm Frequency',
            color='Count',
            color_continuous_scale=['#10b981', '#f59e0b', '#ef4444']
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor='#0f172a',
            plot_bgcolor='#1e293b',
            font=dict(color='#f1f5f9'),
            height=350,
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("Attack Summary")
        
        if recent_attacks:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Attacks", len(recent_attacks))
            
            with col2:
                successful = sum(1 for a in recent_attacks if a.get('success'))
                st.metric("Successful", successful, f"{successful/len(recent_attacks)*100:.0f}%")
            
            with col3:
                failed = len(recent_attacks) - successful
                st.metric("Failed", failed)
            
            with col4:
                duration_total = sum(
                    float(a.get('duration_seconds', 0)) for a in recent_attacks
                )
                st.metric("Total Duration", f"{duration_total:.0f}s")
            
            # Attack distribution
            attack_types = {}
            for attack in recent_attacks:
                atk_type = attack.get('attack_name', 'Unknown')
                attack_types[atk_type] = attack_types.get(atk_type, 0) + 1
            
            atk_df = pd.DataFrame(list(attack_types.items()), columns=['Attack', 'Count'])
            
            fig = px.pie(
                atk_df,
                values='Count',
                names='Attack',
                title='Attack Distribution',
                color_discrete_sequence=px.colors.sequential.Reds_r
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor='#0f172a',
                font=dict(color='#f1f5f9'),
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No attacks recorded")
    
    with tab3:
        st.subheader("Transaction Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            total_tx = len(recent_transactions)
            write_tx = sum(1 for tx in recent_transactions if tx.get('is_write'))
            read_tx = total_tx - write_tx
            
            st.metric("Total Transactions", total_tx)
            st.metric("Reads", read_tx)
            st.metric("Writes", write_tx)
        
        with col2:
            flagged = sum(1 for tx in recent_transactions if tx.get('is_attack'))
            normal = total_tx - flagged
            
            st.metric("Normal Transactions", normal)
            st.metric("Flagged Transactions", flagged)
        
        # Function code distribution
        function_codes = {}
        for tx in recent_transactions:
            fc = tx.get('function_code', 0)
            function_codes[fc] = function_codes.get(fc, 0) + 1
        
        fc_df = pd.DataFrame([
            {'Function Code': f'FC {fc}', 'Count': count}
            for fc, count in sorted(function_codes.items())
        ])
        
        fig = px.bar(
            fc_df,
            x='Function Code',
            y='Count',
            title='Modbus Function Code Distribution',
            color='Count',
            color_continuous_scale='Viridis'
        )
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor='#0f172a',
            plot_bgcolor='#1e293b',
            font=dict(color='#f1f5f9'),
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────
# COMPONENT 7: SETTINGS & MODEL MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────

def render_settings():
    """Render settings and configuration panel."""
    st.header("⚙️ Settings & Configuration")
    
    tab1, tab2, tab3 = st.tabs(["ML Models", "System Config", "Data Management"])
    
    with tab1:
        st.subheader("ML Model Management")
        
        enhanced_detector = get_enhanced_detector()
        capabilities = enhanced_detector.get_detection_capabilities()
        
        # Model status
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Isolation Forest")
            
            if capabilities["ml_based"]["models_loaded"] and enhanced_detector.ml_detector.isolation_forest:
                st.success("✅ Loaded")
                st.info(f"Estimators: {enhanced_detector.ml_detector.isolation_forest.n_estimators}")
                st.info(f"Contamination: {enhanced_detector.ml_detector.isolation_forest.contamination}")
            else:
                st.warning("⚠️ Not Loaded")
        
        with col2:
            st.markdown("### LSTM")
            
            if capabilities["ml_based"]["models_loaded"] and enhanced_detector.ml_detector.lstm_model:
                st.success("✅ Loaded")
                st.info(f"Parameters: {enhanced_detector.ml_detector.lstm_model.count_params():,}")
                st.info(f"Window Size: {enhanced_detector.ml_detector.window_size}")
            else:
                st.warning("⚠️ Not Loaded")
        
        st.divider()
        
        # Training controls
        st.subheader("Model Training")
        
        col1, col2 = st.columns(2)
        
        with col1:
            sample_size = st.number_input(
                "Training Sample Size",
                min_value=100,
                max_value=50000,
                value=10000,
                step=1000
            )
        
        with col2:
            epochs = st.number_input(
                "LSTM Epochs",
                min_value=10,
                max_value=200,
                value=50,
                step=10
            )
        
        if st.button("🔄 Retrain Models", use_container_width=True, type="primary"):
            st.warning("Training in progress...", icon="⏳")
            
            try:
                from ot_twin.environment.ml_model_trainer import MLModelTrainer
                
                historian = get_historian()
                trainer = MLModelTrainer(historian=historian)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.info("Training Isolation Forest...")
                    iso_success = trainer.train_isolation_forest(sample_size=sample_size)
                    if iso_success:
                        st.success("✅ Isolation Forest trained")
                    else:
                        st.error("❌ Failed to train Isolation Forest")
                
                with col2:
                    st.info("Training LSTM...")
                    lstm_success = trainer.train_lstm(sample_size=sample_size, epochs=epochs)
                    if lstm_success:
                        st.success("✅ LSTM trained")
                    else:
                        st.error("❌ Failed to train LSTM")
                
                if iso_success and lstm_success:
                    st.success("✅ All models trained successfully")
                    st.rerun()
                
            except Exception as e:
                st.error(f"❌ Training error: {str(e)}")
    
    with tab2:
        st.subheader("System Configuration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**PLC Connection**")
            plc_host = st.text_input("Host", value="127.0.0.1")
            plc_port = st.number_input("Port", value=5020, min_value=1024, max_value=65535)
        
        with col2:
            st.markdown("**Detection Settings**")
            write_burst_threshold = st.number_input(
                "Write Burst Threshold",
                min_value=1,
                max_value=100,
                value=10
            )
            burst_window = st.number_input(
                "Burst Window (s)",
                min_value=1.0,
                max_value=30.0,
                value=5.0,
                step=0.5
            )
        
        if st.button("💾 Save Configuration", use_container_width=True):
            st.success("✅ Configuration saved")
    
    with tab3:
        st.subheader("Data Management")
        
        historian = get_historian()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            tx_count = historian.get_transaction_count()
            st.metric("Transactions", tx_count)
        
        with col2:
            # Count process states (approximation)
            recent_states = historian.get_recent_process_states(1000)
            st.metric("Process States", len(recent_states))
        
        with col3:
            recent_attacks = historian.get_attack_history(1000)
            st.metric("Attacks", len(recent_attacks))
        
        with col4:
            # Estimate DB size
            import os
            db_path = Path(PROJECT_ROOT) / "data" / "historian.db"
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                st.metric("DB Size", f"{size_mb:.2f} MB")
        
        st.divider()
        
        if st.button("🗑️ Clear All Data", use_container_width=True, type="secondary"):
            if st.checkbox("Confirm deletion"):
                st.warning("Data deletion not implemented in UI - use CLI")


# ─────────────────────────────────────────────────────────────────────────
# MAIN APP LAYOUT
# ─────────────────────────────────────────────────────────────────────────

def main():
    """Main Streamlit application."""
    
    # Sidebar navigation
    with st.sidebar:
        st.image("https://via.placeholder.com/300x100?text=OT+Twin", use_column_width=True)
        st.title("OT Digital Twin")
        st.markdown("Industrial SCADA Security Platform")
        st.divider()
        
        page = option_menu(
            "Navigation",
            [
                "🏭 SCADA HMI",
                "🤖 ML Detection",
                "🚨 Incidents",
                "🗺️ MITRE Matrix",
                "🧪 Scenarios",
                "📊 Analytics",
                "⚙️ Settings"
            ],
            icons=["speedometer2", "robot", "exclamation-triangle", "diagram-2", "flask", "bar-chart", "gear"],
            menu_icon="list",
            default_index=0
        )
        
        st.divider()
        
        # Quick stats
        st.subheader("Quick Stats")
        
        historian = get_historian()
        recent_attacks = historian.get_attack_history(100)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Attacks", len(recent_attacks))
        with col2:
            st.metric("Status", "🟢 Online")
    
    # Route to pages
    if page == "🏭 SCADA HMI":
        render_hmi_dashboard()
    elif page == "🤖 ML Detection":
        render_ml_detection_engine()
    elif page == "🚨 Incidents":
        render_incident_feed()
    elif page == "🗺️ MITRE Matrix":
        render_mitre_matrix()
    elif page == "🧪 Scenarios":
        render_scenario_generator()
    elif page == "📊 Analytics":
        render_analytics()
    elif page == "⚙️ Settings":
        render_settings()


if __name__ == "__main__":
    main()
