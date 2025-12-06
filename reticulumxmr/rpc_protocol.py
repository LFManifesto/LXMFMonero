#!/usr/bin/env python3
"""
ReticulumXMR RPC Protocol
Message definitions for client-hub communication
Based on rnsh pattern with RNS.MessageBase
"""
import RNS
import time

try:
    import umsgpack as msgpack
except ImportError:
    import msgpack

# Protocol constants
MSG_MAGIC = 0xCD  # ReticulumXMR magic number
PROTOCOL_VERSION = 1

def _make_msgtype(val: int):
    """Create message type identifier"""
    return ((MSG_MAGIC << 8) & 0xff00) | (val & 0x00ff)


class VersionMessage(RNS.MessageBase):
    """Protocol version negotiation"""
    MSGTYPE = _make_msgtype(1)

    def __init__(self, version: int = PROTOCOL_VERSION):
        self.version = version

    def pack(self) -> bytes:
        return msgpack.packb(self.version)

    def unpack(self, raw: bytes):
        self.version = msgpack.unpackb(raw)


class AuthMessage(RNS.MessageBase):
    """Authentication (optional for now)"""
    MSGTYPE = _make_msgtype(2)

    def __init__(self, token: str = None):
        self.token = token

    def pack(self) -> bytes:
        return msgpack.packb(self.token)

    def unpack(self, raw: bytes):
        self.token = msgpack.unpackb(raw)


class MoneroCommandMessage(RNS.MessageBase):
    """Monero RPC command from client to hub"""
    MSGTYPE = _make_msgtype(3)

    # Command types
    CMD_BALANCE = "balance"
    CMD_ADDRESS = "address"
    CMD_TRANSFER = "transfer"
    CMD_INCOMING = "incoming_transfers"
    CMD_HEIGHT = "get_height"
    CMD_SWEEP = "sweep_all"

    def __init__(self, command: str = None, params: dict = None):
        """
        Args:
            command: Command type (balance, transfer, etc.)
            params: Command parameters (e.g., {'address': '...', 'amount': 1.5})
        """
        self.command = command
        self.params = params or {}
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb((self.command, self.params, self.timestamp))

    def unpack(self, raw: bytes):
        self.command, self.params, self.timestamp = msgpack.unpackb(raw)


class MoneroResponseMessage(RNS.MessageBase):
    """Monero RPC response from hub to client"""
    MSGTYPE = _make_msgtype(4)

    def __init__(self, success: bool = True, data: dict = None,
                 error: str = None, done: bool = True):
        """
        Args:
            success: Whether command succeeded
            data: Response data (balance, tx_hash, etc.)
            error: Error message if failed
            done: Whether this is the final response (for streaming)
        """
        self.success = success
        self.data = data or {}
        self.error = error
        self.done = done
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb((self.success, self.data, self.error,
                            self.done, self.timestamp))

    def unpack(self, raw: bytes):
        self.success, self.data, self.error, self.done, self.timestamp = \
            msgpack.unpackb(raw)


class StatusMessage(RNS.MessageBase):
    """Hub status updates"""
    MSGTYPE = _make_msgtype(5)

    def __init__(self, status: str = None, message: str = None):
        """
        Args:
            status: Status type (connected, syncing, ready, error)
            message: Human-readable message
        """
        self.status = status
        self.message = message

    def pack(self) -> bytes:
        return msgpack.packb((self.status, self.message))

    def unpack(self, raw: bytes):
        self.status, self.message = msgpack.unpackb(raw)


# Helper functions for creating common commands
def cmd_get_balance() -> MoneroCommandMessage:
    """Create balance query command"""
    return MoneroCommandMessage(MoneroCommandMessage.CMD_BALANCE)


def cmd_get_address() -> MoneroCommandMessage:
    """Create address query command"""
    return MoneroCommandMessage(MoneroCommandMessage.CMD_ADDRESS)


def cmd_transfer(address: str, amount: float, priority: int = 1) -> MoneroCommandMessage:
    """Create transfer command"""
    return MoneroCommandMessage(
        MoneroCommandMessage.CMD_TRANSFER,
        {
            'address': address,
            'amount': amount,
            'priority': priority
        }
    )


