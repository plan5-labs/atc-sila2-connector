import typing_extensions as typing

from unitelabs.cdk import sila

from ...io import (
    AutomatedThermalCyclerProtocol,
    InstrumentErrorOccurred,
    InvalidInstrumentStatusError,
    InvalidProtocol,
    NotInitialized,
    ProtocolNotLoaded,
    ProtocolNotValidated,
    format_duration,
    watch,
)


class AutomatedThermalCyclerController(sila.Feature):
    """
    A SiLA Server for controlling the Automated Thermal Cycler (ATC) made by Thermo Fisher Scientific.

    The Automated Thermal Cycler is a small, easy-to-integrate thermal cycler.
    It supports 96-well and 0.2-mL sample block configuration (compatible with full- or half-skirted plates).
    Model number    : A31487
    Product URL     : https://www.thermofisher.com/order/catalog/product/A31487
    Firmware Version: v1.2.0
    """

    def __init__(self, protocol: AutomatedThermalCyclerProtocol):
        super().__init__(originator="org.riken", category="instruments")
        self.protocol = protocol

    @sila.ObservableCommand(
        errors=[NotInitialized, InstrumentErrorOccurred, InvalidInstrumentStatusError, InvalidProtocol]
    )
    async def load(self, protocol_file_data: bytes) -> None:
        """
        Load the protocol file.

        Calling this command invokes the instrument command load.

        Status required to execute this command: Idle
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes: Same as the status at the start of execution

        Args:
          ProtocolFileData: Protocol file in binary form. The original protocol file is expected to be in XML
            format.
            Note: The file must be encoded in UTF-8.
        """

        await self.protocol.load(protocol_file_data)

    @sila.ObservableCommand(
        errors=[
            NotInitialized,
            InstrumentErrorOccurred,
            InvalidInstrumentStatusError,
            ProtocolNotLoaded,
            InvalidProtocol,
        ]
    )
    async def validate(self, max_sample_volume: float) -> None:
        """
        Validate the protocol file.

        Calling this command invokes the instrument command validate.

        Status required to execute this command: Idle
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes: Same as the status at the start of execution

        Args:
          MaxSampleVolume: Upper limit of sample volume.
            If set to 0, the default value is used.
        """

        await self.protocol.validate(max_sample_volume)

    @sila.ObservableCommand(errors=[NotInitialized, InstrumentErrorOccurred, InvalidInstrumentStatusError])
    async def open_lid(self) -> None:
        """
        Open the lid of the ATC.

        Calling this command invokes the instrument command openLid.

        Status required to execute this command: Idle
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes
          If it completes normally: Same as the status at the start of execution
          If an error occurs: Error
        """

        await self.protocol.open_lid()

    @sila.ObservableCommand(errors=[NotInitialized, InstrumentErrorOccurred, InvalidInstrumentStatusError])
    async def close_lid(self) -> None:
        """
        Close the lid of the ATC.

        Calling this command invokes the instrument command closeLid.

        Status required to execute this command: Idle
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes
          If it completes normally: Same as the status at the start of execution
          If an error occurs: Error
        """

        await self.protocol.close_lid()

    @sila.ObservableCommand(
        errors=[
            NotInitialized,
            InstrumentErrorOccurred,
            InvalidInstrumentStatusError,
            ProtocolNotLoaded,
            ProtocolNotValidated,
        ]
    )
    async def start_run(self) -> None:
        """
        Start to run using the already loaded protocol file.

        Note: Execute the following commands in advance.
        * Load
        * Validate
        * Close Lid

        Calling this command invokes the instrument command startRun, getElapsedTime, getRemainingTime.

        Status required to execute this command: Idle
        Status while this command is running: Running
        Status after this command finishes
          If it completes normally: Running
          If an error occurs: Error
        Note: After the protocol finishes, the status is updated according to the result:
          Normal completion: Idle
          Error occurred: Error
        """

        await self.protocol.start_run()

    @sila.ObservableCommand(errors=[NotInitialized, InstrumentErrorOccurred, InvalidInstrumentStatusError])
    async def stop_run(self) -> None:
        """
        Stop running.

        If this command is sent when the instrument is not running, an error occurs.

        Calling this command invokes the instrument command stopRun.

        Status required to execute this command: Running
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes
          If it completes normally: Same as the status at the start of execution
          If an error occurs: Error
        Note: After stop running, the status is updated according to the result:
          Normal completion: Idle
          Error occurred: Error
        """

        await self.protocol.stop_run()

    @sila.UnobservableCommand(errors=[NotInitialized, InstrumentErrorOccurred])
    async def get_instrument_state(
        self,
    ) -> typing.Annotated[int, sila.constraints.MinimalInclusive(0), sila.constraints.MaximalInclusive(4)]:
        """
        Get the state of the instrument.

        Calling this command invokes the instrument command getInstrumentState.

        Status required to execute this command: Idle, Running, Error
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes
          If it completes normally: Same as the status at the start of execution
          If an error occurs: Error

        Returns:
          InstrumentState: The state of the instrument.
            0: IDLE
            1: STANDBY
            2: RUNNING
            3: ERROR
            4: DIAGNOSTICS
        """

        return await self.protocol.get_instrument_state()

    @sila.ObservableCommand(errors=[NotInitialized, InstrumentErrorOccurred, InvalidInstrumentStatusError])
    async def reset(self) -> None:
        """
        Reset the server to its Idle state. This command is common to all instruments.

        Calling this command invokes the instrument command stopRun.

        Status required to execute this command: Error
        Status while this command is running: Same as the status at the start of execution
        Status after this command finishes
          If it completes normally: Idle
          If an error occurs: Error
        """

        await self.protocol.reset()

    @sila.ObservableProperty()
    async def subscribe_elapsed_time(self) -> sila.Stream[str]:
        """
        The elapsed time since the protocol started running, represented as a string in hh:mm:ss format.

        If the protocol is not running, the value is set to 00:00:00.
        """  # noqa: D401

        async for elapsed_time in watch(self.protocol.elapsed_time):
            yield format_duration(elapsed_time)

    @sila.ObservableProperty()
    async def subscribe_remaining_time(self) -> sila.Stream[str]:
        """
        The remaining time until the protocol completes, represented as a string in hh:mm:ss format.

        If the protocol is not running, the value is set to 00:00:00.

        Note: Until the protocol finishes, the value will not be set to 00:00:00.
        Instead, the value will stop at 00:00:01.
        """  # noqa: D401

        async for remaining_time in watch(self.protocol.remaining_time):
            yield format_duration(remaining_time)

    @sila.ObservableProperty()
    async def subscribe_status(
        self,
    ) -> sila.Stream[typing.Annotated[int, sila.constraints.MinimalInclusive(0), sila.constraints.MaximalInclusive(3)]]:
        """
        Returns the status of the instrument. This property is common to all instruments.

        0: Not Connected
        1: Idle
        2: Running
        3: Error
        """  # noqa: D401

        async for status in watch(self.protocol.status):
            yield int(status)
