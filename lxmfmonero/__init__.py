"""
LXMFMonero - Monero transactions over LXMF/Reticulum mesh networks

Uses LXMF's store-and-forward messaging for reliable delivery over
any Reticulum transport (HF radio, LoRa, I2P, etc.).
"""

__version__ = "0.1.0"
__author__ = "Light Fighter Manifesto L.L.C."

from .wallet_rpc import WalletRPCClient
from .messages import MessageType

__all__ = [
    "WalletRPCClient",
    "MessageType",
    "__version__",
]
