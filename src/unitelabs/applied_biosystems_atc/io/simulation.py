import asyncio
import collections.abc
import xml.etree.ElementTree as ElementTree

import grpc
import grpc.aio
import typing_extensions as typing

from unitelabs.cdk import Subject

from .command_executor import (
    AutomatedThermalCyclerCommandExecutorServiceServicer,
    CloseLidRequest,
    CloseLidResponse,
    GetInstrumentStateRequest,
    GetInstrumentStateResponse,
    InstrumentState,
    LoadRequest,
    LoadResponse,
    OpenLidRequest,
    OpenLidResponse,
    ResetRequest,
    ResetResponse,
    StartRunRequest,
    StartRunResponse,
    Status,
    StopRunRequest,
    StopRunResponse,
    SubscribeElapsedTimeRequest,
    SubscribeElapsedTimeResponse,
    SubscribeRemainingTimeRequest,
    SubscribeRemainingTimeResponse,
    SubscribeStatusRequest,
    SubscribeStatusResponse,
    ValidateRequest,
    ValidateResponse,
    add_AutomatedThermalCyclerCommandExecutorServiceServicer_to_server,
)
from .subjects import watch

SIMULATED_RUN_DURATION = 120
"""Seconds a simulated protocol run takes."""

SIMULATED_LID_DURATION = 3.0
"""Seconds the simulated lid takes to open or close."""

STATUS_BY_INSTRUMENT_STATE = {
    InstrumentState.IDLE: Status.IDLE,
    InstrumentState.RUNNING: Status.RUNNING,
    InstrumentState.ERROR: Status.ERROR,
    InstrumentState.DIAGNOSTICS: Status.RUNNING,
}
"""How the command executor derives its status from the instrument state before a command."""


