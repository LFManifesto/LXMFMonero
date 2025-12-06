"""
Configuration management for ReticulumXMR
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Manages ReticulumXMR configuration"""

    # Default configuration directory
    CONFIG_DIR = Path.home() / ".reticulumxmr"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    IDENTITY_FILE = CONFIG_DIR / "identity"

    DEFAULT_CONFIG = {
        "identity_name": "reticulumxmr_user",
        "announce_interval": 1800,  # 30 minutes

        # Wallet RPC settings (view-only wallet on hub)
        "monero_rpc_host": "127.0.0.1",
        "monero_rpc_port": 18085,
        "monero_rpc_user": "",
        "monero_rpc_password": "",

        # Daemon settings (monerod on hub)
        "monero_daemon_host": "127.0.0.1",
        "monero_daemon_port": 18081,

        # Other settings
        "auto_announce": True,
        "require_confirmations": 10,
    }

    def __init__(self):
        self.config = self.DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        """Load configuration from file"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
                logger.info(f"Loaded configuration from {self.CONFIG_FILE}")
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                logger.info("Using default configuration")
        else:
            logger.debug(f"No config found at {self.CONFIG_FILE}, using defaults")

    def save(self):
        """Save configuration to file"""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Configuration saved to {self.CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get(self, key, default=None):
        """Get configuration value"""
        return self.config.get(key, default)

    def set(self, key, value):
        """Set configuration value"""
        self.config[key] = value
