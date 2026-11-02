import enum


class Status(enum.IntEnum):
    """
    The status the command executor reports for the ATC.

    Mirrors `AutomatedThermalCyclerStatus.StatusCode` of the command executor.
    """

    NOT_CONNECTED = 0
    """The command executor has no connection to the ATC."""

    IDLE = 1
    """The ATC is connected and ready for the next command."""

    RUNNING = 2
    """The ATC is running a protocol, or performing diagnostics."""

    ERROR = 3
    """The last command or run failed."""


class InstrumentState(enum.IntEnum):
    """
    The state the vendor API (`com.apldbio.pcr.instrument.InstrumentState`) reports for the ATC.

    The integer values are those the command executor uses on the wire.
    """

    IDLE = 0
    STANDBY = 1
    RUNNING = 2
    ERROR = 3
    DIAGNOSTICS = 4
