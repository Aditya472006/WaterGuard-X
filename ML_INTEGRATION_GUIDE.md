# ML Model Integration Guide

Complete walkthrough for integrating Isolation Forest and LSTM anomaly detection models into the OT Digital Twin platform.

## Overview

The project now includes **two machine learning models** for advanced anomaly detection:

1. **Isolation Forest** — Detects outlier transactions in multi-dimensional Modbus traffic
2. **LSTM Network** — Forecasts sensor values and detects temporal anomalies

These models are integrated into:
- Rule-based anomaly detector (legacy)
- Enhanced anomaly detector (hybrid)
- ML-specific detector (pure ML)
- Streamlit web dashboard (visualization & control)

## Architecture

### Module Organization

```
ot_twin/environment/
├── ml_anomaly_detector.py        # ML inference engine
├── ml_model_trainer.py            # Model training utilities
├── enhanced_anomaly_detector.py   # Hybrid rule + ML detector
├── anomaly_detector.py            # Rule-based detector (legacy)
├── risk_scorer.py                 # Risk calculation
└── ...other modules...

streamlit_app.py                   # Web dashboard with ML integration
```

### Data Flow

```
PLC Simulation
    ↓
SCADA Master (polling every 2s)
    ↓
Historian (SQLite database)
    ├─→ Transactions Table
    ├─→ Process States Table
    └─→ Attack Results Table
         ↓
    Enhanced Anomaly Detector
         ├─→ Rule-based Engine
         │   • Rapid writes
         │   • Out-of-range values
         │   • Unusual function codes
         │
         ├─→ Isolation Forest
         │   • Multi-dimensional feature analysis
         │   • Outlier scoring
         │   • Confidence quantification
         │
         └─→ LSTM Forecasting
             • Time-series prediction
             • Deviation detection
             • Process drift identification
              ↓
    Results & Visualizations
         ├─→ Streamlit UI
         ├─→ CLI output
         └─→ Alert notifications
```

## Component Details

### 1. ML Anomaly Detector (`ml_anomaly_detector.py`)

**Purpose**: Load and use pre-trained ML models for real-time anomaly detection.

**Key Classes**:
- `MLAnomaly` — Dataclass for ML-detected anomalies
- `MLAnomalyDetector` — Main inference engine

**Features**:
- Loads pre-trained models (pickle + h5)
- Extracts transaction and sensor features
- Runs Isolation Forest inference
- Runs LSTM forecasting
- Cross-validates with historian data

**Usage Example**:
```python
from ot_twin.environment.ml_anomaly_detector import MLAnomalyDetector
from ot_twin.environment.historian import Historian

# Initialize
historian = Historian()
detector = MLAnomalyDetector(model_dir=".")

# Load pre-trained models
if detector.load_models():
    print("✓ Models loaded")
else:
    print("✗ Models not found - train first")

# Detect transaction anomalies
transactions = historian.get_recent_transactions(500)
anomalies = detector.detect_transaction_anomalies(transactions)

for anom in anomalies:
    print(f"{anom.severity}: {anom.description}")

# Forecast sensor values
states = historian.get_recent_process_states(500)
forecasts, forecast_anomalies = detector.forecast_sensor_values(states, forecast_steps=10)
```

### 2. ML Model Trainer (`ml_model_trainer.py`)

**Purpose**: Train new ML models from historian data.

**Key Classes**:
- `MLModelTrainer` — Training orchestrator

**Training Pipeline**:

#### Isolation Forest Training
```python
from ot_twin.environment.ml_model_trainer import MLModelTrainer
from ot_twin.environment.historian import Historian

historian = Historian()
trainer = MLModelTrainer(historian=historian)

# Train on 10,000 transactions
success = trainer.train_isolation_forest(
    sample_size=10000,
    contamination=0.1,  # Assume 10% anomalies
    n_estimators=100    # Number of isolation trees
)

if success:
    print("✓ Model saved to isolation_forest_model.pkl")
```

**Features Extracted**:
- `function_code` — Modbus FC (1-16)
- `register_type_code` — Register type (0-3)
- `address` — Starting address
- `count` — Number of registers
- `is_write` — Read vs. write (0/1)
- `hour_of_day` — Temporal feature
- `minute_of_hour` — Temporal feature
- `value_mean` — Mean of register values
- `value_std` — Std dev of register values

#### LSTM Training
```python
# Train on 10,000 process states with 50 epochs
success = trainer.train_lstm(
    sample_size=10000,
    window_size=10,      # 10-step sequences
    epochs=50,           # Training iterations
    batch_size=32
)

if success:
    print("✓ Model saved to lstm.h5")
```

