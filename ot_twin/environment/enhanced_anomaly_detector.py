"""
Enhanced Anomaly Detector — Combines rule-based and ML-based detection.

This detector uses both traditional rule-based detection (from AnomalyDetector)
and ML-based detection (from MLAnomalyDetector) to provide comprehensive
anomaly detection capabilities.
"""

from __future__ import annotations

from typing import Any, Optional

from ot_twin.environment.anomaly_detector import Anomaly, AnomalyDetector
from ot_twin.environment.historian import Historian
from ot_twin.environment.ml_anomaly_detector import MLAnomaly, MLAnomalyDetector


class EnhancedAnomalyDetector:
    """
    Enhanced anomaly detector that combines rule-based and ML-based detection.
    
    Features:
    1. Rule-based detection (rapid writes, out-of-range, unusual function codes)
    2. ML-based detection (Isolation Forest for transactions, LSTM for forecasting)
    3. Ensemble scoring and ranking
    4. Cross-validation between rule-based and ML-based results
    """
    
    def __init__(
        self,
        use_ml: bool = True,
        write_burst_threshold: int = 10,
        write_burst_window_seconds: float = 5.0,
        allowed_function_codes: Optional[set[int]] = None,
        ml_model_dir: Optional[str] = None
    ):
        # Rule-based detector
        self.rule_detector = AnomalyDetector(
            write_burst_threshold=write_burst_threshold,
            write_burst_window_seconds=write_burst_window_seconds,
            allowed_function_codes=allowed_function_codes
        )
        
        # ML-based detector
        self.use_ml = use_ml
        self.ml_detector = None
        
        if use_ml:
            self.ml_detector = MLAnomalyDetector(model_dir=ml_model_dir)
            self.ml_loaded = self.ml_detector.load_models()
        else:
            self.ml_loaded = False
    
    def analyze(
        self,
        historian: Historian,
        transaction_limit: int = 1000,
        state_limit: int = 500,
        include_forecast: bool = False
    ) -> dict[str, Any]:
        """
        Comprehensive analysis combining rule-based and ML-based detection.
        
        Args:
            historian: Historian instance
            transaction_limit: Max transactions to analyze
            state_limit: Max process states to analyze
            include_forecast: Whether to include LSTM forecasting
        
        Returns:
            Dictionary with combined analysis results
        """
        results = {
            "rule_based": {},
            "ml_based": {},
            "combined": {},
            "recommendations": []
        }
        
        # Rule-based analysis
        rule_anomalies = self.rule_detector.analyze(historian, transaction_limit)
        results["rule_based"] = {
            "anomalies": [
                {
                    "severity": a.severity,
                    "category": a.category,
                    "description": a.description,
                    "timestamp": a.timestamp,
                    "details": a.details
                }
                for a in rule_anomalies[:50]  # Limit output
            ],
            "total_detected": len(rule_anomalies),
            "severity_counts": self._count_severities(rule_anomalies)
        }
        
        # ML-based analysis
        ml_results = {}
        if self.use_ml and self.ml_loaded:
            ml_results = self.ml_detector.analyze_historian(
                historian, 
                transaction_limit, 
                state_limit
            )
            
            if "error" not in ml_results:
                results["ml_based"] = ml_results
                
                # Extract ML anomalies
                ml_anomalies_data = ml_results.get("anomalies", [])
                ml_anomalies = [
                    MLAnomaly(
                        severity=a["severity"],
                        category=a["category"],
                        description=a["description"],
                        timestamp=a["timestamp"],
                        confidence=a["confidence"],
                        details=a["details"]
                    )
                    for a in ml_anomalies_data
                ]
            else:
                ml_anomalies = []
                results["ml_based"] = {"error": ml_results["error"]}
        else:
            ml_anomalies = []
            if self.use_ml:
                results["ml_based"] = {"error": "ML models not loaded"}
            else:
                results["ml_based"] = {"disabled": "ML detection disabled"}
        
        # Combine and cross-validate
        combined_analysis = self._combine_anomalies(rule_anomalies, ml_anomalies)
        results["combined"] = combined_analysis
        
        # Generate recommendations
        all_recommendations = []
        
        # Rule-based recommendations
        if rule_anomalies:
            crit_high = sum(1 for a in rule_anomalies 
                           if a.severity in ["critical", "high"])
            if crit_high > 0:
                all_recommendations.append(
                    f"🔴 Rule-based detection: {crit_high} critical/high priority alerts"
                )
        
        # ML-based recommendations
        if "recommendations" in ml_results:
            all_recommendations.extend(ml_results.get("recommendations", []))
        
        # Cross-validation recommendations
        cross_val = combined_analysis.get("cross_validation", {})
        confirmed_anomalies = cross_val.get("confirmed_by_both", 0)
        if confirmed_anomalies > 0:
            all_recommendations.append(
                f"✅ {confirmed_anomalies} anomalies confirmed by both rule-based and ML detection"
            )
        
        results["recommendations"] = all_recommendations
        
        return results
    
    def _count_severities(self, anomalies: list[Anomaly]) -> dict[str, int]:
        """Count anomalies by severity level."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for anomaly in anomalies:
            counts[anomaly.severity] += 1
        return counts
    
    def _combine_anomalies(
        self, 
        rule_anomalies: list[Anomaly], 
        ml_anomalies: list[MLAnomaly]
    ) -> dict[str, Any]:
        """
        Combine rule-based and ML-based anomalies, identifying overlaps.
        
        Returns a dictionary with combined analysis including:
        - Unique anomalies from each source
        - Anomalies detected by both methods (high confidence)
        - Statistical summary
        """
        # Convert to comparable format
        rule_formatted = [
            {
                "severity": a.severity,
                "category": a.category,
                "timestamp": a.timestamp,
                "description": a.description[:100],  # Truncate for comparison
                "source": "rule"
            }
            for a in rule_anomalies
        ]
        
        ml_formatted = [
            {
                "severity": a.severity,
                "category": a.category,
                "timestamp": a.timestamp,
                "description": a.description[:100],  # Truncate for comparison
                "source": "ml",
                "confidence": a.confidence
            }
            for a in ml_anomalies
        ]
        
        # Find overlaps (same timestamp and similar description)
        confirmed_by_both = []
        rule_only = []
        ml_only = []
        
        for rule_anom in rule_formatted:
            matched = False
            for ml_anom in ml_formatted:
                # Check if same timestamp (within 30 seconds) and similar category
                if (self._time_close(rule_anom["timestamp"], ml_anom["timestamp"]) and
                    self._categories_similar(rule_anom["category"], ml_anom["category"])):
                    
                    confirmed_by_both.append({
                        **rule_anom,
                        "ml_confidence": ml_anom.get("confidence", 0.0),
                        "confirmed_by": "both"
                    })
                    matched = True
                    break
            
            if not matched:
                rule_only.append({**rule_anom, "confirmed_by": "rule_only"})
        
        # Find ML-only anomalies
        for ml_anom in ml_formatted:
            matched = False
            for rule_anom in rule_formatted:
                if (self._time_close(ml_anom["timestamp"], rule_anom["timestamp"]) and
                    self._categories_similar(ml_anom["category"], rule_anom["category"])):
                    matched = True
                    break
            
            if not matched:
                ml_only.append({**ml_anom, "confirmed_by": "ml_only"})
        
        # Calculate statistics
        total_anomalies = len(rule_anomalies) + len(ml_anomalies)
        unique_anomalies = len(rule_only) + len(ml_only) + len(confirmed_by_both)
        
        return {
            "summary": {
                "total_rule_anomalies": len(rule_anomalies),
                "total_ml_anomalies": len(ml_anomalies),
                "total_combined": total_anomalies,
                "unique_anomalies": unique_anomalies,
                "confirmed_by_both": len(confirmed_by_both),
                "rule_only": len(rule_only),
                "ml_only": len(ml_only)
            },
            "cross_validation": {
                "confirmed_by_both": confirmed_by_both[:10],  # Limit output
                "rule_only": rule_only[:10],  # Limit output
                "ml_only": ml_only[:10]  # Limit output
            },
            "severity_distribution": {
                "rule": self._count_severities(rule_anomalies),
                "ml": self._count_ml_severities(ml_anomalies)
            }
        }
    
    def _time_close(self, time1: str, time2: str, threshold_seconds: int = 30) -> bool:
        """Check if two timestamps are close (within threshold seconds)."""
        try:
            from datetime import datetime
            dt1 = datetime.fromisoformat(time1.replace('Z', '+00:00'))
            dt2 = datetime.fromisoformat(time2.replace('Z', '+00:00'))
            diff = abs((dt1 - dt2).total_seconds())
            return diff <= threshold_seconds
        except (ValueError, TypeError):
            return False
    
    def _categories_similar(self, cat1: str, cat2: str) -> bool:
        """Check if two anomaly categories are similar."""
        # Map categories to broader groups
        category_groups = {
            # Rule-based categories
            "rapid_writes": "transaction_pattern",
            "out_of_range": "value_anomaly",
            "unusual_fc": "protocol_anomaly",
            "known_attack": "security",
            # ML-based categories
            "isolation_forest": "transaction_pattern",
            "lstm_forecast": "value_anomaly",
            "ensemble": "combined"
        }
        
        group1 = category_groups.get(cat1, "other")
        group2 = category_groups.get(cat2, "other")
        
        return group1 == group2
    
    def _count_ml_severities(self, anomalies: list[MLAnomaly]) -> dict[str, int]:
        """Count ML anomalies by severity level."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for anomaly in anomalies:
            counts[anomaly.severity] += 1
        return counts
    
    def get_detection_capabilities(self) -> dict[str, Any]:
        """Return information about available detection capabilities."""
        capabilities = {
            "rule_based": {
                "enabled": True,
                "detection_types": [
                    "rapid_write_bursts",
                    "out_of_range_values",
                    "unusual_function_codes",
                    "known_attack_patterns"
                ]
            },
            "ml_based": {
                "enabled": self.use_ml,
                "models_loaded": self.ml_loaded,
                "detection_types": []
            }
        }
        
        if self.ml_loaded and self.ml_detector:
            capabilities["ml_based"]["detection_types"].append("isolation_forest_transactions")
            
            if self.ml_detector.lstm_model is not None:
                capabilities["ml_based"]["detection_types"].append("lstm_sensor_forecasting")
                capabilities["ml_based"]["detection_types"].append("time_series_anomalies")
        
        return capabilities