"""
ML-based Anomaly Detector — Uses Isolation Forest for transaction anomaly detection
and LSTM for sensor time-series forecasting.

This module integrates with the existing AnomalyDetector but adds ML-based detection
capabilities for more sophisticated anomaly detection.
"""

from __future__ import annotations

import json
import logging
import pickle
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from tensorflow import keras

from ot_twin.config import PROJECT_ROOT
from ot_twin.environment.historian import Historian
from ot_twin.models import ModbusTransaction, ProcessState, RegisterType

warnings.filterwarnings('ignore', category=UserWarning)

logger = logging.getLogger(__name__)


@dataclass
class MLAnomaly:
    """A machine learning detected anomaly."""
    severity: str  # "low", "medium", "high", "critical"
    category: str  # "isolation_forest", "lstm_forecast", "ensemble"
    description: str
    timestamp: str = ""
    confidence: float = 0.0
    details: dict = field(default_factory=dict)


class MLAnomalyDetector:
    """
    ML-based anomaly detector that uses both Isolation Forest and LSTM models.
    
    Features:
    1. Isolation Forest for multi-dimensional anomaly detection on transaction features
    2. LSTM for time-series forecasting of sensor values
    3. Ensemble scoring combining both models
    """
    
    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir) if model_dir else PROJECT_ROOT
        self.isolation_forest = None
        self.lstm_model = None
        self.feature_scaler = None
        self.is_loaded = False
        
        # Feature configuration
        self.transaction_features = [
            'function_code', 'register_type_code', 'address', 'count',
            'is_write', 'hour_of_day', 'minute_of_hour', 'value_mean', 'value_std'
        ]
        
        # Sensor features for LSTM
        self.sensor_features = [
            'tank_level', 'ph_level', 'chlorine_dosing', 'pressure_psi',
            'temperature_c', 'turbidity', 'inflow_rate', 'outflow_rate'
        ]
        
        self.window_size = 10  # For LSTM time-series
    
    def load_models(self) -> bool:
        """Load pre-trained ML models from disk."""
        self.isolation_forest = None
        self.feature_scaler = None
        self.lstm_model = None

        isolation_forest_path = self.model_dir / "isolation_forest_model.pkl"
        if isolation_forest_path.exists():
            try:
                with open(isolation_forest_path, 'rb') as f:
                    model_data = pickle.load(f)

                if isinstance(model_data, dict) and "model" in model_data:
                    model = model_data["model"]
                    scaler = model_data.get("scaler")
                    features = model_data.get("features")
                    if features is not None and list(features) != self.transaction_features:
                        raise ValueError(
                            "Isolation Forest feature list does not match the detector"
                        )
                    self.feature_scaler = scaler
                else:
                    model = model_data

                expected_features = getattr(model, "n_features_in_", None)
                if expected_features is not None and expected_features != len(self.transaction_features):
                    raise ValueError(
                        f"Isolation Forest expects {expected_features} features; "
                        f"the detector provides {len(self.transaction_features)}"
                    )

                self.isolation_forest = model
                logger.info("Loaded Isolation Forest model from %s", isolation_forest_path)
            except (OSError, pickle.UnpicklingError, EOFError, ValueError, TypeError):
                logger.exception("Could not load Isolation Forest model from %s", isolation_forest_path)
        else:
            logger.warning("Isolation Forest model not found at %s", isolation_forest_path)

        lstm_path = self.model_dir / "lstm.h5"
        if lstm_path.exists() and lstm_path.stat().st_size > 0:
            try:
                self.lstm_model = keras.models.load_model(lstm_path)
                logger.info("Loaded LSTM model from %s", lstm_path)
            except (OSError, ValueError, TypeError):
                logger.exception("Could not load LSTM model from %s", lstm_path)
        else:
            logger.warning("LSTM model not found or empty at %s", lstm_path)

        self.is_loaded = self.isolation_forest is not None or self.lstm_model is not None
        return self.is_loaded
    
    def _extract_transaction_features(self, transactions: list[ModbusTransaction]) -> pd.DataFrame:
        """Extract features from Modbus transactions for ML analysis."""
        features = []
        
        for tx in transactions:
            # Convert register type to numeric code
            register_type_code = {
                RegisterType.HOLDING: 0,
                RegisterType.INPUT: 1,
                RegisterType.COIL: 2,
                RegisterType.DISCRETE_INPUT: 3
            }.get(tx.register_type, 0)
            
            # Extract temporal features
            dt = tx.timestamp
            hour_of_day = dt.hour
            minute_of_hour = dt.minute
            
            # Basic transaction features
            feature_vector = {
                'function_code': tx.function_code,
                'register_type_code': register_type_code,
                'address': tx.address,
                'count': tx.count,
                'is_write': 1 if tx.is_write else 0,
                'is_attack': 1 if tx.is_attack else 0,
                'hour_of_day': hour_of_day,
                'minute_of_hour': minute_of_hour,
                'value_mean': np.mean(tx.values) if tx.values else 0,
                'value_std': np.std(tx.values) if len(tx.values) > 1 else 0
            }
            
            features.append(feature_vector)
        
        return pd.DataFrame(features)
    
    def _extract_sensor_features(self, process_states: list[ProcessState]) -> pd.DataFrame:
        """Extract sensor features from process states for LSTM forecasting."""
        features = []
        
        for state in process_states:
            feature_vector = {
                'timestamp': state.timestamp,
                'tank_level': state.tank_level,
                'ph_level': state.ph_level,
                'chlorine_dosing': state.chlorine_dosing,
                'pressure_psi': state.pressure_psi,
                'temperature_c': state.temperature_c,
                'turbidity': state.turbidity,
                'inflow_rate': state.inflow_rate,
                'outflow_rate': state.outflow_rate,
                'inlet_valve_open': 1 if state.inlet_valve_open else 0,
                'outlet_valve_open': 1 if state.outlet_valve_open else 0,
                'pump_running': 1 if state.pump_running else 0,
                'mixer_running': 1 if state.mixer_running else 0
            }
            
            features.append(feature_vector)
        
        return pd.DataFrame(features).sort_values('timestamp')
    
    def detect_transaction_anomalies(
        self, 
        transactions: list[ModbusTransaction],
        threshold: float = -0.5
    ) -> list[MLAnomaly]:
        """
        Detect anomalies in Modbus transactions using Isolation Forest.
        
        Args:
            transactions: List of Modbus transactions
            threshold: Anomaly score threshold (lower = more anomalous)
        
        Returns:
            List of MLAnomaly objects
        """
        if not self.is_loaded or self.isolation_forest is None:
            return []
        
        anomalies = []
        
        # Extract features
        df = self._extract_transaction_features(transactions)
        if len(df) == 0:
            return anomalies
        
        # Scale features
        features = df[self.transaction_features].values
        if self.feature_scaler is None:
            self.feature_scaler = StandardScaler()
            features_scaled = self.feature_scaler.fit_transform(features)
        else:
            features_scaled = self.feature_scaler.transform(features)
        
        # Predict anomalies
        anomaly_scores = self.isolation_forest.decision_function(features_scaled)
        predictions = self.isolation_forest.predict(features_scaled)
        
        # Create anomaly objects for anomalous transactions
        for idx, (score, pred) in enumerate(zip(anomaly_scores, predictions)):
            if pred == -1 or score < threshold:
                tx = transactions[idx]
                
                # Determine severity based on score
                if score < -1.0:
                    severity = "critical"
                elif score < -0.7:
                    severity = "high"
                elif score < -0.4:
                    severity = "medium"
                else:
                    severity = "low"
                
                anomalies.append(MLAnomaly(
                    severity=severity,
                    category="isolation_forest",
                    description=f"ML-detected anomalous transaction: {tx.function_code} at address {tx.address}",
                    timestamp=tx.timestamp.isoformat(),
                    confidence=abs(score),
                    details={
                        "address": tx.address,
                        "function_code": tx.function_code,
                        "is_write": tx.is_write,
                        "anomaly_score": float(score),
                        "feature_vector": features[idx].tolist()
                    }
                ))
        
        return anomalies
    
    def forecast_sensor_values(
        self,
        process_states: list[ProcessState],
        forecast_steps: int = 5
    ) -> tuple[list[dict], list[MLAnomaly]]:
        """
        Forecast sensor values using LSTM and detect anomalies.
        
        Args:
            process_states: List of historical process states
            forecast_steps: Number of steps to forecast
        
        Returns:
            Tuple of (forecasted_values, anomalies)
        """
        if not self.is_loaded or self.lstm_model is None:
            return [], []
        if not process_states:
            return [], []
        
        anomalies = []
        
        # Extract sensor features
        df = self._extract_sensor_features(process_states)
        if len(df) < self.window_size:
            return [], []
        
        # Prepare data for LSTM
        sensor_data = df[self.sensor_features].values
        
        # Normalize
        data_mean = sensor_data.mean(axis=0)
        data_std = sensor_data.std(axis=0)
        data_std[data_std == 0] = 1  # Avoid division by zero
        normalized_data = (sensor_data - data_mean) / data_std
        
        # Create sliding windows
        X = []
        for i in range(len(normalized_data) - self.window_size):
            X.append(normalized_data[i:i + self.window_size])
        
        if len(X) == 0:
            return [], []
        
        X = np.array(X)
        
        # Make predictions
        predictions_normalized = self.lstm_model.predict(X, verbose=0)
        
        # Denormalize predictions
        predictions = predictions_normalized * data_std + data_mean
        
        # Compare last prediction with actual value to detect anomalies
        for i in range(len(predictions)):
            actual_idx = i + self.window_size
            if actual_idx >= len(sensor_data):
                break
            
            actual = sensor_data[actual_idx]
            predicted = predictions[i]
            
            # Calculate error
            errors = np.abs(actual - predicted)
            mae = np.mean(errors)
            
            # Detect anomalies based on error threshold
            if mae > 2.0:  # Threshold for anomaly detection
                timestamp = df.iloc[actual_idx]['timestamp']
                
                anomalies.append(MLAnomaly(
                    severity="medium",
                    category="lstm_forecast",
                    description=f"LSTM forecast anomaly: MAE={mae:.2f}",
                    timestamp=timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                    confidence=mae,
                    details={
                        "mean_absolute_error": float(mae),
                        "actual_values": actual.tolist(),
                        "predicted_values": predicted.tolist(),
                        "errors": errors.tolist()
                    }
                ))
        
        # Generate forecast for future steps
        last_window = normalized_data[-self.window_size:]
        forecast_normalized = []
        
        for _ in range(forecast_steps):
            # Predict next step
            next_step = self.lstm_model.predict(
                last_window.reshape(1, self.window_size, len(self.sensor_features)),
                verbose=0
            )
            forecast_normalized.append(next_step[0])
            
            # Update window
            last_window = np.vstack([last_window[1:], next_step])
        
        # Denormalize forecast
        forecast = np.array(forecast_normalized) * data_std + data_mean
        
        # Prepare forecast results
        forecast_results = []
        for i, pred in enumerate(forecast):
            forecast_time = datetime.now() + timedelta(minutes=i * 5)  # Assume 5-minute intervals
            
            forecast_results.append({
                "timestamp": forecast_time.isoformat(),
                "predictions": {feature: float(pred[j]) for j, feature in enumerate(self.sensor_features)},
                "step": i + 1
            })
        
        return forecast_results, anomalies
    
    def analyze_historian(
        self,
        historian: Historian,
        transaction_limit: int = 1000,
        state_limit: int = 500
    ) -> dict[str, Any]:
        """
        Comprehensive ML analysis of historian data.
        
        Args:
            historian: Historian instance
            transaction_limit: Max transactions to analyze
            state_limit: Max process states to analyze
        
        Returns:
            Dictionary with ML analysis results
        """
        if not self.is_loaded:
            return {"error": "ML models not loaded"}
        
        # Get data from historian
        transactions = historian.get_recent_transactions(transaction_limit)
        process_states = historian.get_recent_process_states(state_limit)
        
        # Convert to model objects
        tx_objects = []
        for tx in transactions:
            tx_objects.append(ModbusTransaction(
                timestamp=datetime.fromisoformat(tx["timestamp"]),
                source_ip=tx.get("source_ip", ""),
                function_code=tx["function_code"],
                register_type=RegisterType(tx["register_type"]),
                address=tx["address"],
                count=tx.get("count", 1),
                values=json.loads(tx["values_json"]) if isinstance(tx.get("values_json"), str) else [],
                is_write=bool(tx.get("is_write", 0)),
                is_attack=bool(tx.get("is_attack", 0)),
                attack_type=tx.get("attack_type", "")
            ))
        
        state_objects = []
        for state in process_states:
            state_objects.append(ProcessState(
                timestamp=datetime.fromisoformat(state["timestamp"]),
                tank_level=state["tank_level"],
                inflow_rate=state["inflow_rate"],
                outflow_rate=state["outflow_rate"],
                ph_level=state["ph_level"],
                chlorine_dosing=state["chlorine_dosing"],
                turbidity=state["turbidity"],
                pressure_psi=state["pressure_psi"],
                temperature_c=state["temperature_c"],
                inlet_valve_open=bool(state["inlet_valve_open"]),
                outlet_valve_open=bool(state["outlet_valve_open"]),
                pump_running=bool(state["pump_running"]),
                mixer_running=bool(state["mixer_running"]),
                high_level_alarm=bool(state["high_level_alarm"]),
                low_level_alarm=bool(state["low_level_alarm"]),
                ph_alarm=bool(state["ph_alarm"]),
                pressure_alarm=bool(state["pressure_alarm"])
            ))
        
        # Run ML analysis
        transaction_anomalies = self.detect_transaction_anomalies(tx_objects)
        forecasts, forecast_anomalies = self.forecast_sensor_values(state_objects)
        
        # Combine results
        all_anomalies = transaction_anomalies + forecast_anomalies
        
        # Calculate statistics
        total_transactions = len(tx_objects)
        total_states = len(state_objects)
        anomaly_count = len(all_anomalies)
        
        # Severity breakdown
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        }
        
        for anomaly in all_anomalies:
            severity_counts[anomaly.severity] += 1
        
        return {
            "summary": {
                "total_transactions_analyzed": total_transactions,
                "total_process_states_analyzed": total_states,
                "ml_anomalies_detected": anomaly_count,
                "transaction_anomalies": len(transaction_anomalies),
                "forecast_anomalies": len(forecast_anomalies),
                "severity_breakdown": severity_counts,
                "models_loaded": {
                    "isolation_forest": self.isolation_forest is not None,
                    "lstm": self.lstm_model is not None
                }
            },
            "anomalies": [
                {
                    "severity": a.severity,
                    "category": a.category,
                    "description": a.description,
                    "timestamp": a.timestamp,
                    "confidence": a.confidence,
                    "details": a.details
                }
                for a in all_anomalies[:20]  # Limit output
            ],
            "forecasts": forecasts[:5],  # Limit output
            "recommendations": self._generate_recommendations(all_anomalies)
        }
    
    def _generate_recommendations(self, anomalies: list[MLAnomaly]) -> list[str]:
        """Generate actionable recommendations based on detected anomalies."""
        recommendations = []
        
        critical_count = sum(1 for a in anomalies if a.severity == "critical")
        high_count = sum(1 for a in anomalies if a.severity == "high")
        
        if critical_count > 0:
            recommendations.append(
                f"🔴 Immediate action required: {critical_count} critical anomalies detected"
            )
        
        if high_count > 0:
            recommendations.append(
                f"🟠 High priority: {high_count} high severity anomalies require investigation"
            )
        
        # Check for specific patterns
        isolation_forest_anomalies = [a for a in anomalies if a.category == "isolation_forest"]
        lstm_anomalies = [a for a in anomalies if a.category == "lstm_forecast"]
        
        if isolation_forest_anomalies:
            recommendations.append(
                f"🔍 Review {len(isolation_forest_anomalies)} anomalous transactions for potential attacks"
            )
        
        if lstm_anomalies:
            recommendations.append(
                f"📈 Investigate {len(lstm_anomalies)} sensor forecast deviations for process abnormalities"
            )
        
        if not anomalies:
            recommendations.append("✅ No ML anomalies detected - system appears normal")
        
        return recommendations