class SimulatedCommandExecutor(AutomatedThermalCyclerCommandExecutorServiceServicer):
    """
    An in-process stand-in for the AutomatedThermalCyclerCommandExecutor, driving a simulated ATC.

    Reproduces the status handling and the error responses of the command executor, so the connector
    behaves in simulation mode as it does with the instrument: a command first derives the status
    from the instrument state, then checks that the status allows the command.

    The simulated ATC is always connected and accepts any well-formed XML document as a protocol
    file, without checking its contents. A run takes `run_duration` seconds. Starting a run with
    the lid open fails like an instrument error, as the lid has to be closed before a run.

    Args:
      run_duration: Simulated seconds a protocol run takes.
      lid_duration: Simulated seconds the lid takes to open or close.
      time_scale: Real seconds per simulated second, e.g. `0.01` to simulate 100 times faster.
    """

    def __init__(
        self,
        run_duration: int = SIMULATED_RUN_DURATION,
        lid_duration: float = SIMULATED_LID_DURATION,
        time_scale: float = 1.0,
    ) -> None:
        self.run_duration = run_duration
        self.lid_duration = lid_duration
        self.time_scale = time_scale

        self.instrument_state = InstrumentState.IDLE
        self.lid_open = False
        self.protocol_file: bytes | None = None
        self.protocol_validated = False

        self._status = Subject[Status](maxsize=10, initial_value=Status.IDLE)
        self._elapsed_time = Subject[int](maxsize=10, initial_value=0)
        self._remaining_time = Subject[int](maxsize=10, initial_value=0)
        self._run: asyncio.Task | None = None
        self._server: grpc.aio.Server | None = None
        self._address = ""

    @property
    def address(self) -> str:
        """The `host:port` the simulated command executor listens on, empty while it is stopped."""

        return self._address

    async def start(self, port: int = 0) -> str:
        """
        Serve the simulated command executor on localhost, unless it is already serving.

        Args:
          port: The port to listen on, or 0 for a free one.

        Returns:
          The `host:port` the simulated command executor listens on.
        """

        if self._server is None:
            server = grpc.aio.server()
            add_AutomatedThermalCyclerCommandExecutorServiceServicer_to_server(self, server)
            port = server.add_insecure_port(f"127.0.0.1:{port}")
            await server.start()
            self._server, self._address = server, f"127.0.0.1:{port}"

        return self._address

    async def stop(self) -> None:
        """Stop serving and abort a simulated run."""

        if self._run is not None:
            self._run.cancel()

        if self._server is not None:
            await self._server.stop(grace=None)
            self._server, self._address = None, ""

    @typing.override
    async def Load(self, request: LoadRequest, context: grpc.aio.ServicerContext) -> LoadResponse:
        await self._check_status(context, Status.IDLE)

        try:
            ElementTree.fromstring(request.protocolFileData)
        except ElementTree.ParseError as error:
            code = "PROTOCOL_EMPTY" if not request.protocolFileData else "PROTOCOL_READ_FAILED"
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"InvalidProtocol: The loaded protocol file is invalid.\nErrorCode:{code}, ErrorMessage:{error}",
            )

        self.protocol_file = request.protocolFileData
        self.protocol_validated = False
        return LoadResponse()

    @typing.override
    async def Validate(self, request: ValidateRequest, context: grpc.aio.ServicerContext) -> ValidateResponse:
        await self._check_status(context, Status.IDLE)

        if self.protocol_file is None:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "ProtocolNotLoaded: Execute Load command first.")

        if request.maxSampleVolume < 0:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "InvalidProtocol: The loaded protocol file is invalid.\n"
                f"ErrorCode:PROTOCOL_SAMPLE_VOLUME_OUT_OF_RANGE, ErrorMessage:{request.maxSampleVolume}",
            )

        self.protocol_validated = True
        return ValidateResponse()

    @typing.override
    async def OpenLid(self, request: OpenLidRequest, context: grpc.aio.ServicerContext) -> OpenLidResponse:
        await self._check_status(context, Status.IDLE)
        await asyncio.sleep(self.lid_duration * self.time_scale)
        self.lid_open = True
        return OpenLidResponse()

    @typing.override
    async def CloseLid(self, request: CloseLidRequest, context: grpc.aio.ServicerContext) -> CloseLidResponse:
        await self._check_status(context, Status.IDLE)
        await asyncio.sleep(self.lid_duration * self.time_scale)
        self.lid_open = False
        return CloseLidResponse()

    @typing.override
    async def StartRun(self, request: StartRunRequest, context: grpc.aio.ServicerContext) -> StartRunResponse:
        if self.protocol_file is None:
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "ProtocolNotLoaded: Execute Load command first, and then call Validate command.",
            )

        if not self.protocol_validated:
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, "ProtocolNotValidated: Execute Validate command first."
            )

        await self._check_status(context, Status.IDLE)

        if self.lid_open:
            self._status.update(Status.ERROR)
            await context.abort(grpc.StatusCode.INTERNAL, "Failed to start running.")

        self.instrument_state = InstrumentState.RUNNING
        self._status.update(Status.RUNNING)
        self._run = asyncio.create_task(self._run_protocol())
        return StartRunResponse()

    @typing.override
    async def StopRun(self, request: StopRunRequest, context: grpc.aio.ServicerContext) -> StopRunResponse:
        await self._check_status(context, Status.RUNNING)

        # Like the instrument, end the run asynchronously, after the response.
        if self._run is not None:
            self._run.cancel()

        return StopRunResponse()

    @typing.override
    async def GetInstrumentState(
        self, request: GetInstrumentStateRequest, context: grpc.aio.ServicerContext
    ) -> GetInstrumentStateResponse:
        return GetInstrumentStateResponse(instrumentState=self.instrument_state)

    @typing.override
    async def Reset(self, request: ResetRequest, context: grpc.aio.ServicerContext) -> ResetResponse:
        await self._check_status(context, Status.ERROR)

        if self.instrument_state is InstrumentState.RUNNING and self._run is not None:
            self._run.cancel()
        elif self.instrument_state is InstrumentState.ERROR:
            await context.abort(grpc.StatusCode.INTERNAL, "The instrument error has not been resolved.")

        self._status.update(Status.IDLE)
        return ResetResponse()

    @typing.override
    async def SubscribeElapsedTime(
        self, request: SubscribeElapsedTimeRequest, context: grpc.aio.ServicerContext
    ) -> collections.abc.AsyncIterator[SubscribeElapsedTimeResponse]:
        async for elapsed_time in watch(self._elapsed_time):
            yield SubscribeElapsedTimeResponse(elapsedTime=elapsed_time)

    @typing.override
    async def SubscribeRemainingTime(
        self, request: SubscribeRemainingTimeRequest, context: grpc.aio.ServicerContext
    ) -> collections.abc.AsyncIterator[SubscribeRemainingTimeResponse]:
        async for remaining_time in watch(self._remaining_time):
            yield SubscribeRemainingTimeResponse(remainingTime=remaining_time)

    @typing.override
    async def SubscribeStatus(
        self, request: SubscribeStatusRequest, context: grpc.aio.ServicerContext
    ) -> collections.abc.AsyncIterator[SubscribeStatusResponse]:
        async for status in watch(self._status):
            yield SubscribeStatusResponse(status=status)

    async def _check_status(self, context: grpc.aio.ServicerContext, *valid: Status) -> None:
        """Derive the status from the instrument state, then abort unless the status is one of `valid`."""

        self._status.update(STATUS_BY_INSTRUMENT_STATE[self.instrument_state])

        status = typing.cast(Status, self._status.current)
        if status not in valid:
            expected = ", ".join(valid_status.name for valid_status in valid)
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, f"InvalidStatus. Expected: {expected} / Actual: {status.name}"
            )

    async def _run_protocol(self) -> None:
        """Count the run time once per simulated second until the run completes or is stopped."""

        try:
            for elapsed_time in range(self.run_duration):
                self._elapsed_time.update(elapsed_time)
                # Like the command executor, hold the remaining time at 1 s until the run has ended.
                self._remaining_time.update(max(self.run_duration - elapsed_time, 1))
                await asyncio.sleep(self.time_scale)
        finally:
            self.instrument_state = InstrumentState.IDLE
            self._elapsed_time.update(0)
            self._remaining_time.update(0)
            if self._status.current is not Status.ERROR:
                self._status.update(Status.IDLE)
            self._run = None
