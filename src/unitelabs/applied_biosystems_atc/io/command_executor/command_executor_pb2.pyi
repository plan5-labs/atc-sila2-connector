from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class LoadRequest(_message.Message):
    __slots__ = ("protocolFileData",)
    PROTOCOLFILEDATA_FIELD_NUMBER: _ClassVar[int]
    protocolFileData: bytes
    def __init__(self, protocolFileData: _Optional[bytes] = ...) -> None: ...

class LoadResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ValidateRequest(_message.Message):
    __slots__ = ("protocolFileData", "maxSampleVolume")
    PROTOCOLFILEDATA_FIELD_NUMBER: _ClassVar[int]
    MAXSAMPLEVOLUME_FIELD_NUMBER: _ClassVar[int]
    protocolFileData: bytes
    maxSampleVolume: float
    def __init__(self, protocolFileData: _Optional[bytes] = ..., maxSampleVolume: _Optional[float] = ...) -> None: ...

class ValidateResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class OpenLidRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class OpenLidResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CloseLidRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CloseLidResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartRunRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartRunResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StopRunRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StopRunResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetInstrumentStateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetInstrumentStateResponse(_message.Message):
    __slots__ = ("instrumentState",)
    INSTRUMENTSTATE_FIELD_NUMBER: _ClassVar[int]
    instrumentState: int
    def __init__(self, instrumentState: _Optional[int] = ...) -> None: ...

class ResetRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ResetResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeElapsedTimeRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeElapsedTimeResponse(_message.Message):
    __slots__ = ("elapsedTime",)
    ELAPSEDTIME_FIELD_NUMBER: _ClassVar[int]
    elapsedTime: int
    def __init__(self, elapsedTime: _Optional[int] = ...) -> None: ...

class SubscribeRemainingTimeRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeRemainingTimeResponse(_message.Message):
    __slots__ = ("remainingTime",)
    REMAININGTIME_FIELD_NUMBER: _ClassVar[int]
    remainingTime: int
    def __init__(self, remainingTime: _Optional[int] = ...) -> None: ...

class SubscribeStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SubscribeStatusResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: int
    def __init__(self, status: _Optional[int] = ...) -> None: ...
