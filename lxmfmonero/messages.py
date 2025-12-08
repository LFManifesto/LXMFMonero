"""
Message type definitions for LXMFMonero

All messages are JSON-encoded and sent via LXMF. LXMF handles large
payloads automatically using RNS.Resource when needed.
"""

from enum import Enum
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import json
import uuid
import time


class MessageType(str, Enum):
    """Message types for LXMFMonero protocol"""

    # Requests (Client -> Hub)
    BALANCE_REQUEST = "balance_request"
    EXPORT_OUTPUTS = "export_outputs"
    CREATE_TX = "create_tx"
    SUBMIT_TX = "submit_tx"
    IMPORT_KEY_IMAGES = "import_key_images"

    # Responses (Hub -> Client)
    BALANCE_RESPONSE = "balance_response"
    EXPORT_OUTPUTS_RESPONSE = "export_outputs_response"
    CREATE_TX_RESPONSE = "create_tx_response"
    SUBMIT_TX_RESPONSE = "submit_tx_response"
    IMPORT_KEY_IMAGES_RESPONSE = "import_key_images_response"

    # Errors
    ERROR = "error"


@dataclass
class BaseMessage:
    """Base class for all messages"""
    type: str
    request_id: str
    timestamp: float

    def to_json(self) -> str:
        """Serialize message to JSON"""
        return json.dumps(asdict(self))

    def to_bytes(self) -> bytes:
        """Serialize message to bytes"""
        return self.to_json().encode('utf-8')

    @classmethod
    def from_json(cls, data: str) -> 'BaseMessage':
        """Deserialize from JSON string"""
        parsed = json.loads(data)
        return cls.from_dict(parsed)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'BaseMessage':
        """Deserialize from bytes"""
        return cls.from_json(data.decode('utf-8'))

    @classmethod
    def from_dict(cls, data: dict) -> 'BaseMessage':
        """Create message from dict - subclasses should override"""
        raise NotImplementedError


def generate_request_id() -> str:
    """Generate unique request ID"""
    return str(uuid.uuid4())


def current_timestamp() -> float:
    """Get current timestamp"""
    return time.time()


# Request Messages (Client -> Hub)

@dataclass
class BalanceRequest(BaseMessage):
    """Request wallet balance"""
    operator_id: str

    def __init__(self, operator_id: str, request_id: str = None):
        self.type = MessageType.BALANCE_REQUEST.value
        self.request_id = request_id or generate_request_id()
        self.timestamp = current_timestamp()
        self.operator_id = operator_id

    @classmethod
    def from_dict(cls, data: dict) -> 'BalanceRequest':
        msg = cls(
            operator_id=data.get("operator_id", ""),
            request_id=data.get("request_id")
        )
        msg.timestamp = data.get("timestamp", current_timestamp())
        return msg


@dataclass
class ExportOutputsRequest(BaseMessage):
    """Request outputs export from view-only wallet"""
    operator_id: str
    all_outputs: bool

    def __init__(self, operator_id: str, all_outputs: bool = True, request_id: str = None):
        self.type = MessageType.EXPORT_OUTPUTS.value
        self.request_id = request_id or generate_request_id()
        self.timestamp = current_timestamp()
        self.operator_id = operator_id
        self.all_outputs = all_outputs

    @classmethod
    def from_dict(cls, data: dict) -> 'ExportOutputsRequest':
        msg = cls(
            operator_id=data.get("operator_id", ""),
            all_outputs=data.get("all_outputs", True),
            request_id=data.get("request_id")
        )
        msg.timestamp = data.get("timestamp", current_timestamp())
        return msg


@dataclass
class CreateTxRequest(BaseMessage):
    """Request unsigned transaction creation"""
    operator_id: str
    destination: str
    amount: float  # In XMR
    priority: int

    def __init__(self, operator_id: str, destination: str, amount: float,
                 priority: int = 1, request_id: str = None):
        self.type = MessageType.CREATE_TX.value
        self.request_id = request_id or generate_request_id()
        self.timestamp = current_timestamp()
        self.operator_id = operator_id
        self.destination = destination
        self.amount = amount
        self.priority = priority

    @classmethod
    def from_dict(cls, data: dict) -> 'CreateTxRequest':
        msg = cls(
            operator_id=data.get("operator_id", ""),
            destination=data.get("destination", ""),
            amount=data.get("amount", 0.0),
            priority=data.get("priority", 1),
            request_id=data.get("request_id")
        )
        msg.timestamp = data.get("timestamp", current_timestamp())
        return msg


