#!/usr/bin/env python3
"""
Hub Cold Signing Session Handler for ReticulumXMR

This component manages view-only wallets on the hub and handles cold signing
protocol messages from clients.

Architecture:
    Client (has spend key) → RNS Channel → Hub (has view key)
        → wallet-rpc (view-only wallet)
        → monerod (blockchain)

The hub:
- Manages view-only wallets for registered operators
- Creates unsigned transactions on request
- Submits signed transactions to the network
- Exports outputs for client cold wallet setup
- Imports key images for accurate balance tracking
"""
import RNS
import requests
import time
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from .view_key_protocol import (
    register_view_key_messages,
    ProvisionWalletMessage,
    ProvisionAckMessage,
    BalanceRequestMessage,
    BalanceResponseMessage,
    CreateTransactionMessage,
    UnsignedTransactionMessage,
    SignedTransactionMessage,
    TransactionResultMessage,
    ExportOutputsRequestMessage,
    ExportOutputsResponseMessage,
    ImportKeyImagesMessage,
    ImportKeyImagesResponseMessage,
    ViewKeyStatusMessage,
)

logger = logging.getLogger(__name__)


class WalletRPCClient:
    """Simple wallet-rpc JSON-RPC client"""

    def __init__(self, url: str = "http://127.0.0.1:18082/json_rpc"):
        self.url = url
        self.session = requests.Session()

    def call(self, method: str, params: dict = None) -> dict:
        """Make RPC call to wallet-rpc"""
        payload = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": method,
            "params": params or {}
        }
        try:
            response = self.session.post(self.url, json=payload, timeout=120)
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


