# ReticulumXMR

**Monero transactions over Reticulum mesh networks**

ReticulumXMR enables off-grid Monero transactions over low-bandwidth mesh networks like HF radio, LoRa, and packet radio using the [Reticulum Network Stack](https://reticulum.network/).

## Status

**TCP Transport: VERIFIED WORKING** - First successful mainnet transaction broadcast on 2025-12-03.

| Feature | Status |
|---------|--------|
| Balance queries | Working |
| Transaction creation | Working |
| Transaction broadcast | Working |
| TCP/IP transport | Verified |
| LoRa transport | Untested |
| HF radio transport | Untested |

## How It Works

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Client (Field) │◄───────►│  Reticulum Mesh │◄───────►│   Hub (Pi)      │
│                 │  Radio  │   HF/LoRa/TCP   │         │                 │
│  - Full wallet  │         │                 │         │  - monerod      │
│  - Signs tx     │         │                 │         │  - wallet-rpc   │
│  - Offline      │         │                 │         │  - Internet     │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

**Architecture:**
- **Hub**: Raspberry Pi with synced Monero daemon and wallet-rpc, connected to internet
- **Client**: Field device with wallet, communicates only via Reticulum mesh
- **Transport**: Encrypted Reticulum channels over any physical layer

## Data Sizes

Optimized for low-bandwidth links:

| Operation | Size | Time @ 1200 bps | Time @ 300 bps |
|-----------|------|-----------------|----------------|
| Balance query | ~500 B | <1 sec | ~13 sec |
| Create unsigned tx | ~4 KB | ~27 sec | ~107 sec |
| Broadcast signed tx | ~7 KB | ~47 sec | ~187 sec |

## Installation

### Requirements

- Python 3.9+
- Reticulum Network Stack
- Monero daemon (monerod) - hub only
- monero-wallet-rpc - hub and client

### Install

```bash
# Clone repository
git clone https://github.com/lfmanifesto/reticulumxmr.git
cd reticulumxmr

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install package
pip install -e .
```

### Hub Setup (Raspberry Pi)

1. Install and sync monerod
2. Start wallet-rpc:
```bash
monero-wallet-rpc --wallet-dir ~/.reticulumxmr/wallets \
    --rpc-bind-port 18085 \
    --disable-rpc-login \
    --daemon-address 127.0.0.1:18081
```

3. Start Reticulum daemon:
```bash
rnsd
```

4. Start hub:
```bash
python -m reticulumxmr.hub
```

### Client Setup

1. Start Reticulum daemon:
```bash
rnsd
```

2. Start wallet-rpc with your wallet:
```bash
monero-wallet-rpc --wallet-file ~/your-wallet \
    --rpc-bind-port 18083 \
    --disable-rpc-login \
    --daemon-address <hub-ip>:18081 \
    --prompt-for-password
```

3. Use the test script to broadcast a transaction:
```bash
python tests/test_broadcast_only.py <hub-destination-hash>
```

## Usage

### Check Balance

```python
from reticulumxmr.view_key_protocol import BalanceRequestMessage

# Send balance request
msg = BalanceRequestMessage(operator_id="user", request_id="1")
channel.send(msg)

# Response contains:
# - balance (XMR)
# - unlocked_balance (XMR)
# - block_height
```

### Create and Broadcast Transaction

```python
# 1. Create transaction locally (do_not_relay=True)
# 2. Send tx_metadata to hub via SignedTransactionMessage
# 3. Hub broadcasts via relay_tx
```

See `tests/test_broadcast_only.py` for complete example.

## Protocol

ReticulumXMR uses RNS Channels with msgpack-serialized messages:

| Message | Direction | Purpose |
|---------|-----------|---------|
| ModeSelectionMessage | Client→Hub | Select operating mode |
| BalanceRequestMessage | Client→Hub | Request balance |
| BalanceResponseMessage | Hub→Client | Return balance |
| CreateTransactionMessage | Client→Hub | Request unsigned tx |
| UnsignedTransactionMessage | Hub→Client | Return unsigned tx |
| SignedTransactionMessage | Client→Hub | Submit for broadcast |
| TransactionResultMessage | Hub→Client | Broadcast confirmation |

## Operating Modes

- **cold_signing**: Hub has view-only wallet, client signs transactions
- **non_custodial**: Hub proxies RPC requests to daemon
- **custodial**: Hub controls wallet (legacy)

## Security

- All Reticulum traffic is end-to-end encrypted
- Private keys never leave the client device
- Hub only needs view key for balance queries
- Transactions signed locally before transmission

## Testing

```bash
# Run broadcast test (sends real XMR!)
python tests/test_broadcast_only.py <hub-destination>
```

## First Successful Transaction

**TX Hash:** `b9b45d1be49ee963192efe77ecb6502287289ddfe6e1f8060860439aa75ffebf`

- Date: 2025-12-03
- Amount: 0.001 XMR
- Transport: TCP via Reticulum
- Path: Mac → Reticulum → Pi Hub → Monero Network

## Roadmap

- [ ] LoRa transport testing
- [ ] HF radio transport testing
- [ ] TUI client interface
- [ ] Multi-wallet support
- [ ] Automatic key image sync

## Dependencies

- [Reticulum](https://github.com/markqvist/Reticulum) - Mesh networking stack
- [msgpack](https://msgpack.org/) - Message serialization
- [requests](https://requests.readthedocs.io/) - HTTP client for RPC

## License

MIT License - See LICENSE file

## Contributing

Pull requests welcome. Please test on actual mesh hardware when possible.

## Acknowledgments

- [Monero Project](https://getmonero.org/) - Private digital currency
- [Mark Qvist](https://github.com/markqvist) - Reticulum creator
- Light Fighter Manifesto L.L.C.
