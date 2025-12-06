# ReticulumXMR View Key Protocol Design

**Date:** 2025-12-03
**Architecture:** View Key Model for Team Operations

---

## Overview

Hub maintains team wallets using view keys. Field operators have spend keys only and send high-level commands. All operations use small messages (1-6 KB) suitable for HF/LoRa.

---

## Message Types

### 1. ProvisionWalletMessage (One-time Setup)

**Direction:** Client → Hub (pre-deployment only)

**Purpose:** Provision operator's view key to hub

```python
{
    "operator_id": "alice",           # Unique operator identifier
    "view_key": "...",                # Private view key (hex)
    "wallet_address": "8A...",        # Primary address
    "wallet_name": "alice_wallet",    # Friendly name
    "restore_height": 3500000         # Block to start scanning from
}
```

**Response:** ProvisionAckMessage

```python
{
    "success": True,
    "operator_id": "alice",
    "status": "Wallet provisioned, scanning blockchain..."
}
```

**Size:** ~500 bytes

**Notes:**
- Only done once during pre-deployment setup
- View key encrypted over RNS (end-to-end encrypted)
- Hub stores view key securely
- Hub begins blockchain scan immediately

---

### 2. BalanceRequestMessage

**Direction:** Client → Hub

**Purpose:** Request current balance

```python
{
    "operator_id": "alice",
    "request_id": "req_001"          # For tracking
}
```

**Response:** BalanceResponseMessage

```python
{
    "success": True,
    "request_id": "req_001",
    "balance": 5.234567,              # Total balance (XMR)
    "unlocked_balance": 5.234567,     # Spendable balance (XMR)
    "balance_atomic": 5234567000000,  # Atomic units
    "block_height": 3556929,          # Current sync height
    "blocks_to_unlock": 0             # Confirmations pending
}
```

**Size:** Request ~200 bytes, Response ~300 bytes

---

### 3. CreateTransactionMessage

**Direction:** Client → Hub

**Purpose:** Request unsigned transaction

```python
{
    "operator_id": "alice",
    "request_id": "tx_001",
    "destination": "8A...",           # Recipient XMR address
    "amount": 1.5,                    # Amount in XMR
    "priority": 1,                    # 0=default, 1=elevated, 2=high
    "description": "Payment for gear" # Optional memo (client-side only)
}
```

**Response:** UnsignedTransactionMessage

```python
{
    "success": True,
    "request_id": "tx_001",
    "unsigned_tx": "...",             # Unsigned transaction blob (hex)
    "tx_key": "...",                  # Transaction key for tracking
    "fee": 0.00012,                   # Network fee (XMR)
    "total": 1.50012,                 # Amount + fee
    "destinations": [...],            # Output details
    "change": 3.73388                 # Change amount
}
```

**Size:** Request ~400 bytes, Response ~2-4 KB

---

### 4. SignedTransactionMessage

**Direction:** Client → Hub

**Purpose:** Submit signed transaction for broadcast

```python
{
    "operator_id": "alice",
    "request_id": "tx_001",
    "signed_tx": "..."                # Signed transaction blob (hex)
}
```

**Response:** TransactionResultMessage

```python
{
    "success": True,
    "request_id": "tx_001",
    "tx_hash": "abc123...",           # Transaction hash
    "tx_key": "def456...",            # Key for recipient verification
    "fee": 0.00012,
    "status": "broadcast"             # broadcast|pending|confirmed
}
```

**Size:** Request ~3-5 KB, Response ~400 bytes

---

### 5. TransactionHistoryMessage

**Direction:** Client → Hub

**Purpose:** Get recent transaction history

```python
{
    "operator_id": "alice",
    "request_id": "hist_001",
    "limit": 10,                      # Max transactions to return
    "min_height": 0                   # Optional: only after this block
}
```

**Response:** HistoryResponseMessage

