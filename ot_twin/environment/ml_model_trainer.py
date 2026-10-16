"""
ML Model Trainer — Trains Isolation Forest and LSTM models from historian data.
"""

from __future__ import annotations

import json
import pickle
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from tensorflow import keras
from tensorflow.keras import layers

from ot_twin.config import PROJECT_ROOT
from ot_twin.environment.historian import Historian
from ot_twin.models import RegisterType

warnings.filterwarnings('ignore', category=UserWarning)


class MLModelTrainer:
    """Trains ML models from historian data."""
    
    def __init__(self, historian: Historian, model_dir: str | None = None):
        self.historian = historian
        self.model_dir = Path(model_dir) if model_dir else PROJECT_ROOT
        
        self.transaction_features = [
            'function_code', 'register_type_code', 'address', 'count',
            'is_write', 'hour_of_day', 'minute_of_hour', 'value_mean', 'value_std'
        ]
        
        self.sensor_features = [
            'tank_level', 'ph_level', 'chlorine_dosing', 'pressure_psi',
            'temperature_c', 'turbidity', 'inflow_rate', 'outflow_rate'
        ]
    
    def train_isolation_forest(
        self,
        sample_size: int = 10000,
        contamination: float = 0.1,
        n_estimators: int = 100
    ) -> bool:
        """Train Isolation Forest model on transaction data."""
        try:
            print(f"Fetching transaction data (max {sample_size} records)...")
            transactions = self.historian.get_recent_transactions(sample_size)
            
            if len(transactions) < 100:
                print(f"⚠ Only {len(transactions)} transactions available (need at least 100)")
                return False
            
            print(f"Processing {len(transactions)} transactions...")
            
            # Extract features
            features = []
            for tx in transactions:
                register_type_code = {
                    'holding_register': 0,
                    'input_register': 1,
                    'coil': 2,
                    'discrete_input': 3
                }.get(tx.get("register_type", "holding_register"), 0)
                
                try:
                    dt = datetime.fromisoformat(tx.get("timestamp", datetime.now().isoformat()))
                except (ValueError, TypeError):
                    dt = datetime.now()
                
                values_json = tx.get("values_json", "[]")
                try:
                    values = json.loads(values_json) if isinstance(values_json, str) else values_json
                except (json.JSONDecodeError, TypeError):
                    values = []
                
                feature_vector = {
                    'function_code': tx.get("function_code", 0),
                    'register_type_code': register_type_code,
                    'address': tx.get("address", 0),
                    'count': tx.get("count", 1),
                    'is_write': 1 if tx.get("is_write") else 0,
                    'hour_of_day': dt.hour,
                    'minute_of_hour': dt.minute,
                    'value_mean': np.mean(values) if values else 0,
                    'value_std': np.std(values) if len(values) > 1 else 0
                }
                
                features.append(feature_vector)
            
            df = pd.DataFrame(features)
            
            # Normalize
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(df[self.transaction_features])
            
            # Train model
            print(f"Training Isolation Forest ({n_estimators} estimators, contamination={contamination})...")
            model = IsolationForest(
                n_estimators=n_estimators,
                contamination=contamination,
                random_state=42,
                n_jobs=-1
            )
            model.fit(features_scaled)
            
            # Save model
            model_path = self.model_dir / "isolation_forest_model.pkl"
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
            
            print(f"✓ Isolation Forest saved to {model_path}")
            return True
            
        except Exception as e:
            print(f"✗ Error training Isolation Forest: {e}")
            return False
    
    def train_lstm(
        self,
        sample_size: int = 10000,
        window_size: int = 10,
        epochs: int = 50,
        batch_size: int = 32
    ) -> bool:
        """Train LSTM model on sensor time-series data."""
        try:
            print(f"Fetching process state data (max {sample_size} records)...")
            states = self.historian.get_recent_process_states(sample_size)
            
            if len(states) < window_size * 2:
                print(f"⚠ Only {len(states)} states available (need at least {window_size * 2})")
                return False
            
            print(f"Processing {len(states)} process states...")
            
            # Extract sensor data
            data = []
            for state in states:
                try:
                    data_point = {
                        'tank_level': float(state.get("tank_level", 50.0)),
                        'ph_level': float(state.get("ph_level", 7.0)),
                        'chlorine_dosing': float(state.get("chlorine_dosing", 1.5)),
                        'pressure_psi': float(state.get("pressure_psi", 45.0)),
                        'temperature_c': float(state.get("temperature_c", 22.0)),
                        'turbidity': float(state.get("turbidity", 0.5)),
                        'inflow_rate': float(state.get("inflow_rate", 10.0)),
                        'outflow_rate': float(state.get("outflow_rate", 10.0))
                    }
                    data.append(data_point)
                except (ValueError, TypeError):
                    continue
            
            if len(data) < window_size * 2:
                print(f"✗ Insufficient valid data points: {len(data)}")
                return False
            
            df = pd.DataFrame(data)
            sensor_data = df[self.sensor_features].values
            
            # Normalize
            data_mean = sensor_data.mean(axis=0)
            data_std = sensor_data.std(axis=0)
            data_std[data_std == 0] = 1
            normalized_data = (sensor_data - data_mean) / data_std
            
            # Create windowed sequences
            X, y = [], []
            for i in range(len(normalized_data) - window_size):
                X.append(normalized_data[i:i + window_size])
                y.append(normalized_data[i + window_size])
            
            X = np.array(X)
            y = np.array(y)
            
            if len(X) < 32:
                print(f"✗ Insufficient sequences: {len(X)}")
                return False
            
            print(f"Training LSTM ({len(X)} sequences, window={window_size})...")
            
            # Build LSTM model
            model = keras.Sequential([
                layers.LSTM(64, input_shape=(window_size, len(self.sensor_features)), 
                           activation='relu', return_sequences=True),
                layers.Dropout(0.2),
                layers.LSTM(32, activation='relu'),
                layers.Dropout(0.2),
                layers.Dense(16, activation='relu'),
                layers.Dense(len(self.sensor_features))
            ])
            
            model.compile(optimizer='adam', loss='mse', metrics=['mae'])
            
            # Train
            history = model.fit(
                X, y,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=0.2,
                verbose=0
            )
            
            # Save model
            model_path = self.model_dir / "lstm.h5"
            model.save(model_path)
            
            print(f"✓ LSTM saved to {model_path}")
            print(f"  Final loss: {history.history['loss'][-1]:.4f}")
            
            return True
            
        except Exception as e:
            print(f"✗ Error training LSTM: {e}")
            return False