@dataclass
class SubmitTxRequest(BaseMessage):
    """Submit signed transaction for broadcast"""
    operator_id: str
    signed_txset: str

    def __init__(self, operator_id: str, signed_txset: str, request_id: str = None):
        self.type = MessageType.SUBMIT_TX.value
        self.request_id = request_id or generate_request_id()
        self.timestamp = current_timestamp()
        self.operator_id = operator_id
        self.signed_txset = signed_txset

    @classmethod
    def from_dict(cls, data: dict) -> 'SubmitTxRequest':
        msg = cls(
            operator_id=data.get("operator_id", ""),
            signed_txset=data.get("signed_txset", ""),
            request_id=data.get("request_id")
        )
        msg.timestamp = data.get("timestamp", current_timestamp())
        return msg


@dataclass
class ImportKeyImagesRequest(BaseMessage):
    """Import key images from cold wallet"""
    operator_id: str
    signed_key_images: List[Dict]
    offset: int

    def __init__(self, operator_id: str, signed_key_images: List[Dict],
                 offset: int = 0, request_id: str = None):
        self.type = MessageType.IMPORT_KEY_IMAGES.value
        self.request_id = request_id or generate_request_id()
        self.timestamp = current_timestamp()
        self.operator_id = operator_id
        self.signed_key_images = signed_key_images
        self.offset = offset

    @classmethod
    def from_dict(cls, data: dict) -> 'ImportKeyImagesRequest':
        msg = cls(
            operator_id=data.get("operator_id", ""),
            signed_key_images=data.get("signed_key_images", []),
            offset=data.get("offset", 0),
            request_id=data.get("request_id")
        )
        msg.timestamp = data.get("timestamp", current_timestamp())
        return msg


# Response Messages (Hub -> Client)

@dataclass
class BalanceResponse(BaseMessage):
    """Balance query response"""
    success: bool
    balance: float  # In XMR
    unlocked_balance: float  # In XMR
    block_height: int
    error: Optional[str]

    def __init__(self, request_id: str, success: bool,
                 balance: float = 0.0, unlocked_balance: float = 0.0,
                 block_height: int = 0, error: str = None):
        self.type = MessageType.BALANCE_RESPONSE.value
        self.request_id = request_id
        self.timestamp = current_timestamp()
        self.success = success
        self.balance = balance
        self.unlocked_balance = unlocked_balance
        self.block_height = block_height
        self.error = error

    @classmethod
    def from_dict(cls, data: dict) -> 'BalanceResponse':
        return cls(
            request_id=data.get("request_id", ""),
            success=data.get("success", False),
            balance=data.get("balance", 0.0),
            unlocked_balance=data.get("unlocked_balance", 0.0),
            block_height=data.get("block_height", 0),
            error=data.get("error")
        )


@dataclass
class ExportOutputsResponse(BaseMessage):
    """Export outputs response"""
    success: bool
    outputs_data_hex: str
    error: Optional[str]

    def __init__(self, request_id: str, success: bool,
                 outputs_data_hex: str = "", error: str = None):
        self.type = MessageType.EXPORT_OUTPUTS_RESPONSE.value
        self.request_id = request_id
        self.timestamp = current_timestamp()
        self.success = success
        self.outputs_data_hex = outputs_data_hex
        self.error = error

    @classmethod
    def from_dict(cls, data: dict) -> 'ExportOutputsResponse':
        return cls(
            request_id=data.get("request_id", ""),
            success=data.get("success", False),
            outputs_data_hex=data.get("outputs_data_hex", ""),
            error=data.get("error")
        )


@dataclass
class CreateTxResponse(BaseMessage):
    """Create unsigned transaction response"""
    success: bool
    unsigned_txset: str
    fee: float  # In XMR
    amount: float  # In XMR
    error: Optional[str]

    def __init__(self, request_id: str, success: bool,
                 unsigned_txset: str = "", fee: float = 0.0,
                 amount: float = 0.0, error: str = None):
        self.type = MessageType.CREATE_TX_RESPONSE.value
        self.request_id = request_id
        self.timestamp = current_timestamp()
        self.success = success
        self.unsigned_txset = unsigned_txset
        self.fee = fee
        self.amount = amount
        self.error = error

    @classmethod
    def from_dict(cls, data: dict) -> 'CreateTxResponse':
        return cls(
            request_id=data.get("request_id", ""),
            success=data.get("success", False),
            unsigned_txset=data.get("unsigned_txset", ""),
            fee=data.get("fee", 0.0),
            amount=data.get("amount", 0.0),
            error=data.get("error")
        )