```python
{
    "success": True,
    "request_id": "hist_001",
    "transactions": [
        {
            "tx_hash": "...",
            "height": 3556900,
            "timestamp": 1701432000,
            "amount": 2.5,
            "fee": 0.00012,
            "type": "in|out",
            "confirmations": 29,
            "address": "8A..."         # Counterparty address
        },
        ...
    ]
}
```

**Size:** Request ~200 bytes, Response ~1-5 KB (depends on history)

---

### 6. StatusMessage (Hub Push)

**Direction:** Hub → Client

**Purpose:** Notify client of important events

```python
{
    "operator_id": "alice",
    "event_type": "incoming_tx|tx_confirmed|sync_complete",
    "tx_hash": "...",                 # If tx-related
    "amount": 1.5,                    # If tx-related
    "message": "Received 1.5 XMR",
    "timestamp": 1701432000
}
```

**Size:** ~500 bytes

**Notes:**
- Hub pushes these proactively
- Client can subscribe to notifications
- Useful for incoming payment alerts

---

## Transaction Workflow

### Send Transaction

```
1. Client → Hub: CreateTransactionMessage
   "I want to send 1.5 XMR to address 8A..."

2. Hub:
   - Uses view key to check balance
   - Identifies spendable outputs
   - Constructs unsigned transaction
   - Returns unsigned tx blob

3. Client:
   - Reviews transaction details
   - Signs with spend key (LOCAL - offline)
   - Never sends spend key anywhere

4. Client → Hub: SignedTransactionMessage
   "Here's the signed transaction"

5. Hub:
   - Validates signed transaction
   - Broadcasts to Monero network
   - Returns tx hash

6. Client:
   - Displays confirmation
   - Stores tx hash for tracking
```

**Total Data:** ~5-10 KB per transaction

**Time:** Seconds to minutes (depending on link speed)

---

## Security Model

### What Hub Knows (View Key)
- ✓ All incoming transactions
- ✓ All outgoing transactions
- ✓ Balance
- ✓ Transaction history
- ❌ **Cannot spend** (no spend key)

### What Client Controls (Spend Key)
- ✓ **Authorization to spend** (signs all transactions)
- ✓ Can reject any transaction
- ✓ Can recover wallet independently
- ✓ Full control of funds

### Trust Requirements
- Hub must not lose view keys (backup required)
- Hub must be available for operations
- Hub is trusted infrastructure (team-owned)
- Network link must be authenticated (RNS encryption)

---

## Implementation Notes

### Message Encoding
- Use `msgpack` for efficient serialization
- All messages inherit from `RNS.MessageBase`
- Use Reticulum Channel for reliable delivery

### Error Handling
- All responses include `success` field
- Errors include `error` field with human-readable message
- Client implements retry logic with exponential backoff

### State Management
- Hub maintains wallet state (blockchain sync)
- Client caches recent balance/history
- Client stores all spend key operations locally

### Performance
- Balance check: <1 KB, <10 seconds over LoRa
- Create tx: ~4 KB, <40 seconds over LoRa
- Sign + broadcast: ~5 KB, <50 seconds over LoRa
- **Total transaction: ~10 KB, ~2 minutes over LoRa**

---

## Comparison to Full wallet-rpc Proxy

| Operation | Old (Proxy) | New (View Key) |
|-----------|-------------|----------------|
| Balance check | 100+ MB (sync) | 1 KB |
| Send tx | 100+ MB (sync) | 10 KB |
| Daily sync | ~200 MB | 0 (hub syncs) |
| 2-week data | ~2 GB | ~160 KB |
| LoRa time | 154 days | 18 minutes |

**Result:** 1000x more efficient for HF/LoRa operations

---

## Next Steps

1. Implement message classes in `rpc_protocol.py`
2. Implement hub wallet manager
3. Implement lightweight client
4. Test over TCP/local
5. Test over LoRa/HF

---

**Status:** Design complete, ready for implementation