**Sensor Features for LSTM**:
- `tank_level`, `ph_level`, `chlorine_dosing`
- `pressure_psi`, `temperature_c`, `turbidity`
- `inflow_rate`, `outflow_rate`

### 3. Enhanced Anomaly Detector (`enhanced_anomaly_detector.py`)

**Purpose**: Combine rule-based and ML-based detection with cross-validation.

**Key Classes**:
- `EnhancedAnomalyDetector` — Hybrid detector orchestrator

**Hybrid Analysis**:
```python
from ot_twin.environment.enhanced_anomaly_detector import EnhancedAnomalyDetector
from ot_twin.environment.historian import Historian

historian = Historian()
detector = EnhancedAnomalyDetector(use_ml=True)

# Run comprehensive analysis
results = detector.analyze(
    historian,
    transaction_limit=1000,
    state_limit=500,
    include_forecast=True
)

# Results structure:
results['rule_based']      # Rule-based detections
results['ml_based']        # ML detections
results['combined']        # Cross-validation results
results['recommendations'] # Actionable insights
```

**Cross-Validation**:
- Matches anomalies by timestamp (±30s window)
- Groups by category (transaction_pattern, value_anomaly, etc.)
- Identifies:
  - `confirmed_by_both` — High confidence
  - `rule_only` — Rule-based finding
  - `ml_only` — ML-specific finding

## Integration Points

### CLI Commands

```bash
# Train models from CLI
python -m ot_twin.cli train-models --samples 10000 --retrain

# Run enhanced analysis
python -m ot_twin.cli analyze-ml --limit 1000 --ml-only

# Show model info
python -m ot_twin.cli model-info

# Generate forecasts
python -m ot_twin.cli forecast --steps 10 --interval 5
```

### Streamlit Dashboard

**ML Detection Tab**:
- Combined analysis with severity breakdown
- Isolation Forest visualization
- LSTM forecasting charts
- Confidence scoring
- Anomaly log with filtering

**Settings Tab**:
- Model status display
- Training controls
- Hyperparameter configuration
- Sample size tuning

### Python API

```python
# Minimal integration example
from ot_twin.environment.enhanced_anomaly_detector import EnhancedAnomalyDetector
from ot_twin.environment.historian import Historian

def monitor_system():
    historian = Historian()
    detector = EnhancedAnomalyDetector(use_ml=True)
    
    while True:
        results = detector.analyze(historian, transaction_limit=500)
        
        critical_count = sum(
            1 for a in results['combined']['summary'].get('confirmed_by_both', [])
            if a.get('severity') == 'critical'
        )
        
        if critical_count > 0:
            print(f"🚨 {critical_count} critical anomalies detected")
        
        time.sleep(60)  # Analyze every minute

monitor_system()
```

## Model Performance

### Isolation Forest

**Inference Time**: ~100ms for 500 transactions

**Anomaly Score Interpretation**:
- Score < -1.0 → Severity: CRITICAL
- Score < -0.7 → Severity: HIGH
- Score < -0.4 → Severity: MEDIUM
- Score ≥ -0.4 → Severity: LOW

**Output**:
```python
MLAnomaly(
    severity="critical",
    category="isolation_forest",
    description="ML-detected anomalous transaction: FC16 at address 105",
    timestamp="2024-10-16T14:23:45",
    confidence=0.89,  # abs(anomaly_score)
    details={
        "address": 105,
        "function_code": 16,
        "is_write": True,
        "anomaly_score": -0.89,
        "feature_vector": [16, 0, 105, 5, 1, 14, 23, 32.5, 12.3]
    }
)
```

### LSTM

**Inference Time**: ~500ms for 10-step forecast

**Forecast Output**:
```python
{
    "timestamp": "2024-10-16T14:25:00",
    "predictions": {
        "tank_level": 52.3,
        "ph_level": 7.15,
        "pressure_psi": 48.2,
        "temperature_c": 22.8
    },
    "step": 1
}
```

**Anomaly Detection**:
- Mean Absolute Error (MAE) > 2.0 → Anomaly detected
- Visualized as shaded zones on charts

## Training Guidelines

### Data Requirements

**Isolation Forest**:
- Minimum: 100 transactions
- Recommended: 10,000+ transactions
- Training time: <30 seconds

**LSTM**:
- Minimum: 100 sequences (window_size * 10)
- Recommended: 1,000+ sequences
- Training time: 2-5 minutes

