#!/usr/bin/env python3
"""
ReticulumXMR View Key Protocol
Message definitions for view key architecture

Hub maintains team wallets using view keys.
Clients have spend keys only and send high-level commands.
All operations use small messages (1-6 KB) suitable for HF/LoRa.
"""
import RNS
import time

try:
    import umsgpack as msgpack
except ImportError:
    import msgpack

# Protocol constants
MSG_MAGIC = 0xCD  # ReticulumXMR magic number
PROTOCOL_VERSION = 2  # Version 2 = view key model

def _make_msgtype(val: int):
    """Create message type identifier"""
    return ((MSG_MAGIC << 8) & 0xff00) | (val & 0x00ff)


def _get_val(data: dict, key: str, default=None):
    """
    Get value from msgpack dict handling both string and bytes keys.

    Different msgpack versions return different key types:
    - Some return bytes keys (b'key')
    - Some return string keys ('key')

    This helper checks both to ensure cross-platform compatibility.
    """
    val = data.get(key)
    if val is None:
        val = data.get(key.encode('utf-8') if isinstance(key, str) else key.decode('utf-8'))
    return val if val is not None else default


# ============================================================================
# VIEW KEY PROTOCOL MESSAGES
# ============================================================================


class ProvisionWalletMessage(RNS.MessageBase):
    """
    One-time setup: Client provisions view key to hub

    Direction: Client → Hub (pre-deployment only)
    Size: ~500 bytes
    """
    MSGTYPE = _make_msgtype(30)

    def __init__(self, operator_id: str = None, view_key: str = None,
                 wallet_address: str = None, wallet_name: str = None,
                 restore_height: int = 0):
        """
        Args:
            operator_id: Unique operator identifier (e.g., "alice")
            view_key: Private view key (hex)
            wallet_address: Primary Monero address
            wallet_name: Friendly name for wallet
            restore_height: Block height to start scanning from
        """
        self.operator_id = operator_id
        self.view_key = view_key
        self.wallet_address = wallet_address
        self.wallet_name = wallet_name
        self.restore_height = restore_height
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'view_key': self.view_key,
            'wallet_address': self.wallet_address,
            'wallet_name': self.wallet_name,
            'restore_height': self.restore_height,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        view_key = _get_val(data, 'view_key', b'')
        self.view_key = view_key.decode('utf-8') if isinstance(view_key, bytes) else view_key

        wallet_address = _get_val(data, 'wallet_address', b'')
        self.wallet_address = wallet_address.decode('utf-8') if isinstance(wallet_address, bytes) else wallet_address

        wallet_name = _get_val(data, 'wallet_name', b'')
        self.wallet_name = wallet_name.decode('utf-8') if isinstance(wallet_name, bytes) else wallet_name

        self.restore_height = _get_val(data, 'restore_height', 0)
        self.timestamp = _get_val(data, 'ts', time.time())


class ProvisionAckMessage(RNS.MessageBase):
    """
    Hub acknowledges wallet provisioning

    Direction: Hub → Client
    Size: ~300 bytes
    """
    MSGTYPE = _make_msgtype(31)

    def __init__(self, success: bool = True, operator_id: str = None,
                 status: str = None, error: str = None):
        """
        Args:
            success: Whether provisioning succeeded
            operator_id: Operator ID from request
            status: Status message
            error: Error message if failed
        """
        self.success = success
        self.operator_id = operator_id
        self.status = status
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'operator_id': self.operator_id,
            'status': self.status,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        status = _get_val(data, 'status')
        self.status = status.decode('utf-8') if isinstance(status, bytes) else status

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class BalanceRequestMessage(RNS.MessageBase):
    """
    Request current balance

    Direction: Client → Hub
    Size: ~200 bytes
    """
    MSGTYPE = _make_msgtype(32)

    def __init__(self, operator_id: str = None, request_id: str = None):
        """
        Args:
            operator_id: Operator requesting balance
            request_id: Unique request ID for tracking
        """
        self.operator_id = operator_id
        self.request_id = request_id or f"req_{int(time.time()*1000)}"
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'request_id': self.request_id,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.timestamp = _get_val(data, 'ts', time.time())


