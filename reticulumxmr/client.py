#!/usr/bin/env python3
"""
ReticulumXMR Client
Connects to hub over Reticulum for cold signing transactions

The client:
- Has the full wallet (with spend key) for signing
- Connects to hub over Reticulum mesh
- Requests balance/creates tx via hub (view-only wallet)
- Signs transactions locally
- Sends signed tx back to hub for broadcast
"""
import RNS
import time
import sys
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
import requests

from .rpc_protocol import register_message_types, ModeSelectionMessage
from .view_key_protocol import (
    register_view_key_messages,
    BalanceRequestMessage,
    BalanceResponseMessage,
    CreateTransactionMessage,
    UnsignedTransactionMessage,
    SignedTransactionMessage,
    TransactionResultMessage,
    ExportOutputsRequestMessage,
    ExportOutputsResponseMessage,
)
from .config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

APP_NAME = "reticulumxmr"


class WalletRPCClient:
    """Simple wallet-rpc JSON-RPC client for local signing"""

    def __init__(self, url: str = "http://127.0.0.1:18083/json_rpc"):
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

    def sign_transfer(self, unsigned_txset: str) -> dict:
        """Sign an unsigned transaction set"""
        return self.call("sign_transfer", {
            "unsigned_txset": unsigned_txset,
            "export_raw": False
        })


