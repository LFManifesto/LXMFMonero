"""
ReticulumXMR - Monero payments over Reticulum mesh networks
Community currency system for resilient, sovereign transactions
"""

__version__ = "0.1.0"
__author__ = "Light Fighter Manifesto"
__license__ = "MIT"

from .hub import ReticulumXMRHub
from .client import ReticulumXMRClient

__all__ = ["ReticulumXMRHub", "ReticulumXMRClient"]