class BalanceResponseMessage(RNS.MessageBase):
    """
    Return current balance

    Direction: Hub → Client
    Size: ~300 bytes
    """
    MSGTYPE = _make_msgtype(33)

    def __init__(self, success: bool = True, request_id: str = None,
                 balance: float = 0.0, unlocked_balance: float = 0.0,
                 balance_atomic: int = 0, block_height: int = 0,
                 blocks_to_unlock: int = 0, error: str = None):
        """
        Args:
            success: Whether request succeeded
            request_id: Matches request ID
            balance: Total balance in XMR
            unlocked_balance: Spendable balance in XMR
            balance_atomic: Balance in atomic units
            block_height: Current blockchain height
            blocks_to_unlock: Blocks until funds unlock
            error: Error message if failed
        """
        self.success = success
        self.request_id = request_id
        self.balance = balance
        self.unlocked_balance = unlocked_balance
        self.balance_atomic = balance_atomic
        self.block_height = block_height
        self.blocks_to_unlock = blocks_to_unlock
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'request_id': self.request_id,
            'balance': self.balance,
            'unlocked_balance': self.unlocked_balance,
            'balance_atomic': self.balance_atomic,
            'block_height': self.block_height,
            'blocks_to_unlock': self.blocks_to_unlock,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.balance = _get_val(data, 'balance', 0.0)
        self.unlocked_balance = _get_val(data, 'unlocked_balance', 0.0)
        self.balance_atomic = _get_val(data, 'balance_atomic', 0)
        self.block_height = _get_val(data, 'block_height', 0)
        self.blocks_to_unlock = _get_val(data, 'blocks_to_unlock', 0)

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class CreateTransactionMessage(RNS.MessageBase):
    """
    Request unsigned transaction

    Direction: Client → Hub
    Size: ~400 bytes
    """
    MSGTYPE = _make_msgtype(34)

    def __init__(self, operator_id: str = None, request_id: str = None,
                 destination: str = None, amount: float = 0.0,
                 priority: int = 1, description: str = ""):
        """
        Args:
            operator_id: Operator making transaction
            request_id: Unique request ID
            destination: Recipient XMR address
            amount: Amount in XMR
            priority: 0=default, 1=elevated, 2=high
            description: Optional memo (client-side only)
        """
        self.operator_id = operator_id
        self.request_id = request_id or f"tx_{int(time.time()*1000)}"
        self.destination = destination
        self.amount = amount
        self.priority = priority
        self.description = description
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'request_id': self.request_id,
            'destination': self.destination,
            'amount': self.amount,
            'priority': self.priority,
            'description': self.description,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', '')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        request_id = _get_val(data, 'request_id', '')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        destination = _get_val(data, 'destination', '')
        self.destination = destination.decode('utf-8') if isinstance(destination, bytes) else destination

        self.amount = _get_val(data, 'amount', 0.0)
        self.priority = _get_val(data, 'priority', 1)

        description = _get_val(data, 'description', '')
        self.description = description.decode('utf-8') if isinstance(description, bytes) else description

        self.timestamp = _get_val(data, 'ts', time.time())