class ReticulumXMRClient:
    """Client for cold signing over Reticulum"""

    def __init__(self, hub_destination: str, operator_id: str = "default",
                 local_wallet_rpc: str = "http://127.0.0.1:18083/json_rpc",
                 config: Config = None):
        """
        Args:
            hub_destination: Hub destination hash (hex string)
            operator_id: Identifier for this operator
            local_wallet_rpc: URL of local wallet-rpc with spend key
            config: Configuration object
        """
        self.config = config or Config()
        self.hub_destination_hash = bytes.fromhex(hub_destination.replace("<", "").replace(">", ""))
        self.operator_id = operator_id
        self.local_wallet = WalletRPCClient(local_wallet_rpc)

        # Response tracking
        self._pending_requests = {}
        self._response_events = {}

        # Connection state
        self.link: Optional[RNS.Link] = None
        self.channel = None
        self.connected = False

        # Initialize Reticulum
        logger.info("Initializing Reticulum...")
        self.reticulum = RNS.Reticulum()

        # Load or create identity
        identity_path = self.config.CONFIG_DIR / "client_identity"
        if identity_path.exists():
            self.identity = RNS.Identity.from_file(str(identity_path))
            logger.info(f"Loaded identity from {identity_path}")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(str(identity_path))
            logger.info(f"Created new identity at {identity_path}")

        logger.info(f"Client initialized for operator: {operator_id}")
        logger.info(f"Hub destination: {RNS.prettyhexrep(self.hub_destination_hash)}")

    def connect(self, timeout: float = 30.0) -> bool:
        """
        Connect to hub over Reticulum

        Args:
            timeout: Connection timeout in seconds

        Returns:
            True if connected successfully
        """
        logger.info("Connecting to hub...")

        # Request path to destination
        if not RNS.Transport.has_path(self.hub_destination_hash):
            logger.info("Requesting path to hub...")
            RNS.Transport.request_path(self.hub_destination_hash)

            # Wait for path
            start = time.time()
            while not RNS.Transport.has_path(self.hub_destination_hash):
                if time.time() - start > timeout:
                    logger.error("Timeout waiting for path to hub")
                    return False
                time.sleep(0.5)

        # Recall destination identity
        hub_identity = RNS.Identity.recall(self.hub_destination_hash)
        if not hub_identity:
            logger.error("Could not recall hub identity")
            return False

        # Create destination
        destination = RNS.Destination(
            hub_identity,
            RNS.Destination.OUT,
            RNS.Destination.SINGLE,
            APP_NAME,
            "hub"
        )

        # Create link
        self.link = RNS.Link(destination)

        # Wait for link to become active
        start = time.time()
        while self.link.status != RNS.Link.ACTIVE:
            if self.link.status == RNS.Link.CLOSED:
                logger.error("Link closed before becoming active")
                return False
            if time.time() - start > timeout:
                logger.error("Timeout waiting for link to become active")
                return False
            time.sleep(0.1)

        logger.info("Link established!")

        # Get channel
        self.channel = self.link.get_channel()
        if not self.channel:
            logger.error("Could not get channel from link")
            return False

        # Register message types
        register_message_types(self.channel)
        register_view_key_messages(self.channel)

        # Add message handler
        self.channel.add_message_handler(self._handle_message)

        # Send mode selection
        mode_msg = ModeSelectionMessage(mode=ModeSelectionMessage.MODE_COLD_SIGNING)
        self.channel.send(mode_msg)

        self.connected = True
        logger.info("Connected to hub successfully!")
        return True

    def _handle_message(self, message) -> bool:
        """Handle incoming messages from hub"""
        msg_type = type(message).__name__
        logger.debug(f"Received: {msg_type}")

        # Check for pending request
        request_id = getattr(message, 'request_id', None)
        if request_id and request_id in self._pending_requests:
            self._pending_requests[request_id] = message
            if request_id in self._response_events:
                self._response_events[request_id].set()
            return True

        return False

    def _wait_for_response(self, request_id: str, timeout: float = 60.0):
        """Wait for response with given request_id"""
        event = threading.Event()
        self._response_events[request_id] = event
        self._pending_requests[request_id] = None

        if event.wait(timeout):
            response = self._pending_requests.pop(request_id, None)
            self._response_events.pop(request_id, None)
            return response
        else:
            self._pending_requests.pop(request_id, None)
            self._response_events.pop(request_id, None)
            return None

    def get_balance(self, timeout: float = 60.0) -> dict:
        """
        Get balance from hub

        Returns:
            Dict with balance info or error
        """
        if not self.connected:
            return {"error": "Not connected to hub"}

        request_id = f"bal_{int(time.time()*1000)}"
        msg = BalanceRequestMessage(
            operator_id=self.operator_id,
            request_id=request_id
        )

        logger.info(f"Requesting balance...")
        self.channel.send(msg)

        response = self._wait_for_response(request_id, timeout)
        if not response:
            return {"error": "Timeout waiting for balance response"}

        if isinstance(response, BalanceResponseMessage):
            if response.success:
                return {
                    "balance": response.balance,
                    "unlocked_balance": response.unlocked_balance,
                    "balance_atomic": response.balance_atomic,
                    "block_height": response.block_height,
                    "blocks_to_unlock": response.blocks_to_unlock
                }
            else:
                return {"error": response.error}

        return {"error": f"Unexpected response type: {type(response).__name__}"}

    def create_and_sign_transaction(self, destination: str, amount: float,
                                     priority: int = 1, timeout: float = 120.0) -> dict:
        """
        Create transaction on hub and sign locally

        Args:
            destination: Recipient address
            amount: Amount in XMR
            priority: Transaction priority (0-2)
            timeout: Timeout for each step

        Returns:
            Dict with transaction result or error
        """
        if not self.connected:
            return {"error": "Not connected to hub"}

        # Step 1: Request unsigned transaction from hub
        request_id = f"tx_{int(time.time()*1000)}"
        msg = CreateTransactionMessage(
            operator_id=self.operator_id,
            request_id=request_id,
            destination=destination,
            amount=amount,
            priority=priority
        )

        logger.info(f"Requesting unsigned transaction: {amount} XMR to {destination[:20]}...")
        self.channel.send(msg)

        response = self._wait_for_response(request_id, timeout)
        if not response:
            return {"error": "Timeout waiting for unsigned transaction"}

        if not isinstance(response, UnsignedTransactionMessage):
            return {"error": f"Unexpected response: {type(response).__name__}"}

        if not response.success:
            return {"error": response.error}

        unsigned_tx = response.unsigned_tx
        fee = response.fee
        logger.info(f"Received unsigned tx (fee: {fee} XMR, size: {len(unsigned_tx)} chars)")

        # Step 2: Sign locally with spend key
        logger.info("Signing transaction locally...")
        sign_result = self.local_wallet.sign_transfer(unsigned_tx)

        if "error" in sign_result:
            return {"error": f"Signing failed: {sign_result['error']}"}

        signed_txset = sign_result.get("result", {}).get("signed_txset", "")
        if not signed_txset:
            return {"error": "No signed transaction returned"}

        logger.info(f"Transaction signed (size: {len(signed_txset)} chars)")

        # Step 3: Submit signed transaction to hub
        submit_msg = SignedTransactionMessage(
            operator_id=self.operator_id,
            request_id=request_id,
            signed_tx=signed_txset
        )

        logger.info("Submitting signed transaction to hub...")
        self.channel.send(submit_msg)

        result = self._wait_for_response(request_id, timeout)
        if not result:
            return {"error": "Timeout waiting for broadcast confirmation"}

        if isinstance(result, TransactionResultMessage):
            if result.success:
                return {
                    "success": True,
                    "tx_hash": result.tx_hash,
                    "fee": fee,
                    "amount": amount,
                    "destination": destination
                }
            else:
                return {"error": result.error}

        return {"error": f"Unexpected response: {type(result).__name__}"}

    def export_outputs(self, all_outputs: bool = True, timeout: float = 60.0) -> dict:
        """
        Request outputs export from hub for cold wallet sync

        Args:
            all_outputs: Export all outputs or only new ones
            timeout: Request timeout

        Returns:
            Dict with outputs_data_hex or error
        """
        if not self.connected:
            return {"error": "Not connected to hub"}

        request_id = f"out_{int(time.time()*1000)}"
        msg = ExportOutputsRequestMessage(
            operator_id=self.operator_id,
            request_id=request_id,
            all_outputs=all_outputs
        )

        logger.info("Requesting outputs export...")
        self.channel.send(msg)

        response = self._wait_for_response(request_id, timeout)
        if not response:
            return {"error": "Timeout waiting for outputs"}

        if isinstance(response, ExportOutputsResponseMessage):
            if response.success:
                return {
                    "outputs_data_hex": response.outputs_data_hex,
                    "size": len(response.outputs_data_hex) if response.outputs_data_hex else 0
                }
            else:
                return {"error": response.error}

        return {"error": f"Unexpected response: {type(response).__name__}"}

    def disconnect(self):
        """Disconnect from hub"""
        if self.link:
            self.link.teardown()
            self.link = None
        self.connected = False
        logger.info("Disconnected from hub")


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="ReticulumXMR Client")
    parser.add_argument("hub", help="Hub destination hash")
    parser.add_argument("-o", "--operator", default="default", help="Operator ID")
    parser.add_argument("-w", "--wallet-rpc", default="http://127.0.0.1:18083/json_rpc",
                        help="Local wallet-rpc URL")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Balance command
    subparsers.add_parser("balance", help="Get wallet balance")

    # Send command
    send_parser = subparsers.add_parser("send", help="Send XMR")
    send_parser.add_argument("address", help="Destination address")
    send_parser.add_argument("amount", type=float, help="Amount in XMR")
    send_parser.add_argument("-p", "--priority", type=int, default=1,
                             help="Priority (0=low, 1=normal, 2=high)")

    # Export outputs command
    subparsers.add_parser("export-outputs", help="Export outputs for cold wallet sync")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Create client and connect
    client = ReticulumXMRClient(
        hub_destination=args.hub,
        operator_id=args.operator,
        local_wallet_rpc=args.wallet_rpc
    )

    if not client.connect():
        logger.error("Failed to connect to hub")
        sys.exit(1)

    try:
        if args.command == "balance":
            result = client.get_balance()
            if "error" in result:
                logger.error(f"Error: {result['error']}")
                sys.exit(1)
            print(f"\nBalance: {result['balance']:.12f} XMR")
            print(f"Unlocked: {result['unlocked_balance']:.12f} XMR")
            print(f"Block height: {result['block_height']}")

        elif args.command == "send":
            print(f"\nCreating transaction:")
            print(f"  To: {args.address}")
            print(f"  Amount: {args.amount} XMR")
            print(f"  Priority: {args.priority}")

            result = client.create_and_sign_transaction(
                destination=args.address,
                amount=args.amount,
                priority=args.priority
            )

            if "error" in result:
                logger.error(f"Error: {result['error']}")
                sys.exit(1)

            print(f"\nTransaction broadcast!")
            print(f"  TX Hash: {result['tx_hash']}")
            print(f"  Fee: {result['fee']:.12f} XMR")

        elif args.command == "export-outputs":
            result = client.export_outputs()
            if "error" in result:
                logger.error(f"Error: {result['error']}")
                sys.exit(1)
            print(f"\nExported outputs: {result['size']} chars")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
