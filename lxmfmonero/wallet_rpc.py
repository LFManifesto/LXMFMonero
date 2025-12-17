"""
Monero wallet-rpc JSON-RPC client

Provides interface to monero-wallet-rpc for both view-only wallets (hub)
and cold wallets (client).
"""

import requests
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class WalletRPCClient:
    """
    Simple wallet-rpc JSON-RPC client

    Extracted from ReticulumXMR hub_cold_signing.py for reuse in LXMF-based
    implementation.
    """

    def __init__(self, url: str = "http://127.0.0.1:18082/json_rpc", timeout: int = 120):
        """
        Initialize wallet RPC client

        Args:
            url: wallet-rpc endpoint URL
            timeout: Request timeout in seconds
        """
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()

    def call(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make RPC call to wallet-rpc

        Args:
            method: RPC method name
            params: Optional parameters dict

        Returns:
            Dict with either "result" or "error" key
        """
        payload = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": method,
            "params": params or {}
        }
        try:
            response = self.session.post(self.url, json=payload, timeout=self.timeout)
            result = response.json()
            if "error" in result:
                return {"error": result["error"]}
            return {"result": result.get("result", {})}
        except requests.exceptions.Timeout:
            return {"error": {"code": -1, "message": "RPC timeout"}}
        except requests.exceptions.ConnectionError as e:
            return {"error": {"code": -2, "message": f"Connection error: {e}"}}
        except Exception as e:
            return {"error": {"code": -3, "message": str(e)}}

    # Convenience methods for common operations

    def get_version(self) -> Dict[str, Any]:
        """Get wallet-rpc version"""
        return self.call("get_version")

    def get_balance(self) -> Dict[str, Any]:
        """Get wallet balance"""
        return self.call("get_balance")

    def get_height(self) -> Dict[str, Any]:
        """Get current blockchain height"""
        return self.call("get_height")

    def get_address(self) -> Dict[str, Any]:
        """Get wallet address"""
        return self.call("get_address")

    def refresh(self) -> Dict[str, Any]:
        """Refresh wallet from blockchain"""
        return self.call("refresh")

    # View-only wallet methods (Hub side)

    def export_outputs(self, all_outputs: bool = True) -> Dict[str, Any]:
        """
        Export outputs for cold wallet import

        Args:
            all_outputs: Export all outputs or just new ones

        Returns:
            Dict with outputs_data_hex
        """
        return self.call("export_outputs", {"all": all_outputs})

    def transfer(self, destinations: List[Dict], priority: int = 1,
                 do_not_relay: bool = True, get_tx_metadata: bool = True) -> Dict[str, Any]:
        """
        Create transaction (unsigned if view-only wallet)

        Args:
            destinations: List of {"address": str, "amount": int} (atomic units)
            priority: Transaction priority (0-3)
            do_not_relay: If True, don't broadcast (for cold signing)
            get_tx_metadata: Include tx metadata in response

        Returns:
            Dict with unsigned_txset, fee, etc.
        """
        return self.call("transfer", {
            "destinations": destinations,
            "priority": priority,
            "do_not_relay": do_not_relay,
            "get_tx_metadata": get_tx_metadata
        })

    def submit_transfer(self, tx_data_hex: str) -> Dict[str, Any]:
        """
        Submit signed transaction to network

        Args:
            tx_data_hex: Signed transaction data

        Returns:
            Dict with tx_hash_list
        """
        return self.call("submit_transfer", {"tx_data_hex": tx_data_hex})

    def relay_tx(self, hex_data: str) -> Dict[str, Any]:
        """
        Relay transaction (fallback method)

        Args:
            hex_data: Transaction hex

        Returns:
            Dict with tx_hash
        """
        return self.call("relay_tx", {"hex": hex_data})

    def import_key_images(self, signed_key_images: List[Dict],
                          offset: int = 0) -> Dict[str, Any]:
        """
        Import key images from cold wallet

        Args:
            signed_key_images: List of signed key image dicts
            offset: Starting offset

        Returns:
            Dict with height, spent, unspent
        """
        return self.call("import_key_images", {
            "signed_key_images": signed_key_images,
            "offset": offset
        })

    # Cold wallet methods (Client side)

    def import_outputs(self, outputs_data_hex: str) -> Dict[str, Any]:
        """
        Import outputs from view-only wallet

        Args:
            outputs_data_hex: Hex-encoded outputs data

        Returns:
            Dict with num_imported
        """
        return self.call("import_outputs", {"outputs_data_hex": outputs_data_hex})

    def sign_transfer(self, unsigned_txset: str) -> Dict[str, Any]:
        """
        Sign unsigned transaction with spend key

        Args:
            unsigned_txset: Unsigned transaction set from view-only wallet

        Returns:
            Dict with signed_txset, tx_hash_list
        """
        return self.call("sign_transfer", {"unsigned_txset": unsigned_txset})

    def export_key_images(self, all_images: bool = True) -> Dict[str, Any]:
        """
        Export key images for view-only wallet import

        Args:
            all_images: Export all key images or just new ones

        Returns:
            Dict with signed_key_images
        """
        return self.call("export_key_images", {"all": all_images})

    # Wallet management

    def open_wallet(self, filename: str, password: str = "") -> Dict[str, Any]:
        """
        Open a wallet file

        Args:
            filename: Wallet filename
            password: Wallet password
        """
        return self.call("open_wallet", {
            "filename": filename,
            "password": password
        })

    def generate_from_keys(self, filename: str, address: str, viewkey: str,
                           password: str = "", restore_height: int = 0,
                           spendkey: str = None) -> Dict[str, Any]:
        """
        Create wallet from keys

        Args:
            filename: Wallet filename
            address: Wallet address
            viewkey: View key
            password: Wallet password
            restore_height: Blockchain height to start scanning
            spendkey: Spend key (omit for view-only wallet)
        """
        params = {
            "filename": filename,
            "address": address,
            "viewkey": viewkey,
            "password": password,
            "restore_height": restore_height,
            "autosave_current": True
        }
        if spendkey:
            params["spendkey"] = spendkey
        return self.call("generate_from_keys", params)


def test_connection(url: str = "http://127.0.0.1:18082/json_rpc") -> bool:
    """
    Test connection to wallet-rpc

    Args:
        url: wallet-rpc endpoint URL

    Returns:
        True if connected successfully
    """
    client = WalletRPCClient(url)
    result = client.get_version()

    if "error" in result:
        logger.error(f"Cannot connect to wallet-rpc: {result['error']}")
        return False

    version = result.get("result", {}).get("version", 0)
    logger.info(f"Connected to wallet-rpc version: {version}")
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    print("Testing wallet-rpc connection...")
    if test_connection():
        print("wallet-rpc is available")
    else:
        print("wallet-rpc is not available")
        print("Start with: monero-wallet-rpc --wallet-dir <dir> --rpc-bind-port 18082 --disable-rpc-login")
