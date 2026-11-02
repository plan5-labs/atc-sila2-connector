class NotInitialized(Exception):
    """
    Automated Thermal Cycler (ATC) is not initialized.

    The possible causes are as follows:
    * ATC is not connected to the PC running AutomatedThermalCyclerController.
    * The configuration for ATC (ex. HostName) is incorrect.
    """


class InstrumentErrorOccurred(Exception):
    """An error occurred on the instrument during command execution. Inspect the instrument."""


class InvalidInstrumentStatusError(Exception):
    """The instrument is not in a valid status to accept the specified command."""


class ProtocolNotLoaded(Exception):
    """Protocol file has not been loaded."""


class ProtocolNotValidated(Exception):
    """Protocol file has been loaded but not validated."""


class InvalidProtocol(Exception):
    """Protocol file is invalid."""


class CommandExecutorUnavailable(Exception):
    """The connector cannot reach the ATC command executor."""
