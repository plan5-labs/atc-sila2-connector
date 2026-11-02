import asyncio
import collections.abc
import datetime
import logging

import grpc
import grpc.aio
import typing_extensions as typing

from unitelabs.cdk import Subject

from .command_executor import (
    AutomatedThermalCyclerCommandExecutorServiceStub,
    CloseLidRequest,
    GetInstrumentStateRequest,
    GetInstrumentStateResponse,
    InstrumentState,
    LoadRequest,
    OpenLidRequest,
    ResetRequest,
    StartRunRequest,
    Status,
    StopRunRequest,
    SubscribeElapsedTimeRequest,
    SubscribeElapsedTimeResponse,
    SubscribeRemainingTimeRequest,
    SubscribeRemainingTimeResponse,
    SubscribeStatusRequest,
    ValidateRequest,
)
from .errors import (
    CommandExecutorUnavailable,
    InstrumentErrorOccurred,
    InvalidInstrumentStatusError,
    InvalidProtocol,
    NotInitialized,
    ProtocolNotLoaded,
    ProtocolNotValidated,
)

OPEN_TIMEOUT = 10.0
"""Seconds to wait for the command executor to accept a connection."""

COMMAND_TIMEOUT = 300.0
"""Seconds to wait for the command executor to finish a command."""

RESUBSCRIBE_DELAY = 5.0
"""Seconds to wait before subscribing again to a stream of the command executor that ended."""

HISTORY_SIZE = 10
"""Number of updates a slow subscriber can fall behind before its oldest updates are dropped."""

ZERO = datetime.timedelta(0)

Message = typing.TypeVar("Message")

logger = logging.getLogger(__name__)


