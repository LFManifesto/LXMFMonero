#!/usr/bin/env python3
"""
Test transaction broadcast via Reticulum hub.

This test:
1. Creates and signs tx locally (Mac has full wallet)
2. Sends signed tx to hub for broadcast

This demonstrates the "hot wallet to hub" flow where the client
has a full wallet but uses the hub's network access to broadcast.

WARNING: This will actually send XMR if successful!
"""
import RNS
import time
import sys
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from reticulumxmr.rpc_protocol import ModeSelectionMessage, register_message_types
from reticulumxmr.view_key_protocol import (
    register_view_key_messages,
    SignedTransactionMessage,
    TransactionResultMessage,
)

APP_NAME = "reticulumxmr"
LOCAL_WALLET_RPC = "http://127.0.0.1:18083/json_rpc"


def create_signed_transaction(dest_address: str, amount_xmr: float) -> tuple:
    """Create and sign transaction using local full wallet"""
    print("[Local] Creating signed transaction...")

    amount_atomic = int(amount_xmr * 1e12)

    payload = {
        "jsonrpc": "2.0",
        "id": "0",
        "method": "transfer",
        "params": {
            "destinations": [{
                "amount": amount_atomic,
                "address": dest_address
            }],
            "priority": 1,
            "do_not_relay": True,  # Don't broadcast yet
            "get_tx_hex": True,
            "get_tx_metadata": True
        }
    }

    try:
        response = requests.post(LOCAL_WALLET_RPC, json=payload, timeout=60)
        result = response.json()

        if "error" in result:
            print(f"[Local] Transfer error: {result['error']}")
            return None, None

        tx_data = result.get("result", {})
        tx_hash = tx_data.get("tx_hash", "")
        tx_metadata = tx_data.get("tx_metadata", "")  # For relay_tx
        fee = tx_data.get("fee", 0)

        print(f"[Local] Transaction created!")
        print(f"[Local] TX hash: {tx_hash}")
        print(f"[Local] Fee: {fee / 1e12} XMR")
        print(f"[Local] TX metadata size: {len(tx_metadata)} chars")

        return tx_hash, tx_metadata

    except requests.exceptions.ConnectionError:
        print(f"[Local] ERROR: Cannot connect to wallet-rpc")
        return None, None
    except Exception as e:
        print(f"[Local] ERROR: {e}")
        return None, None


def main():
    hub_dest = sys.argv[1] if len(sys.argv) > 1 else "4230ae93bd3cea0208271f50f928bae8"

    # Monero Project donation address
    dest_address = "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A"
    amount = 0.001

    print("=" * 60)
    print("BROADCAST TEST - Local Sign, Remote Broadcast")
    print("=" * 60)
    print(f"Destination: {dest_address[:20]}...{dest_address[-8:]}")
    print(f"Amount: {amount} XMR")
    print()
    print("WARNING: This will send real XMR!")
    print("=" * 60)
    print()

    # Step 1: Create signed tx locally
    print("[Step 1] Creating signed transaction locally...")
    tx_hash, tx_blob = create_signed_transaction(dest_address, amount)

    if not tx_blob:
        print("[Step 1] FAILED to create transaction")
        return 1

    # Step 2: Connect to hub
    print("\n[Step 2] Connecting to hub via Reticulum...")
    reticulum = RNS.Reticulum()
    identity = RNS.Identity()

    dest_hash = bytes.fromhex(hub_dest)
    if not RNS.Transport.has_path(dest_hash):
        print("[Step 2] Requesting path...")
        RNS.Transport.request_path(dest_hash)
        start = time.time()
        while not RNS.Transport.has_path(dest_hash) and time.time() - start < 10:
            time.sleep(0.5)

    if not RNS.Transport.has_path(dest_hash):
        print("[Step 2] ERROR: No path to hub")
        return 1

    dest_identity = RNS.Identity.recall(dest_hash)
    destination = RNS.Destination(
        dest_identity,
        RNS.Destination.OUT,
        RNS.Destination.SINGLE,
        APP_NAME,
        "hub"
    )

    print("[Step 2] Establishing link...")
    link = RNS.Link(destination)

    start = time.time()
    while link.status != RNS.Link.ACTIVE and time.time() - start < 30:
        if link.status == RNS.Link.CLOSED:
            print("[Step 2] Link closed!")
            return 1
        time.sleep(0.1)

    print("[Step 2] Link ACTIVE")

    channel = link.get_channel()
    responses = []

    def handler(message):
        print(f"[RX] Received: {type(message).__name__}")
        responses.append(message)
        return True

    register_message_types(channel)
    register_view_key_messages(channel)
    channel.add_message_handler(handler)

    # Select mode
    print("\n[Step 3] Selecting cold_signing mode...")
    channel.send(ModeSelectionMessage(ModeSelectionMessage.MODE_COLD_SIGNING))
    time.sleep(3)

    # Step 4: Send signed tx to hub for broadcast
    print("\n[Step 4] Sending signed transaction to hub...")
    print(f"[Step 4] TX blob: {tx_blob[:50]}...")

    signed_msg = SignedTransactionMessage(
        operator_id="test_operator",
        request_id=f"broadcast_{int(time.time())}",
        signed_tx=tx_blob
    )
    channel.send(signed_msg)

    # Wait for result
    print("[Step 4] Waiting for broadcast confirmation...")
    start = time.time()
    broadcast_hash = None
    while time.time() - start < 120:
        for resp in responses:
            if isinstance(resp, TransactionResultMessage):
                if resp.success:
                    broadcast_hash = resp.tx_hash
                    print(f"\n[SUCCESS] Transaction broadcast!")
                    print(f"[SUCCESS] TX Hash: {broadcast_hash}")
                    print(f"[SUCCESS] Status: {resp.status}")
                else:
                    print(f"\n[FAILED] {resp.error}")
                break
        if broadcast_hash or any(isinstance(r, TransactionResultMessage) for r in responses):
            break
        time.sleep(1)

    link.teardown()

    if broadcast_hash:
        print("\n" + "=" * 60)
        print("TRANSACTION BROADCAST SUCCESSFUL!")
        print("=" * 60)
        print(f"TX Hash: {broadcast_hash}")
        print(f"\nView: https://xmrchain.net/tx/{broadcast_hash}")
        print("=" * 60)
        return 0
    else:
        print("\n[FAILED] No broadcast confirmation received")
        return 1


if __name__ == "__main__":
    sys.exit(main())