@dataclass
class SubmitTxResponse(BaseMessage):
    """Submit transaction response"""
    success: bool
    tx_hash: str
    error: Optional[str]

    def __init__(self, request_id: str, success: bool,
                 tx_hash: str = "", error: str = None):
        self.type = MessageType.SUBMIT_TX_RESPONSE.value
        self.request_id = request_id
        self.timestamp = current_timestamp()
        self.success = success
        self.tx_hash = tx_hash
        self.error = error

    @classmethod
    def from_dict(cls, data: dict) -> 'SubmitTxResponse':
        return cls(
            request_id=data.get("request_id", ""),
            success=data.get("success", False),
            tx_hash=data.get("tx_hash", ""),
            error=data.get("error")
        )


@dataclass
class ImportKeyImagesResponse(BaseMessage):
    """Import key images response"""
    success: bool
    height: int
    spent: int  # Atomic units
    unspent: int  # Atomic units
    error: Optional[str]

    def __init__(self, request_id: str, success: bool,
                 height: int = 0, spent: int = 0, unspent: int = 0,
                 error: str = None):
        self.type = MessageType.IMPORT_KEY_IMAGES_RESPONSE.value
        self.request_id = request_id
        self.timestamp = current_timestamp()
        self.success = success
        self.height = height
        self.spent = spent
        self.unspent = unspent
        self.error = error

    @classmethod
    def from_dict(cls, data: dict) -> 'ImportKeyImagesResponse':
        return cls(
            request_id=data.get("request_id", ""),
            success=data.get("success", False),
            height=data.get("height", 0),
            spent=data.get("spent", 0),
            unspent=data.get("unspent", 0),
            error=data.get("error")
        )


@dataclass
class ErrorResponse(BaseMessage):
    """Generic error response"""
    error: str

    def __init__(self, request_id: str, error: str):
        self.type = MessageType.ERROR.value
        self.request_id = request_id
        self.timestamp = current_timestamp()
        self.error = error

    @classmethod
    def from_dict(cls, data: dict) -> 'ErrorResponse':
        return cls(
            request_id=data.get("request_id", ""),
            error=data.get("error", "Unknown error")
        )


# Message parsing

MESSAGE_CLASSES = {
    MessageType.BALANCE_REQUEST.value: BalanceRequest,
    MessageType.EXPORT_OUTPUTS.value: ExportOutputsRequest,
    MessageType.CREATE_TX.value: CreateTxRequest,
    MessageType.SUBMIT_TX.value: SubmitTxRequest,
    MessageType.IMPORT_KEY_IMAGES.value: ImportKeyImagesRequest,
    MessageType.BALANCE_RESPONSE.value: BalanceResponse,
    MessageType.EXPORT_OUTPUTS_RESPONSE.value: ExportOutputsResponse,
    MessageType.CREATE_TX_RESPONSE.value: CreateTxResponse,
    MessageType.SUBMIT_TX_RESPONSE.value: SubmitTxResponse,
    MessageType.IMPORT_KEY_IMAGES_RESPONSE.value: ImportKeyImagesResponse,
    MessageType.ERROR.value: ErrorResponse,
}


def parse_message(data: str) -> BaseMessage:
    """
    Parse JSON message into appropriate message class

    Args:
        data: JSON string or bytes

    Returns:
        Parsed message object

    Raises:
        ValueError: If message type unknown or parsing fails
    """
    if isinstance(data, bytes):
        data = data.decode('utf-8')

    parsed = json.loads(data)
    msg_type = parsed.get("type")

    if msg_type not in MESSAGE_CLASSES:
        raise ValueError(f"Unknown message type: {msg_type}")

    return MESSAGE_CLASSES[msg_type].from_dict(parsed)


def is_request(msg_type: str) -> bool:
    """Check if message type is a request"""
    return msg_type in [
        MessageType.BALANCE_REQUEST.value,
        MessageType.EXPORT_OUTPUTS.value,
        MessageType.CREATE_TX.value,
        MessageType.SUBMIT_TX.value,
        MessageType.IMPORT_KEY_IMAGES.value,
    ]


def is_response(msg_type: str) -> bool:
    """Check if message type is a response"""
    return msg_type in [
        MessageType.BALANCE_RESPONSE.value,
        MessageType.EXPORT_OUTPUTS_RESPONSE.value,
        MessageType.CREATE_TX_RESPONSE.value,
        MessageType.SUBMIT_TX_RESPONSE.value,
        MessageType.IMPORT_KEY_IMAGES_RESPONSE.value,
        MessageType.ERROR.value,
    ]