def cmd_incoming_transfers() -> MoneroCommandMessage:
    """Create incoming transfers query"""
    return MoneroCommandMessage(MoneroCommandMessage.CMD_INCOMING)


def cmd_get_height() -> MoneroCommandMessage:
    """Create blockchain height query"""
    return MoneroCommandMessage(MoneroCommandMessage.CMD_HEIGHT)


# ============================================================================
# NON-CUSTODIAL MODE: RPC TUNNELING PROTOCOL
# ============================================================================
# These messages enable RPC proxy mode where client's wallet-rpc tunnels
# daemon RPC calls through the hub to reach the Monero network


class RPCTunnelRequest(RNS.MessageBase):
    """
    Tunnel a daemon RPC request from client to hub (JSON or Binary)

    In non-custodial mode, the client runs monero-wallet-rpc locally.
    The wallet-rpc needs blockchain data from monerod, but client has
    no internet. This message tunnels those daemon RPC calls through
    Reticulum to the hub's monerod.

    Supports both JSON-RPC (/json_rpc) and binary RPC (/getblocks.bin, etc.)

    Examples of tunneled methods:
    - JSON: get_info, get_block_count, submit_transaction
    - Binary: /getblocks.bin, /get_o_indexes.bin, /get_hashes.bin
    """
    MSGTYPE = _make_msgtype(10)

    def __init__(self, endpoint: str = "/json_rpc",
                 method: str = None, params: dict = None,
                 body: bytes = None, rpc_id: str = None):
        """
        Args:
            endpoint: HTTP endpoint path (e.g., "/json_rpc", "/getblocks.bin")
            method: Daemon RPC method name (for JSON-RPC)
            params: Method parameters (for JSON-RPC)
            body: Raw binary body (for binary RPC endpoints)
            rpc_id: JSON-RPC ID for matching request/response
        """
        self.endpoint = endpoint
        self.method = method
        self.params = params or {}
        self.body = body  # Binary data for binary endpoints
        self.rpc_id = rpc_id or str(int(time.time() * 1000))
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'endpoint': self.endpoint,
            'method': self.method,
            'params': self.params,
            'body': self.body,
            'id': self.rpc_id,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)
        # msgpack uses byte string keys by default
        endpoint = data.get(b'endpoint', b'/json_rpc')
        self.endpoint = endpoint.decode('utf-8') if isinstance(endpoint, bytes) else endpoint

        method = data.get(b'method')
        self.method = method.decode('utf-8') if isinstance(method, bytes) else method

        self.params = data.get(b'params', {})
        self.body = data.get(b'body')  # Keep as bytes

        rpc_id = data.get(b'id', b'0')
        self.rpc_id = rpc_id.decode('utf-8') if isinstance(rpc_id, bytes) else str(rpc_id) if rpc_id else '0'

        self.timestamp = data.get(b'ts', time.time())


class RPCTunnelResponse(RNS.MessageBase):
    """
    Return daemon RPC response from hub to client (JSON or Binary)

    Hub receives RPCTunnelRequest, forwards to monerod via HTTP,
    wraps the response, and sends back via this message.

    For large responses (> channel MDU), use RPCTunnelChunk instead.
    """
    MSGTYPE = _make_msgtype(11)

    def __init__(self, result: dict = None, body: bytes = None,
                 error: dict = None, rpc_id: str = None,
                 is_binary: bool = False, total_chunks: int = 1):
        """
        Args:
            result: JSON-RPC result object (if successful, JSON mode)
            body: Raw binary response (binary RPC mode)
            error: JSON-RPC error object (if failed)
            rpc_id: Matches request ID for correlation
            is_binary: True if this is a binary RPC response
            total_chunks: Total number of chunks (1 if fits in single message)
        """
        self.result = result
        self.body = body
        self.error = error
        self.rpc_id = rpc_id
        self.is_binary = is_binary
        self.total_chunks = total_chunks
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'result': self.result,
            'body': self.body,
            'error': self.error,
            'id': self.rpc_id,
            'is_binary': self.is_binary,
            'total_chunks': self.total_chunks,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)
        self.result = data.get(b'result')
        self.body = data.get(b'body')  # Keep as bytes
        self.error = data.get(b'error')

        rpc_id = data.get(b'id', b'0')
        self.rpc_id = rpc_id.decode('utf-8') if isinstance(rpc_id, bytes) else str(rpc_id) if rpc_id else '0'

        self.is_binary = data.get(b'is_binary', False)
        self.total_chunks = data.get(b'total_chunks', 1)
        self.timestamp = data.get(b'ts', time.time())