class UnsignedTransactionMessage(RNS.MessageBase):
    """
    Return unsigned transaction

    Direction: Hub → Client
    Size: ~2-4 KB
    """
    MSGTYPE = _make_msgtype(35)

    def __init__(self, success: bool = True, request_id: str = None,
                 unsigned_tx: str = None, tx_key: str = None,
                 fee: float = 0.0, total: float = 0.0,
                 destinations: list = None, change: float = 0.0,
                 error: str = None):
        """
        Args:
            success: Whether transaction creation succeeded
            request_id: Matches request ID
            unsigned_tx: Unsigned transaction blob (hex)
            tx_key: Transaction key for tracking
            fee: Network fee in XMR
            total: Amount + fee
            destinations: Output details
            change: Change amount in XMR
            error: Error message if failed
        """
        self.success = success
        self.request_id = request_id
        self.unsigned_tx = unsigned_tx
        self.tx_key = tx_key
        self.fee = fee
        self.total = total
        self.destinations = destinations or []
        self.change = change
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'request_id': self.request_id,
            'unsigned_tx': self.unsigned_tx,
            'tx_key': self.tx_key,
            'fee': self.fee,
            'total': self.total,
            'destinations': self.destinations,
            'change': self.change,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        unsigned_tx = _get_val(data, 'unsigned_tx')
        self.unsigned_tx = unsigned_tx.decode('utf-8') if isinstance(unsigned_tx, bytes) else unsigned_tx

        tx_key = _get_val(data, 'tx_key')
        self.tx_key = tx_key.decode('utf-8') if isinstance(tx_key, bytes) else tx_key

        self.fee = _get_val(data, 'fee', 0.0)
        self.total = _get_val(data, 'total', 0.0)
        self.destinations = _get_val(data, 'destinations', [])
        self.change = _get_val(data, 'change', 0.0)

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class SignedTransactionMessage(RNS.MessageBase):
    """
    Submit signed transaction for broadcast

    Direction: Client → Hub
    Size: ~3-5 KB
    """
    MSGTYPE = _make_msgtype(36)

    def __init__(self, operator_id: str = None, request_id: str = None,
                 signed_tx: str = None):
        """
        Args:
            operator_id: Operator submitting transaction
            request_id: Matches request ID
            signed_tx: Signed transaction blob (hex)
        """
        self.operator_id = operator_id
        self.request_id = request_id
        self.signed_tx = signed_tx
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'request_id': self.request_id,
            'signed_tx': self.signed_tx,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        signed_tx = _get_val(data, 'signed_tx')
        self.signed_tx = signed_tx.decode('utf-8') if isinstance(signed_tx, bytes) else signed_tx

        self.timestamp = _get_val(data, 'ts', time.time())


class TransactionResultMessage(RNS.MessageBase):
    """
    Confirmation of transaction broadcast

    Direction: Hub → Client
    Size: ~400 bytes
    """
    MSGTYPE = _make_msgtype(37)

    def __init__(self, success: bool = True, request_id: str = None,
                 tx_hash: str = None, tx_key: str = None,
                 fee: float = 0.0, status: str = "broadcast",
                 error: str = None):
        """
        Args:
            success: Whether broadcast succeeded
            request_id: Matches request ID
            tx_hash: Transaction hash
            tx_key: Transaction key for recipient verification
            fee: Network fee in XMR
            status: "broadcast", "pending", "confirmed"
            error: Error message if failed
        """
        self.success = success
        self.request_id = request_id
        self.tx_hash = tx_hash
        self.tx_key = tx_key
        self.fee = fee
        self.status = status
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'request_id': self.request_id,
            'tx_hash': self.tx_hash,
            'tx_key': self.tx_key,
            'fee': self.fee,
            'status': self.status,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        tx_hash = _get_val(data, 'tx_hash')
        self.tx_hash = tx_hash.decode('utf-8') if isinstance(tx_hash, bytes) else tx_hash

        tx_key = _get_val(data, 'tx_key')
        self.tx_key = tx_key.decode('utf-8') if isinstance(tx_key, bytes) else tx_key

        self.fee = _get_val(data, 'fee', 0.0)

        status = _get_val(data, 'status', b'broadcast')
        self.status = status.decode('utf-8') if isinstance(status, bytes) else status

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class TransactionHistoryMessage(RNS.MessageBase):
    """
    Request transaction history

    Direction: Client → Hub
    Size: ~200 bytes
    """
    MSGTYPE = _make_msgtype(38)

    def __init__(self, operator_id: str = None, request_id: str = None,
                 limit: int = 10, min_height: int = 0):
        """
        Args:
            operator_id: Operator requesting history
            request_id: Unique request ID
            limit: Max transactions to return
            min_height: Optional: only after this block
        """
        self.operator_id = operator_id
        self.request_id = request_id or f"hist_{int(time.time()*1000)}"
        self.limit = limit
        self.min_height = min_height
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'request_id': self.request_id,
            'limit': self.limit,
            'min_height': self.min_height,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.limit = _get_val(data, 'limit', 10)
        self.min_height = _get_val(data, 'min_height', 0)
        self.timestamp = _get_val(data, 'ts', time.time())