### Hyperparameter Tuning

**Isolation Forest**:
```python
trainer.train_isolation_forest(
    sample_size=10000,
    contamination=0.1,      # % of expected anomalies
    n_estimators=100        # More trees = more robust
)
```

- ↑ `contamination` → More sensitive, more false positives
- ↑ `n_estimators` → Better detection, slower inference

**LSTM**:
```python
trainer.train_lstm(
    sample_size=10000,
    window_size=10,    # Sequence length (5-20 typical)
    epochs=50,         # More epochs = longer training
    batch_size=32      # Larger batch = faster but less stable
)
```

- ↑ `window_size` → Captures longer patterns
- ↑ `epochs` → Better fitting but risk of overfitting
- ↑ `batch_size` → Faster training, coarser gradients

## Troubleshooting

### Models Not Loading

**Symptom**: "ML models not loaded" warning in Streamlit

**Solutions**:
```bash
# Train models from scratch
python -m ot_twin.cli train-models --samples 10000 --retrain

# Check model files exist
ls -lh isolation_forest_model.pkl lstm.h5

# Verify permissions
chmod 644 isolation_forest_model.pkl lstm.h5
```

### Insufficient Training Data

**Symptom**: "Only N samples available (need at least M)"

**Solutions**:
- Run SCADA for longer to accumulate data
- Reduce sample size requirement: `--samples 1000`
- Use synthetic data generation (future enhancement)

### High False Positive Rate

**Symptoms**:
- All transactions flagged as anomalies
- Constant alerts in Streamlit

**Solutions**:
- Increase `contamination` parameter
- Collect more normal baseline data
- Retrain with balanced dataset
- Adjust confidence threshold in Streamlit

### LSTM Predictions Inaccurate

**Symptoms**:
- Forecast always flat or constant
- Large MAE values
- Poor drift detection

**Solutions**:
- Increase training data
- Reduce window size for shorter patterns
- Increase epochs for better convergence
- Verify input normalization

## Best Practices

### 1. Regular Retraining
```bash
# Monthly retraining
python -m ot_twin.cli train-models --samples 20000 --retrain
```

### 2. Baseline Establishment
```bash
# Collect 24 hours of normal operation before production
# Use this baseline for model training and threshold tuning
```

### 3. Cross-Validation
```python
# Compare ML results with rule-based detection
results = enhanced_detector.analyze(historian)
confirmed = results['combined']['summary']['confirmed_by_both']

# High-confidence anomalies: flagged by both methods
if confirmed > 0:
    trigger_alert()
```

### 4. Monitoring
```bash
# Monitor model accuracy in production
python -m ot_twin.cli analyze-ml --limit 1000 > analysis.json

# Parse JSON for metrics
# - Anomaly rate (%)
# - Severity distribution
# - Detection coverage
```

## Future Enhancements

### Planned Improvements
1. **Ensemble Models**: Combine multiple algorithms
2. **Online Learning**: Continuous model updates
3. **Explainability**: SHAP values for feature importance
4. **Transfer Learning**: Pre-trained models on ICS datasets
5. **Distributed Training**: GPU acceleration for LSTM
6. **Real-time Retraining**: Auto-retrain on new patterns
7. **Anomaly Clustering**: Group related anomalies
8. **Predictive Alerts**: Warn before attacks occur

### Experimental Features
- Autoencoders for unsupervised detection
- Time series classification for attack type prediction
- Graph neural networks for Modbus topology analysis
- Attention mechanisms for interpretable predictions

## References

### Papers
- Liu et al. (2008) — Isolation Forest [original paper]
- Hochreiter & Schmidhuber (1997) — LSTM [foundational work]
- Goodfellow et al. (2016) — Deep Learning [comprehensive reference]

### Libraries
- scikit-learn: https://scikit-learn.org/stable/
- TensorFlow/Keras: https://www.tensorflow.org/
- Pandas: https://pandas.pydata.org/

### ICS Security
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework
- IEC 62443 Standard: https://en.wikipedia.org/wiki/IEC_62443
- MITRE ATT&CK for ICS: https://attack.mitre.org/tactics/ics/

## Support & Issues

For issues or questions:
1. Check model files exist and have size > 0
2. Verify dependencies: `pip install -r requirements.txt`
3. Test models individually via CLI
4. Review console logs for detailed error messages
5. Open GitHub issue with reproducible example

---

**Last Updated**: October 2024
**Version**: 1.0
**Status**: Production-Ready