class RPCTunnelChunk(RNS.MessageBase):
    """
    Chunked response for large RPC data

    When RPC response exceeds channel MDU (~465 bytes), split into chunks.
    Client reassembles before returning to wallet-rpc.
    """
    MSGTYPE = _make_msgtype(13)

    def __init__(self, rpc_id: str = None, chunk_index: int = 0,
                 total_chunks: int = 1, chunk_data: bytes = None):
        """
        Args:
            rpc_id: Matches request ID
            chunk_index: Chunk number (0-indexed)
            total_chunks: Total number of chunks
            chunk_data: This chunk's data
        """
        self.rpc_id = rpc_id
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks
        self.chunk_data = chunk_data
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'id': self.rpc_id,
            'idx': self.chunk_index,
            'total': self.total_chunks,
            'data': self.chunk_data,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        rpc_id = data.get(b'id', b'0')
        self.rpc_id = rpc_id.decode('utf-8') if isinstance(rpc_id, bytes) else str(rpc_id) if rpc_id else '0'

        self.chunk_index = data.get(b'idx', 0)
        self.total_chunks = data.get(b'total', 1)
        self.chunk_data = data.get(b'data', b'')  # Keep as bytes
        self.timestamp = data.get(b'ts', time.time())


class ModeSelectionMessage(RNS.MessageBase):
    """
    Client announces which mode it's using on connection

    When client establishes link to hub, it sends this message to indicate
    which operating mode to use.

    Hub uses this to create appropriate session type:
    - Custodial: HubSession (hub controls wallet)
    - Non-custodial: HubRPCProxySession (client controls wallet, hub proxies RPC)
    - Cold signing: HubColdSigningSession (hub has view key, client has spend key)
    """
    MSGTYPE = _make_msgtype(12)

    MODE_CUSTODIAL = "custodial"          # Hub controls wallet
    MODE_NON_CUSTODIAL = "non_custodial"  # Client has wallet, hub proxies
    MODE_COLD_SIGNING = "cold_signing"    # Hub view key, client spend key

    def __init__(self, mode: str = MODE_NON_CUSTODIAL):
        """
        Args:
            mode: Either MODE_CUSTODIAL or MODE_NON_CUSTODIAL
        """
        self.mode = mode
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'mode': self.mode,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        # Handle both string and bytes keys (msgpack version differences)
        mode = data.get('mode') or data.get(b'mode') or 'non_custodial'
        self.mode = mode.decode('utf-8') if isinstance(mode, bytes) else mode

        self.timestamp = data.get('ts') or data.get(b'ts') or time.time()


# ============================================================================
# PEER-TO-PEER PROTOCOL MESSAGES
# ============================================================================
# Messages for peer discovery, messaging, and transaction coordination


class PeerAnnouncement(RNS.MessageBase):
    """
    Peer announces itself on the network as a ReticulumXMR peer

    Based on NomadNet announcement pattern. Includes peer display name,
    capabilities, and Monero address (optional).
    """
    MSGTYPE = _make_msgtype(20)

    def __init__(self, display_name: str = "Unknown",
                 xmr_address: str = None, capabilities: list = None):
        """
        Args:
            display_name: Human-readable name for this peer
            xmr_address: Optional Monero address for receiving payments
            capabilities: List of capabilities ["send", "receive", "trade"]
        """
        self.display_name = display_name
        self.xmr_address = xmr_address
        self.capabilities = capabilities or ["send", "receive"]
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'name': self.display_name,
            'address': self.xmr_address,
            'caps': self.capabilities,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        name = data.get(b'name', b'Unknown')
        self.display_name = name.decode('utf-8') if isinstance(name, bytes) else name

        address = data.get(b'address')
        self.xmr_address = address.decode('utf-8') if isinstance(address, bytes) else address

        self.capabilities = data.get(b'caps', ["send", "receive"])
        self.timestamp = data.get(b'ts', time.time())