class HistoryResponseMessage(RNS.MessageBase):
    """
    Return transaction history

    Direction: Hub → Client
    Size: ~1-5 KB (depends on history)
    """
    MSGTYPE = _make_msgtype(39)

    def __init__(self, success: bool = True, request_id: str = None,
                 transactions: list = None, error: str = None):
        """
        Args:
            success: Whether request succeeded
            request_id: Matches request ID
            transactions: List of transaction dicts
            error: Error message if failed
        """
        self.success = success
        self.request_id = request_id
        self.transactions = transactions or []
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'request_id': self.request_id,
            'transactions': self.transactions,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.transactions = _get_val(data, 'transactions', [])

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class ExportOutputsRequestMessage(RNS.MessageBase):
    """
    Request outputs export from hub for cold wallet setup

    Direction: Client → Hub
    Size: ~200 bytes
    """
    MSGTYPE = _make_msgtype(41)

    def __init__(self, operator_id: str = None, request_id: str = None,
                 all_outputs: bool = False):
        """
        Args:
            operator_id: Operator requesting outputs
            request_id: Unique request ID
            all_outputs: Export all outputs (True) or only new (False)
        """
        self.operator_id = operator_id
        self.request_id = request_id or f"out_{int(time.time()*1000)}"
        self.all_outputs = all_outputs
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'request_id': self.request_id,
            'all': self.all_outputs,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.all_outputs = _get_val(data, 'all', False)
        self.timestamp = _get_val(data, 'ts', time.time())


class ExportOutputsResponseMessage(RNS.MessageBase):
    """
    Return exported outputs data

    Direction: Hub → Client
    Size: Variable (can be large for many outputs)
    """
    MSGTYPE = _make_msgtype(42)

    def __init__(self, success: bool = True, request_id: str = None,
                 outputs_data_hex: str = None, error: str = None):
        """
        Args:
            success: Whether export succeeded
            request_id: Matches request ID
            outputs_data_hex: Exported outputs in hex format
            error: Error message if failed
        """
        self.success = success
        self.request_id = request_id
        self.outputs_data_hex = outputs_data_hex
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'request_id': self.request_id,
            'outputs': self.outputs_data_hex,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        outputs = _get_val(data, 'outputs')
        self.outputs_data_hex = outputs.decode('utf-8') if isinstance(outputs, bytes) else outputs

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class ImportKeyImagesMessage(RNS.MessageBase):
    """
    Client sends key images to hub for balance tracking

    Direction: Client → Hub
    Size: Variable (~100 bytes per key image)
    """
    MSGTYPE = _make_msgtype(43)

    def __init__(self, operator_id: str = None, request_id: str = None,
                 signed_key_images: list = None, offset: int = 0):
        """
        Args:
            operator_id: Operator sending key images
            request_id: Unique request ID
            signed_key_images: List of {"key_image": str, "signature": str}
            offset: Starting offset for key images
        """
        self.operator_id = operator_id
        self.request_id = request_id or f"ki_{int(time.time()*1000)}"
        self.signed_key_images = signed_key_images or []
        self.offset = offset
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'request_id': self.request_id,
            'key_images': self.signed_key_images,
            'offset': self.offset,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.signed_key_images = _get_val(data, 'key_images', [])
        self.offset = _get_val(data, 'offset', 0)
        self.timestamp = _get_val(data, 'ts', time.time())


