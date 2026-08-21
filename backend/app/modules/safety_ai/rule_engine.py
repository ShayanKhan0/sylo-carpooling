"""
Rule Engine for Safety AI

Supports YAML and database-driven configurable rules with hot reload capability.
"""

import logging
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Configurable rule engine for safety AI thresholds and parameters.
    
    Supports loading from YAML file and runtime reloading.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize rule engine.
        
        Args:
            config_path: Path to YAML config file (default: safety_rules.yaml)
        """
        self.config_path = config_path or "safety_rules.yaml"
        self.rules: Dict[str, Any] = {}
        self.last_loaded: Optional[datetime] = None
        self.default_rules = {
            # Off-route detection
            "off_route_threshold_m": 60,
            "off_route_min_consecutive": 3,
            "off_route_min_seconds": 15,
            
            # Stop detection
            "stop_minutes": 3,
            "stop_speed_threshold_kmh": 1.0,
            
            # Overspeed detection
            "overspeed_kmh": 120,
            "overspeed_high_kmh": 140,
            
            # ML settings
            "ml_sensitivity": 0.7,
            "ml_enabled": True,
            "ml_model_type": "isolation_forest",
            
            # False positive suppression
            "false_positive_min_seconds": 15,
            "false_positive_min_consecutive": 3,
            
            # Polyline settings
            "polyline_max_alternates": 5,
            "polyline_cache_ttl_hours": 24,
            
            # Escalation settings
            "escalation_stage1_timeout_seconds": 60,
            "escalation_stage2_timeout_seconds": 300,
            "escalation_auto_admin_severity": "high",
            
            # Rapid direction change
            "rapid_direction_change_degrees": 45,
            "rapid_direction_change_seconds": 5,
            
            # Driver offline
            "driver_offline_seconds": 180,
        }
        
        self.load_rules()
    
    def load_rules(self) -> bool:
        """
        Load rules from YAML file, fallback to defaults.
        
        Returns:
            True if loaded successfully
        """
        try:
            config_file = Path(self.config_path)
            
            if config_file.exists():
                with open(config_file, 'r') as f:
                    loaded_rules = yaml.safe_load(f)
                    
                if loaded_rules and isinstance(loaded_rules, dict):
                    # Merge with defaults
                    self.rules = {**self.default_rules, **loaded_rules}
                    self.last_loaded = datetime.utcnow()
                    logger.info(f"✅ Loaded {len(self.rules)} rules from {self.config_path}")
                    return True
                else:
                    logger.warning(f"⚠️ Empty or invalid YAML in {self.config_path}, using defaults")
                    self.rules = self.default_rules.copy()
                    return False
            else:
                logger.warning(f"⚠️ Config file {self.config_path} not found, using defaults")
                self.rules = self.default_rules.copy()
                self.last_loaded = datetime.utcnow()
                return False
                
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML: {e}")
            self.rules = self.default_rules.copy()
            return False
        
        except Exception as e:
            logger.error(f"Failed to load rules: {e}", exc_info=True)
            self.rules = self.default_rules.copy()
            return False
    
    def reload_rules(self) -> bool:
        """
        Hot reload rules from config file.
        
        Returns:
            True if reloaded successfully
        """
        logger.info(f"🔄 Reloading safety AI rules from {self.config_path}")
        return self.load_rules()
    
    def get_rule_value(self, key: str, default: Any = None) -> Any:
        """
        Get rule value by key.
        
        Args:
            key: Rule key
            default: Default value if key not found
            
        Returns:
            Rule value or default
        """
        return self.rules.get(key, default)
    
    def set_rule_value(self, key: str, value: Any):
        """
        Set rule value at runtime (not persisted).
        
        Args:
            key: Rule key
            value: New value
        """
        self.rules[key] = value
        logger.info(f"Updated rule {key} = {value}")
    
    def get_all_rules(self) -> Dict[str, Any]:
        """Get all current rules"""
        return self.rules.copy()
    
    def get_defaults(self) -> Dict[str, Any]:
        """Get default rules"""
        return self.default_rules.copy()
    
    def save_to_yaml(self, output_path: Optional[str] = None) -> bool:
        """
        Save current rules to YAML file.
        
        Args:
            output_path: Output file path (default: config_path)
            
        Returns:
            True if saved successfully
        """
        try:
            output = output_path or self.config_path
            output_file = Path(output)
            
            # Create parent directory if needed
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w') as f:
                yaml.dump(self.rules, f, default_flow_style=False, sort_keys=True)
            
            logger.info(f"✅ Saved rules to {output}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save rules: {e}", exc_info=True)
            return False


# Global rule engine instance
_rule_engine_instance: Optional[RuleEngine] = None


def get_rule_engine(config_path: Optional[str] = None) -> RuleEngine:
    """
    Get global rule engine instance (singleton).
    
    Args:
        config_path: Config file path (only used on first call)
        
    Returns:
        RuleEngine instance
    """
    global _rule_engine_instance
    
    if _rule_engine_instance is None:
        _rule_engine_instance = RuleEngine(config_path)
    
    return _rule_engine_instance


def reload_rules() -> bool:
    """
    Reload rules from config file (convenience function).
    
    Returns:
        True if reloaded successfully
    """
    engine = get_rule_engine()
    return engine.reload_rules()


def get_rule(key: str, default: Any = None) -> Any:
    """
    Get rule value (convenience function).
    
    Args:
        key: Rule key
        default: Default value
        
    Returns:
        Rule value
    """
    engine = get_rule_engine()
    return engine.get_rule_value(key, default)
