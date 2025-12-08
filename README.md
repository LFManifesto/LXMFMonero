# LXMFMonero

**Monero transactions over LXMF/Reticulum mesh networks**

LXMFMonero enables Monero wallet operations over Reticulum mesh networks using LXMF (Lightweight Extensible Message Format) for reliable message delivery. This allows financial sovereignty even in environments without traditional internet connectivity.

## Status

**Testing in Progress** - Core functionality verified over 2-hop public testnet.

| Feature | Status | Notes |
|---------|--------|-------|
| Balance queries | ✅ Verified | 2-4 second round-trip over testnet |
| Export outputs | ✅ Verified | 638 bytes delivered |
| Create unsigned tx | ✅ Verified | 6.5KB payloads work |
| Sign transaction | ✅ Verified | Cold wallet signing works |
| Submit transaction | ✅ Verified | Format correct, broadcasts to daemon |
| I2P transport | 🔄 Pending | Next test phase |
| LoRa/HF transport | 🔄 Pending | Future testing |

## Features

- **Cold Signing Workflow**: Private keys never leave your device
- **Any Transport**: Works over HF radio, LoRa, WiFi, I2P, or any Reticulum interface
- **Reliable Delivery**: LXMF handles retries, large payloads, and store-and-forward
- **Simple Architecture**: Stateless messages, no persistent connections required

## Architecture

```
┌─────────────────────┐                    ┌─────────────────────┐
│   COLD CLIENT       │                    │      HUB            │
│                     │                    │                     │
│  - Has spend key    │     LXMF           │  - View-only wallet │
│  - Signs locally    │◄──────────────────►│  - Connected to     │
│  - Air-gapped OK    │   (any transport)  │    monerod          │
│                     │                    │                     │
└─────────────────────┘                    └─────────────────────┘
```

## Installation

```bash
# Clone repository
git clone https://github.com/LFManifesto/LXMFMonero.git
cd LXMFMonero

# Install
pip install -e .
```

## Quick Start

### Hub Setup (View-Only Wallet)

The hub runs alongside a view-only Monero wallet and handles requests from clients.

1. Start `monero-wallet-rpc` with your view-only wallet:
```bash
monero-wallet-rpc --wallet-file /path/to/viewonly-wallet \
    --rpc-bind-port 18082 --disable-rpc-login
```

2. Start the hub:
```bash
lxmfmonero-hub --wallet-rpc http://127.0.0.1:18082/json_rpc
```

3. Note the destination hash printed at startup.

### Client Setup (Cold Wallet)

The client holds the spend key and can be air-gapped.

1. Start `monero-wallet-rpc` with your cold wallet:
```bash
monero-wallet-rpc --wallet-file /path/to/cold-wallet \
    --rpc-bind-port 18083 --disable-rpc-login
```

2. Check balance:
```bash
lxmfmonero-client --hub <hub-destination-hash> balance
```

3. Send XMR:
```bash
lxmfmonero-client --hub <hub-destination-hash> send <address> <amount>
```

## Cold Signing Workflow

The transaction flow ensures private keys never leave the cold wallet:

1. **Client** requests balance/transaction from **Hub** (view-only)
2. **Hub** creates unsigned transaction
3. **Client** signs locally with spend key
4. **Client** sends signed transaction to **Hub**
5. **Hub** broadcasts to Monero network
6. **Client** exports key images for balance sync

Each step is an independent LXMF message - no persistent connection required.

## Configuration

### Hub Options

```
--identity, -i    Path to identity file (default: ~/.lxmfmonero/hub/identity)
--storage, -s     Path to LXMF storage (default: ~/.lxmfmonero/hub/storage)
--wallet-rpc, -w  wallet-rpc URL (default: http://127.0.0.1:18082/json_rpc)
--name, -n        Display name for announcements
--announce-interval, -a  Seconds between announces (0 to disable)
```

### Client Options

```
--identity, -i    Path to identity file
--storage, -s     Path to LXMF storage
--hub, -H         Hub destination hash (required)
--cold-wallet, -c Cold wallet-rpc URL (default: http://127.0.0.1:18083/json_rpc)
--operator, -o    Operator ID for hub
--timeout, -t     Request timeout in seconds (default: 300)
```

## Message Sizes

All data sizes are compatible with LXMF's automatic Resource handling:

| Data | Size | Verified |
|------|------|----------|
| Balance response | ~500 bytes | ✅ |
| Export outputs | ~640-820 bytes | ✅ |
| Unsigned tx | 6-7 KB | ✅ |
| Signed tx | 12-13 KB | ✅ |
| Key images | ~500 bytes per | - |

## Tested Configuration

Successfully tested over Reticulum public testnet:

```
Mac (cold wallet) → Amsterdam Testnet → Pi (hub + monerod)
                        2 hops
```

- **Transport**: TCPInterface to amsterdam.connect.reticulum.network:4965
- **Round-trip**: 2-4 seconds for balance queries
- **Large payloads**: 12KB+ signed transactions delivered reliably

## Security Notes

- The **Hub** only has view-only access - it cannot spend funds
- The **Client** has the spend key and signs transactions locally
- All communication is end-to-end encrypted by Reticulum
- LXMF provides forward secrecy

## Requirements

- Python 3.9+
- Reticulum Network Stack (`rns`)
- LXMF (`lxmf`)
- Monero (`monero-wallet-rpc`)

## License

MIT License - See LICENSE file

## Credits

Built on:
- [Reticulum](https://reticulum.network/) - Cryptographic networking stack
- [LXMF](https://github.com/markqvist/LXMF) - Message format for Reticulum
- [Monero](https://getmonero.org/) - Private, decentralized cryptocurrency

Developed by [Light Fighter Manifesto L.L.C.](https://lightfightermanifesto.org)