class AutomatedThermalCyclerProtocol:
    """
    Client of the AutomatedThermalCyclerCommandExecutor, which drives the ATC through the vendor API.

    The command executor owns the connection to the instrument, checks the preconditions of every
    command and tracks the status of the instrument. This protocol forwards commands to it one at a
    time, translates its errors and mirrors its status, elapsed time and remaining time.

    Args:
      host: The host name of the PC running the command executor.
      port: The port the command executor listens on.
    """

    def __init__(self, host: str = "localhost", port: int = 5141) -> None:
        self.host = host
        self.port = port

        self.status = Subject[Status](maxsize=HISTORY_SIZE, initial_value=Status.NOT_CONNECTED)
        """The status of the ATC, `NOT_CONNECTED` while the command executor is unreachable."""

        self.elapsed_time = Subject[datetime.timedelta](maxsize=HISTORY_SIZE, initial_value=ZERO)
        """The time since the running protocol started, zero while no protocol runs."""

        self.remaining_time = Subject[datetime.timedelta](maxsize=HISTORY_SIZE, initial_value=ZERO)
        """The time until the running protocol completes, zero while no protocol runs."""

        self._address = ""
        self._channel: grpc.aio.Channel | None = None
        self._stub: AutomatedThermalCyclerCommandExecutorServiceStub | None = None
        self._command_lock = asyncio.Lock()
        self._status_task: asyncio.Task | None = None
        self._run_time_tasks: set[asyncio.Task] = set()

    @property
    def address(self) -> str:
        """The configured `host:port` of the command executor."""

        return f"{self.host}:{self.port}"

    async def open(self, address: str | None = None) -> None:
        """
        Connect to the command executor and start mirroring its status.

        Closes the current connection first, if any.

        Args:
          address: The `host:port` of a command executor to connect to instead of the configured one.

        Raises:
          CommandExecutorUnavailable: If the command executor does not accept the connection in time.
        """

        await self.close()

        address = address or self.address
        channel = grpc.aio.insecure_channel(address)
        try:
            await asyncio.wait_for(channel.channel_ready(), timeout=OPEN_TIMEOUT)
        except asyncio.TimeoutError:
            await channel.close()
            msg = (
                f"No ATC command executor answered at '{address}' within {OPEN_TIMEOUT:g} s. Start "
                "AutomatedThermalCyclerCommandExecutor.exe on the PC connected to the ATC, and check the "
                "'command_executor' host and port in the connector configuration."
            )
            raise CommandExecutorUnavailable(msg) from None

        stub = AutomatedThermalCyclerCommandExecutorServiceStub(channel)
        self._address, self._channel, self._stub = address, channel, stub
        self._status_task = asyncio.create_task(
            self._follow(
                lambda: stub.SubscribeStatus(SubscribeStatusRequest()),
                lambda response: self._update_status(stub, Status(response.status)),
                on_end=lambda: self._update_status(stub, Status.NOT_CONNECTED),
            )
        )
        logger.info("Connected to the ATC command executor at '%s'.", address)

    async def close(self) -> None:
        """Disconnect from the command executor."""

        tasks = [task for task in (self._status_task, *self._run_time_tasks) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._status_task = None
        self._run_time_tasks.clear()

        if self._channel is not None:
            await self._channel.close()
            logger.info("Disconnected from the ATC command executor at '%s'.", self._address)
        self._channel, self._stub = None, None

        self.status.update(Status.NOT_CONNECTED)
        self.elapsed_time.update(ZERO)
        self.remaining_time.update(ZERO)

    async def load(self, protocol_file: bytes) -> None:
        """
        Load a protocol file, the instrument command `load`.

        Args:
          protocol_file: The protocol file, an UTF-8 encoded XML document.
        """

        await self._execute("Load", LoadRequest(protocolFileData=protocol_file))

    async def validate(self, max_sample_volume: float) -> None:
        """
        Validate the loaded protocol file, the instrument command `validate`.

        Args:
          max_sample_volume: The upper limit of the sample volume, or 0 for the instrument default.
        """

        await self._execute("Validate", ValidateRequest(maxSampleVolume=max_sample_volume))

    async def open_lid(self) -> None:
        """Open the lid, the instrument command `openLid`."""

        await self._execute("OpenLid", OpenLidRequest())

    async def close_lid(self) -> None:
        """Close the lid, the instrument command `closeLid`."""

        await self._execute("CloseLid", CloseLidRequest())

    async def start_run(self) -> None:
        """Start running the loaded and validated protocol, the instrument command `startRun`."""

        await self._execute("StartRun", StartRunRequest())

    async def stop_run(self) -> None:
        """Stop the running protocol, the instrument command `stopRun`."""

        await self._execute("StopRun", StopRunRequest())

    async def reset(self) -> None:
        """Return from the `ERROR` status to `IDLE`, stopping a run that is still going."""

        await self._execute("Reset", ResetRequest())

    async def get_instrument_state(self) -> InstrumentState:
        """
        Get the state of the instrument, the instrument command `getInstrumentState`.

        Unlike the other commands, this one does not wait for a running command to finish.

        Returns:
          The state the vendor API reports.
        """

        response = await self._execute("GetInstrumentState", GetInstrumentStateRequest(), exclusive=False)
        return InstrumentState(typing.cast(GetInstrumentStateResponse, response).instrumentState)

    async def _execute(self, method: str, request: object, *, exclusive: bool = True) -> object:
        """
        Call a unary method of the command executor and translate its errors.

        Args:
          method: The name of the gRPC method.
          request: The request message.
          exclusive: Whether to wait for other exclusive calls to finish first. The command executor
            keeps the loaded protocol and the instrument status in shared state, so commands that
            change them must not overlap.

        Returns:
          The response message.
        """

        if self._stub is None:
            msg = "The connector is not connected to the ATC command executor."
            raise NotInitialized(msg)

        call = getattr(self._stub, method)
        try:
            if not exclusive:
                return await call(request, timeout=COMMAND_TIMEOUT)

            async with self._command_lock:
                return await call(request, timeout=COMMAND_TIMEOUT)
        except grpc.aio.AioRpcError as error:
            raise self._translate_error(error) from error

    def _translate_error(self, error: grpc.aio.AioRpcError) -> Exception:
        """Translate an error of the command executor the way the original C# SiLA server does."""

        code = error.code()
        details = error.details() or code.name

        if code == grpc.StatusCode.FAILED_PRECONDITION:
            if "InvalidStatus" in details:
                return InvalidInstrumentStatusError(details)
            if "ProtocolNotLoaded" in details:
                return ProtocolNotLoaded(details)
            if "ProtocolNotValidated" in details:
                return ProtocolNotValidated(details)
            return NotInitialized(details)

        if code == grpc.StatusCode.INVALID_ARGUMENT:
            return InvalidProtocol(details)

        if code == grpc.StatusCode.UNAVAILABLE:
            return NotInitialized(
                f"The ATC command executor at '{self._address}' is unreachable ({details}). "
                "Make sure AutomatedThermalCyclerCommandExecutor.exe is running."
            )

        if code == grpc.StatusCode.DEADLINE_EXCEEDED:
            return InstrumentErrorOccurred(
                f"The ATC command executor did not finish the command within {COMMAND_TIMEOUT:g} s. "
                "Inspect the instrument."
            )

        return InstrumentErrorOccurred(details)

    def _update_status(self, stub: AutomatedThermalCyclerCommandExecutorServiceStub, status: Status) -> None:
        """
        Publish a status update and follow the run time while the ATC is connected.

        The command executor attaches run time subscriptions to its current connection with the
        ATC, so they are renewed whenever the ATC (re)connects.
        """

        was_connected = self.status.current is not Status.NOT_CONNECTED
        self.status.update(status)

        if status is Status.NOT_CONNECTED:
            for task in self._run_time_tasks:
                task.cancel()
            self._run_time_tasks.clear()
            self.elapsed_time.update(ZERO)
            self.remaining_time.update(ZERO)
        elif not was_connected:
            self._run_time_tasks = {
                asyncio.create_task(
                    self._follow(
                        lambda: stub.SubscribeElapsedTime(SubscribeElapsedTimeRequest()),
                        self._update_elapsed_time,
                    )
                ),
                asyncio.create_task(
                    self._follow(
                        lambda: stub.SubscribeRemainingTime(SubscribeRemainingTimeRequest()),
                        self._update_remaining_time,
                    )
                ),
            }

    def _update_elapsed_time(self, response: SubscribeElapsedTimeResponse) -> None:
        self.elapsed_time.update(datetime.timedelta(seconds=response.elapsedTime))

    def _update_remaining_time(self, response: SubscribeRemainingTimeResponse) -> None:
        self.remaining_time.update(datetime.timedelta(seconds=response.remainingTime))

    async def _follow(
        self,
        subscribe: collections.abc.Callable[[], collections.abc.AsyncIterable[Message]],
        on_message: collections.abc.Callable[[Message], None],
        on_end: collections.abc.Callable[[], None] | None = None,
    ) -> None:
        """Mirror a stream of the command executor, subscribing again whenever it ends."""

        while True:
            try:
                async for message in subscribe():
                    on_message(message)
            except grpc.aio.AioRpcError as error:
                logger.debug("A stream of the ATC command executor ended: %s", error.details() or error.code().name)

            if on_end is not None:
                on_end()

            await asyncio.sleep(RESUBSCRIBE_DELAY)