class ImportKeyImagesResponseMessage(RNS.MessageBase):
    """
    Hub confirms key image import

    Direction: Hub → Client
    Size: ~300 bytes
    """
    MSGTYPE = _make_msgtype(44)

    def __init__(self, success: bool = True, request_id: str = None,
                 height: int = 0, spent: int = 0, unspent: int = 0,
                 error: str = None):
        """
        Args:
            success: Whether import succeeded
            request_id: Matches request ID
            height: Current height
            spent: Amount spent (atomic units)
            unspent: Amount unspent (atomic units)
            error: Error message if failed
        """
        self.success = success
        self.request_id = request_id
        self.height = height
        self.spent = spent
        self.unspent = unspent
        self.error = error
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'success': self.success,
            'request_id': self.request_id,
            'height': self.height,
            'spent': self.spent,
            'unspent': self.unspent,
            'error': self.error,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        self.success = _get_val(data, 'success', True)

        request_id = _get_val(data, 'request_id', b'')
        self.request_id = request_id.decode('utf-8') if isinstance(request_id, bytes) else request_id

        self.height = _get_val(data, 'height', 0)
        self.spent = _get_val(data, 'spent', 0)
        self.unspent = _get_val(data, 'unspent', 0)

        error = _get_val(data, 'error')
        self.error = error.decode('utf-8') if isinstance(error, bytes) else error

        self.timestamp = _get_val(data, 'ts', time.time())


class ViewKeyStatusMessage(RNS.MessageBase):
    """
    Hub pushes status updates to client

    Direction: Hub → Client
    Size: ~500 bytes
    """
    MSGTYPE = _make_msgtype(40)

    def __init__(self, operator_id: str = None,
                 event_type: str = "info", tx_hash: str = None,
                 amount: float = 0.0, message: str = None):
        """
        Args:
            operator_id: Operator this message is for
            event_type: "incoming_tx", "tx_confirmed", "sync_complete", "info"
            tx_hash: Transaction hash if tx-related
            amount: Amount if tx-related (XMR)
            message: Human-readable message
        """
        self.operator_id = operator_id
        self.event_type = event_type
        self.tx_hash = tx_hash
        self.amount = amount
        self.message = message
        self.timestamp = time.time()

    def pack(self) -> bytes:
        return msgpack.packb({
            'operator_id': self.operator_id,
            'event_type': self.event_type,
            'tx_hash': self.tx_hash,
            'amount': self.amount,
            'message': self.message,
            'ts': self.timestamp
        })

    def unpack(self, raw: bytes):
        data = msgpack.unpackb(raw)

        operator_id = _get_val(data, 'operator_id', b'')
        self.operator_id = operator_id.decode('utf-8') if isinstance(operator_id, bytes) else operator_id

        event_type = _get_val(data, 'event_type', b'info')
        self.event_type = event_type.decode('utf-8') if isinstance(event_type, bytes) else event_type

        tx_hash = _get_val(data, 'tx_hash')
        self.tx_hash = tx_hash.decode('utf-8') if isinstance(tx_hash, bytes) else tx_hash

        self.amount = _get_val(data, 'amount', 0.0)

        message = _get_val(data, 'message')
        self.message = message.decode('utf-8') if isinstance(message, bytes) else message

        self.timestamp = _get_val(data, 'ts', time.time())


# ============================================================================
# MESSAGE TYPE REGISTRY
# ============================================================================

VIEW_KEY_MESSAGE_TYPES = [
    ProvisionWalletMessage,
    ProvisionAckMessage,
    BalanceRequestMessage,
    BalanceResponseMessage,
    CreateTransactionMessage,
    UnsignedTransactionMessage,
    SignedTransactionMessage,
    TransactionResultMessage,
    TransactionHistoryMessage,
    HistoryResponseMessage,
    ExportOutputsRequestMessage,
    ExportOutputsResponseMessage,
    ImportKeyImagesMessage,
    ImportKeyImagesResponseMessage,
    ViewKeyStatusMessage,
]


def register_view_key_messages(channel: RNS.Channel.Channel):
    """Register all view key message types with RNS channel"""
    for msg_type in VIEW_KEY_MESSAGE_TYPES:
        channel.register_message_type(msg_type)