class PeerMessage(RNS.MessageBase):
    """
    Direct message between peers

    Used for chat, coordination, and general peer-to-peer communication.
    Sent over established Links for reliability.
    """
    MSGTYPE = _make_msgtype(21)

    def __init__(self, content: str = "", message_type: str = "chat"):
        """
        Args:
            content: Message content (text)
            message_type: Type of message ("chat", "info", "system")
        """
        self.content = content
        self.message_type = message_type
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'content': self.content,
            'type': self.message_type,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        content = data.get(b'content', b'')
        self.content = content.decode('utf-8') if isinstance(content, bytes) else content

        msg_type = data.get(b'type', b'chat')
        self.message_type = msg_type.decode('utf-8') if isinstance(msg_type, bytes) else msg_type

        self.timestamp = data.get(b'ts', time.time())


class TransactionProposal(RNS.MessageBase):
    """
    Payment proposal from one peer to another

    Initiates a Monero transaction. Recipient can accept or reject.
    """
    MSGTYPE = _make_msgtype(22)

    def __init__(self, amount: float = 0.0, recipient_address: str = None,
                 message: str = "", proposal_id: str = None):
        """
        Args:
            amount: Amount in XMR
            recipient_address: Monero address to receive payment
            message: Optional message/note
            proposal_id: Unique ID for this proposal (auto-generated if None)
        """
        self.amount = amount
        self.recipient_address = recipient_address
        self.message = message
        self.proposal_id = proposal_id or f"tx_{int(time.time()*1000)}"
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'amount': self.amount,
            'address': self.recipient_address,
            'message': self.message,
            'id': self.proposal_id,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.amount = data.get(b'amount', 0.0)

        address = data.get(b'address')
        self.recipient_address = address.decode('utf-8') if isinstance(address, bytes) else address

        message = data.get(b'message', b'')
        self.message = message.decode('utf-8') if isinstance(message, bytes) else message

        proposal_id = data.get(b'id', b'tx_0')
        self.proposal_id = proposal_id.decode('utf-8') if isinstance(proposal_id, bytes) else proposal_id

        self.timestamp = data.get(b'ts', time.time())


class TransactionResponse(RNS.MessageBase):
    """
    Response to a transaction proposal

    Peer accepts or rejects a payment proposal.
    """
    MSGTYPE = _make_msgtype(23)

    def __init__(self, proposal_id: str = None, accepted: bool = False,
                 message: str = ""):
        """
        Args:
            proposal_id: ID of the proposal being responded to
            accepted: True if accepting, False if rejecting
            message: Optional message (reason for rejection, etc.)
        """
        self.proposal_id = proposal_id
        self.accepted = accepted
        self.message = message
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'id': self.proposal_id,
            'accepted': self.accepted,
            'message': self.message,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        proposal_id = data.get(b'id', b'')
        self.proposal_id = proposal_id.decode('utf-8') if isinstance(proposal_id, bytes) else proposal_id

        self.accepted = data.get(b'accepted', False)

        message = data.get(b'message', b'')
        self.message = message.decode('utf-8') if isinstance(message, bytes) else message

        self.timestamp = data.get(b'ts', time.time())


# ============================================================================
# MESSAGE TYPE REGISTRY
# ============================================================================
# Must be defined AFTER all message classes

MESSAGE_TYPES = [
    VersionMessage,
    AuthMessage,
    MoneroCommandMessage,
    MoneroResponseMessage,
    StatusMessage,
    RPCTunnelRequest,
    RPCTunnelResponse,
    RPCTunnelChunk,
    ModeSelectionMessage,
    # Peer-to-peer messages
    PeerAnnouncement,
    PeerMessage,
    TransactionProposal,
    TransactionResponse,
]


def register_message_types(channel: RNS.Channel.Channel):
    """Register all message types with RNS channel"""
    for msg_type in MESSAGE_TYPES:
        channel.register_message_type(msg_type)