class HubColdSigningSession:
    """
    Cold signing session handler for one client connection

    Each client that connects gets one of these sessions. The session
    handles all view-key protocol messages and interacts with wallet-rpc.
    """

    def __init__(self, link: RNS.Link, wallet_rpc_url: str = "http://127.0.0.1:18082/json_rpc",
                 wallet_dir: Path = None):
        """
        Args:
            link: RNS Link to client
            wallet_rpc_url: URL of wallet-rpc instance
            wallet_dir: Directory for wallet files
        """
        self.link = link
        self.channel = link.get_channel()
        self.wallet_rpc = WalletRPCClient(wallet_rpc_url)
        self.wallet_dir = wallet_dir or Path.home() / ".reticulumxmr" / "wallets"
        self.wallet_dir.mkdir(parents=True, exist_ok=True)

        # Get client identity
        remote_identity = link.get_remote_identity()
        if remote_identity:
            self.client_identity = RNS.hexrep(remote_identity.hash, delimit=False)
        else:
            self.client_identity = RNS.hexrep(link.hash, delimit=False)

        # Session state
        self.current_operator_id: Optional[str] = None
        self.current_wallet_name: Optional[str] = None
        self.start_time = time.time()
        self.message_count = 0

        # Register message types
        register_view_key_messages(self.channel)

        # Add message handler
        self.channel.add_message_handler(self._handle_message)

        logger.info(f"[HubColdSigning] Session started for {self.client_identity[:16]}...")

    def _handle_message(self, message) -> bool:
        """Handle incoming message from client"""
        self.message_count += 1
        msg_type = type(message).__name__
        logger.debug(f"Received message #{self.message_count}: {msg_type}")

        try:
            if isinstance(message, ProvisionWalletMessage):
                self._handle_provision_wallet(message)
                return True
            elif isinstance(message, BalanceRequestMessage):
                logger.info(f"Processing BalanceRequest from {message.operator_id}")
                self._handle_balance_request(message)
                return True
            elif isinstance(message, CreateTransactionMessage):
                self._handle_create_transaction(message)
                return True
            elif isinstance(message, SignedTransactionMessage):
                self._handle_signed_transaction(message)
                return True
            elif isinstance(message, ExportOutputsRequestMessage):
                logger.info(f"Processing ExportOutputs from {message.operator_id}")
                self._handle_export_outputs(message)
                return True
            elif isinstance(message, ImportKeyImagesMessage):
                self._handle_import_key_images(message)
                return True
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                return False

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            return False

    def _handle_provision_wallet(self, msg: ProvisionWalletMessage):
        """
        Handle wallet provisioning request

        Creates a view-only wallet from provided view key and address.
        """
        logger.info(f"[HubColdSigning] Provisioning wallet for operator: {msg.operator_id}")

        # Generate unique wallet name
        wallet_name = f"viewonly_{msg.operator_id}_{int(time.time())}"

        # Create view-only wallet via RPC
        result = self.wallet_rpc.call("generate_from_keys", {
            "filename": wallet_name,
            "address": msg.wallet_address,
            "viewkey": msg.view_key,
            # NO spendkey - makes it view-only
            "password": "",  # Can be configured
            "restore_height": msg.restore_height,
            "autosave_current": True
        })

        if "error" in result:
            error_msg = result["error"].get("message", str(result["error"]))
            logger.error(f"[HubColdSigning] Failed to provision wallet: {error_msg}")
            response = ProvisionAckMessage(
                success=False,
                operator_id=msg.operator_id,
                error=error_msg
            )
        else:
            # Store operator info
            self.current_operator_id = msg.operator_id
            self.current_wallet_name = wallet_name

            # Save mapping for persistence
            self._save_operator_mapping(msg.operator_id, wallet_name, msg.wallet_address)

            logger.info(f"[HubColdSigning] Wallet provisioned: {wallet_name}")
            response = ProvisionAckMessage(
                success=True,
                operator_id=msg.operator_id,
                status=f"View-only wallet created: {wallet_name}"
            )

        self.channel.send(response)

    def _handle_balance_request(self, msg: BalanceRequestMessage):
        """Handle balance query request"""
        logger.info(f"Balance request from: {msg.operator_id}")

        # Ensure correct wallet is open
        if not self._ensure_wallet_open(msg.operator_id):
            logger.warning(f"No wallet for operator {msg.operator_id}")
            response = BalanceResponseMessage(
                success=False,
                request_id=msg.request_id,
                error="Wallet not found for operator"
            )
            self.channel.send(response)
            return

        # Refresh wallet to get latest state
        refresh_result = self.wallet_rpc.call("refresh")
        if "error" in refresh_result:
            logger.warning(f"[HubColdSigning] Refresh warning: {refresh_result['error']}")

        # Get balance
        result = self.wallet_rpc.call("get_balance")

        if "error" in result:
            error_msg = result["error"].get("message", str(result["error"]))
            response = BalanceResponseMessage(
                success=False,
                request_id=msg.request_id,
                error=error_msg
            )
        else:
            balance_data = result.get("result", {})
            balance_atomic = balance_data.get("balance", 0)
            unlocked_atomic = balance_data.get("unlocked_balance", 0)

            # Get current height
            height_result = self.wallet_rpc.call("get_height")
            height = height_result.get("result", {}).get("height", 0)

            response = BalanceResponseMessage(
                success=True,
                request_id=msg.request_id,
                balance=balance_atomic / 1e12,
                unlocked_balance=unlocked_atomic / 1e12,
                balance_atomic=balance_atomic,
                block_height=height,
                blocks_to_unlock=balance_data.get("blocks_to_unlock", 0)
            )

        self.channel.send(response)

    def _handle_create_transaction(self, msg: CreateTransactionMessage):
        """
        Handle unsigned transaction creation request

        Creates a transaction but does not relay it - returns unsigned_txset
        for client to sign with their spend key.
        """
        logger.info(f"[HubColdSigning] Create tx request: {msg.amount} XMR to {msg.destination[:20]}...")

        # Ensure correct wallet is open
        if not self._ensure_wallet_open(msg.operator_id):
            response = UnsignedTransactionMessage(
                success=False,
                request_id=msg.request_id,
                error="Wallet not found for operator"
            )
            self.channel.send(response)
            return

        # Convert XMR to atomic units
        amount_atomic = int(msg.amount * 1e12)

        # Create transaction with do_not_relay=true
        result = self.wallet_rpc.call("transfer", {
            "destinations": [{
                "amount": amount_atomic,
                "address": msg.destination
            }],
            "priority": msg.priority,
            "do_not_relay": True,
            "get_tx_metadata": True
        })

        if "error" in result:
            error_msg = result["error"].get("message", str(result["error"]))
            logger.error(f"[HubColdSigning] Failed to create tx: {error_msg}")
            response = UnsignedTransactionMessage(
                success=False,
                request_id=msg.request_id,
                error=error_msg
            )
        else:
            tx_data = result.get("result", {})

            # Get the unsigned_txset for cold signing
            unsigned_txset = tx_data.get("unsigned_txset", "")
            if not unsigned_txset:
                # Fallback to tx_metadata if unsigned_txset not present
                unsigned_txset = tx_data.get("tx_metadata", "")

            fee_atomic = tx_data.get("fee", 0)

            response = UnsignedTransactionMessage(
                success=True,
                request_id=msg.request_id,
                unsigned_tx=unsigned_txset,
                tx_key=tx_data.get("tx_key", ""),
                fee=fee_atomic / 1e12,
                total=(amount_atomic + fee_atomic) / 1e12,
                destinations=[{
                    "address": msg.destination,
                    "amount": msg.amount
                }]
            )

            logger.info(f"[HubColdSigning] Unsigned tx created, size: {len(unsigned_txset)} chars")

        self.channel.send(response)

    def _handle_signed_transaction(self, msg: SignedTransactionMessage):
        """
        Handle signed transaction submission

        Takes signed_txset from client and broadcasts to network.
        Supports both cold-signed transactions (signed_txset) and raw tx blobs.
        """
        logger.info(f"[HubColdSigning] Submitting signed tx for request: {msg.request_id}")

        # Ensure correct wallet is open
        if not self._ensure_wallet_open(msg.operator_id):
            response = TransactionResultMessage(
                success=False,
                request_id=msg.request_id,
                error="Wallet not found for operator"
            )
            self.channel.send(response)
            return

        tx_hash = None
        error_msg = None

        # Try submit_transfer first (for cold-signed transactions)
        result = self.wallet_rpc.call("submit_transfer", {
            "tx_data_hex": msg.signed_tx
        })

        if "error" not in result:
            tx_result = result.get("result", {})
            tx_hash_list = tx_result.get("tx_hash_list", [])
            tx_hash = tx_hash_list[0] if tx_hash_list else ""
        else:
            # Try relay_tx as fallback (for transactions created with do_not_relay)
            logger.info("[HubColdSigning] submit_transfer failed, trying relay_tx...")
            result = self.wallet_rpc.call("relay_tx", {
                "hex": msg.signed_tx
            })

            if "error" not in result:
                tx_hash = result.get("result", {}).get("tx_hash", "")
            else:
                error_msg = result["error"].get("message", str(result["error"]))
                logger.error(f"[HubColdSigning] Failed to submit tx: {error_msg}")

        if tx_hash:
            logger.info(f"[HubColdSigning] Transaction broadcast: {tx_hash}")
            response = TransactionResultMessage(
                success=True,
                request_id=msg.request_id,
                tx_hash=tx_hash,
                status="broadcast"
            )
        else:
            response = TransactionResultMessage(
                success=False,
                request_id=msg.request_id,
                error=error_msg or "Unknown error"
            )

        self.channel.send(response)

    def _handle_export_outputs(self, msg: ExportOutputsRequestMessage):
        """
        Handle outputs export request

        Exports outputs for client to import into their cold wallet.
        This is needed before the cold wallet can sign transactions.
        """
        logger.info(f"[HubColdSigning] Export outputs request from: {msg.operator_id}")

        # Ensure correct wallet is open
        if not self._ensure_wallet_open(msg.operator_id):
            response = ExportOutputsResponseMessage(
                success=False,
                request_id=msg.request_id,
                error="Wallet not found for operator"
            )
            self.channel.send(response)
            return

        # Export outputs
        result = self.wallet_rpc.call("export_outputs", {
            "all": msg.all_outputs
        })

        if "error" in result:
            error_msg = result["error"].get("message", str(result["error"]))
            response = ExportOutputsResponseMessage(
                success=False,
                request_id=msg.request_id,
                error=error_msg
            )
        else:
            outputs_data = result.get("result", {})
            outputs_hex = outputs_data.get("outputs_data_hex", "")

            logger.info(f"[HubColdSigning] Exported outputs: {len(outputs_hex)} chars")

            response = ExportOutputsResponseMessage(
                success=True,
                request_id=msg.request_id,
                outputs_data_hex=outputs_hex
            )

        self.channel.send(response)

    def _handle_import_key_images(self, msg: ImportKeyImagesMessage):
        """
        Handle key images import from client

        Client exports key images from their cold wallet (which has spend key)
        and sends them to hub. Hub imports them into view-only wallet to
        accurately track spent outputs and balance.
        """
        logger.info(f"[HubColdSigning] Import key images from: {msg.operator_id}")

        # Ensure correct wallet is open
        if not self._ensure_wallet_open(msg.operator_id):
            response = ImportKeyImagesResponseMessage(
                success=False,
                request_id=msg.request_id,
                error="Wallet not found for operator"
            )
            self.channel.send(response)
            return

        # Import key images
        result = self.wallet_rpc.call("import_key_images", {
            "signed_key_images": msg.signed_key_images,
            "offset": msg.offset
        })

        if "error" in result:
            error_msg = result["error"].get("message", str(result["error"]))
            response = ImportKeyImagesResponseMessage(
                success=False,
                request_id=msg.request_id,
                error=error_msg
            )
        else:
            import_data = result.get("result", {})

            logger.info(f"[HubColdSigning] Imported key images, spent: {import_data.get('spent', 0)}")

            response = ImportKeyImagesResponseMessage(
                success=True,
                request_id=msg.request_id,
                height=import_data.get("height", 0),
                spent=import_data.get("spent", 0),
                unspent=import_data.get("unspent", 0)
            )

        self.channel.send(response)

    def _ensure_wallet_open(self, operator_id: str) -> bool:
        """
        Ensure the correct wallet is open for the operator

        Returns True if wallet is open, False otherwise.
        """
        # Check if we need to open a different wallet
        if self.current_operator_id == operator_id and self.current_wallet_name:
            return True

        # Look up wallet name for operator
        wallet_name = self._get_wallet_for_operator(operator_id)
        if not wallet_name:
            # Try using the currently open wallet (for testing/simple setups)
            result = self.wallet_rpc.call("get_address")
            if "error" not in result and result.get("result", {}).get("address"):
                logger.info(f"[HubColdSigning] Using currently open wallet for operator: {operator_id}")
                self.current_operator_id = operator_id
                self.current_wallet_name = "default"
                return True
            logger.warning(f"[HubColdSigning] No wallet found for operator: {operator_id}")
            return False

        # Open the wallet
        result = self.wallet_rpc.call("open_wallet", {
            "filename": wallet_name,
            "password": ""
        })

        if "error" in result:
            logger.error(f"[HubColdSigning] Failed to open wallet: {result['error']}")
            return False

        self.current_operator_id = operator_id
        self.current_wallet_name = wallet_name
        logger.info(f"[HubColdSigning] Opened wallet: {wallet_name}")
        return True

    def _save_operator_mapping(self, operator_id: str, wallet_name: str, address: str):
        """Save operator to wallet mapping for persistence"""
        mapping_file = self.wallet_dir / "operator_wallets.json"

        mappings = {}
        if mapping_file.exists():
            try:
                mappings = json.load(open(mapping_file))
            except Exception:
                pass

        mappings[operator_id] = {
            "wallet_name": wallet_name,
            "address": address,
            "created": time.time()
        }

        json.dump(mappings, open(mapping_file, "w"), indent=2)

    def _get_wallet_for_operator(self, operator_id: str) -> Optional[str]:
        """Look up wallet name for operator"""
        mapping_file = self.wallet_dir / "operator_wallets.json"

        if not mapping_file.exists():
            return None

        try:
            mappings = json.load(open(mapping_file))
            operator_data = mappings.get(operator_id, {})
            return operator_data.get("wallet_name")
        except Exception:
            return None

    def send_status_update(self, event_type: str, message: str,
                           tx_hash: str = None, amount: float = 0.0):
        """Send status update to client"""
        if not self.current_operator_id:
            return

        status_msg = ViewKeyStatusMessage(
            operator_id=self.current_operator_id,
            event_type=event_type,
            tx_hash=tx_hash,
            amount=amount,
            message=message
        )
        self.channel.send(status_msg)

    def get_stats(self) -> dict:
        """Get session statistics"""
        return {
            "client_identity": self.client_identity,
            "current_operator": self.current_operator_id,
            "current_wallet": self.current_wallet_name,
            "message_count": self.message_count,
            "uptime_seconds": time.time() - self.start_time
        }

    def close(self):
        """Close session and cleanup"""
        stats = self.get_stats()
        logger.info(f"[HubColdSigning] Session closed for {self.client_identity[:16]}...")
        logger.info(f"[HubColdSigning] Messages: {stats['message_count']}, "
                   f"Uptime: {stats['uptime_seconds']:.1f}s")


def test_wallet_rpc_connection(url: str = "http://127.0.0.1:18082/json_rpc") -> bool:
    """Test connection to wallet-rpc"""
    client = WalletRPCClient(url)
    result = client.call("get_version")

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

    logger.info("Hub Cold Signing - Connection Test")

    if test_wallet_rpc_connection():
        logger.info("wallet-rpc is ready for cold signing operations")
    else:
        logger.error("wallet-rpc is not available")
        logger.info("Start it with: monero-wallet-rpc --wallet-dir <dir> --rpc-bind-port 18082 --disable-rpc-login")
