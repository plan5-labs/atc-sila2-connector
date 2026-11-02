import asyncio
import datetime

import grpc
import grpc.aio
import pytest

from tests.conftest import PROTOCOL_FILE, TIMEOUT, free_port, wait_for_status
from unitelabs.applied_biosystems_atc.io import (
    AutomatedThermalCyclerProtocol,
    CommandExecutorUnavailable,
    InstrumentErrorOccurred,
    InstrumentState,
    InvalidInstrumentStatusError,
    InvalidProtocol,
    NotInitialized,
    ProtocolNotLoaded,
    ProtocolNotValidated,
    SimulatedCommandExecutor,
    Status,
)
from unitelabs.applied_biosystems_atc.io.command_executor import (
    AutomatedThermalCyclerCommandExecutorServiceServicer,
    add_AutomatedThermalCyclerCommandExecutorServiceServicer_to_server,
)
from unitelabs.cdk import Replay


async def prepare_run(protocol: AutomatedThermalCyclerProtocol) -> None:
    await protocol.load(PROTOCOL_FILE)
    await protocol.validate(0)
    await protocol.close_lid()


class TestConnection:
    async def test_mirrors_status_of_command_executor(self, protocol):
        assert protocol.status.current is Status.IDLE

    async def test_reports_not_connected_after_close(self, protocol):
        await protocol.close()

        assert protocol.status.current is Status.NOT_CONNECTED

    async def test_raises_if_no_command_executor_answers(self):
        protocol = AutomatedThermalCyclerProtocol(host="127.0.0.1", port=free_port())

        with pytest.raises(CommandExecutorUnavailable, match=r"AutomatedThermalCyclerCommandExecutor\.exe"):
            await protocol.open()

        assert protocol.status.current is Status.NOT_CONNECTED

    async def test_commands_raise_not_initialized_before_open(self):
        protocol = AutomatedThermalCyclerProtocol()

        with pytest.raises(NotInitialized):
            await protocol.open_lid()

    async def test_reports_not_connected_when_command_executor_stops(self, protocol, simulator):
        await simulator.stop()

        await wait_for_status(protocol, Status.NOT_CONNECTED)
        with pytest.raises(NotInitialized, match="unreachable"):
            await protocol.open_lid()

    async def test_follows_command_executor_after_restart(self):
        port = free_port()
        simulator = SimulatedCommandExecutor(time_scale=0.01)
        await simulator.start(port)
        protocol = AutomatedThermalCyclerProtocol(host="127.0.0.1", port=port)
        await protocol.open()
        try:
            await wait_for_status(protocol, Status.IDLE)

            await simulator.stop()
            await wait_for_status(protocol, Status.NOT_CONNECTED)

            await simulator.start(port)
            await wait_for_status(protocol, Status.IDLE)
            await protocol.load(PROTOCOL_FILE)
        finally:
            await protocol.close()
            await simulator.stop()


class TestLoad:
    async def test_loads_protocol_file(self, protocol, simulator):
        await protocol.load(PROTOCOL_FILE)

        assert simulator.protocol_file == PROTOCOL_FILE

    async def test_rejects_malformed_protocol_file(self, protocol):
        with pytest.raises(InvalidProtocol, match="PROTOCOL_READ_FAILED"):
            await protocol.load(b"<Protocol>")

    async def test_rejects_empty_protocol_file(self, protocol):
        with pytest.raises(InvalidProtocol, match="PROTOCOL_EMPTY"):
            await protocol.load(b"")


class TestValidate:
    async def test_validates_loaded_protocol(self, protocol, simulator):
        await protocol.load(PROTOCOL_FILE)

        await protocol.validate(50.0)

        assert simulator.protocol_validated

    async def test_requires_loaded_protocol(self, protocol):
        with pytest.raises(ProtocolNotLoaded):
            await protocol.validate(0)

    async def test_rejects_negative_sample_volume(self, protocol):
        await protocol.load(PROTOCOL_FILE)

        with pytest.raises(InvalidProtocol, match="PROTOCOL_SAMPLE_VOLUME_OUT_OF_RANGE"):
            await protocol.validate(-1)

    async def test_loading_again_requires_validating_again(self, protocol):
        await protocol.load(PROTOCOL_FILE)
        await protocol.validate(0)
        await protocol.load(PROTOCOL_FILE)

        with pytest.raises(ProtocolNotValidated):
            await protocol.start_run()


class TestLid:
    async def test_opens_and_closes_lid(self, protocol, simulator):
        await protocol.open_lid()
        assert simulator.lid_open

        await protocol.close_lid()
        assert not simulator.lid_open

    async def test_runs_lid_commands_one_at_a_time(self, protocol, simulator):
        simulator.lid_duration = 20
        lid_motion = simulator.lid_duration * simulator.time_scale

        started = asyncio.get_running_loop().time()
        await asyncio.gather(protocol.open_lid(), protocol.close_lid())

        # Two lid motions one after the other take about twice as long as one. Allow for the coarse
        # clock on Windows.
        assert asyncio.get_running_loop().time() - started >= 1.5 * lid_motion


class TestStartRun:
    async def test_requires_loaded_protocol(self, protocol):
        with pytest.raises(ProtocolNotLoaded):
            await protocol.start_run()

    async def test_requires_validated_protocol(self, protocol):
        await protocol.load(PROTOCOL_FILE)

        with pytest.raises(ProtocolNotValidated):
            await protocol.start_run()

    async def test_runs_protocol_to_completion(self, protocol):
        await prepare_run(protocol)
        statuses = protocol.status.subscribe()
        remaining_times = protocol.remaining_time.subscribe()

        await protocol.start_run()

        assert await statuses.get(timeout=TIMEOUT) is Status.RUNNING
        assert await statuses.get(timeout=TIMEOUT) is Status.IDLE
        await protocol.remaining_time.wait_for(lambda value: not value, timeout=TIMEOUT, replay=Replay.CURRENT)
        assert protocol.elapsed_time.current == datetime.timedelta(0)

        values = []
        while remaining_times.size:
            values.append(await remaining_times.get())
        assert values[0] == datetime.timedelta(seconds=5)
        assert values[-2:] == [datetime.timedelta(seconds=1), datetime.timedelta(0)]

    async def test_reports_running_instrument_state(self, protocol, simulator):
        simulator.run_duration = 1000
        await prepare_run(protocol)

        await protocol.start_run()

        assert await protocol.get_instrument_state() is InstrumentState.RUNNING

    async def test_fails_with_lid_open(self, protocol):
        await protocol.load(PROTOCOL_FILE)
        await protocol.validate(0)
        await protocol.open_lid()

        with pytest.raises(InstrumentErrorOccurred):
            await protocol.start_run()

        await wait_for_status(protocol, Status.ERROR)

    async def test_next_command_derives_status_from_instrument_state(self, protocol):
        await protocol.load(PROTOCOL_FILE)
        await protocol.validate(0)
        await protocol.open_lid()
        with pytest.raises(InstrumentErrorOccurred):
            await protocol.start_run()

        await protocol.close_lid()

        await wait_for_status(protocol, Status.IDLE)

    async def test_rejects_second_run(self, protocol, simulator):
        simulator.run_duration = 1000
        await prepare_run(protocol)
        await protocol.start_run()

        with pytest.raises(InvalidInstrumentStatusError, match="Actual: RUNNING"):
            await protocol.start_run()


class TestStopRun:
    async def test_requires_running_protocol(self, protocol):
        with pytest.raises(InvalidInstrumentStatusError, match="Expected: RUNNING"):
            await protocol.stop_run()

    async def test_stops_running_protocol(self, protocol, simulator):
        simulator.run_duration = 1000
        await prepare_run(protocol)
        await protocol.start_run()
        await wait_for_status(protocol, Status.RUNNING)

        await protocol.stop_run()

        await wait_for_status(protocol, Status.IDLE)
        assert await protocol.get_instrument_state() is InstrumentState.IDLE


class TestReset:
    async def test_requires_error_status(self, protocol):
        with pytest.raises(InvalidInstrumentStatusError, match="Expected: ERROR"):
            await protocol.reset()


class FailingCommandExecutor(AutomatedThermalCyclerCommandExecutorServiceServicer):
    """A command executor that fails every `OpenLid` call with the given status code and details."""

    def __init__(self, code: grpc.StatusCode, details: str):
        self.code = code
        self.details = details

    async def OpenLid(self, request, context):
        await context.abort(self.code, self.details)


@pytest.mark.parametrize(
    ("code", "details", "error"),
    [
        (
            grpc.StatusCode.FAILED_PRECONDITION,
            "InvalidStatus. Expected: Idle / Actual: Running",
            InvalidInstrumentStatusError,
        ),
        (grpc.StatusCode.FAILED_PRECONDITION, "ProtocolNotLoaded: Execute Load command first.", ProtocolNotLoaded),
        (
            grpc.StatusCode.FAILED_PRECONDITION,
            "ProtocolNotValidated: Execute Validate command first.",
            ProtocolNotValidated,
        ),
        (grpc.StatusCode.FAILED_PRECONDITION, "Automated Thermal Cycler is not initialized.", NotInitialized),
        (grpc.StatusCode.INVALID_ARGUMENT, "InvalidProtocol: The loaded protocol file is invalid.", InvalidProtocol),
        (grpc.StatusCode.INTERNAL, "Failed to open lid.", InstrumentErrorOccurred),
        (grpc.StatusCode.UNKNOWN, "Exception was thrown by handler.", InstrumentErrorOccurred),
    ],
)
async def test_translates_command_executor_errors(code, details, error):
    server = grpc.aio.server()
    add_AutomatedThermalCyclerCommandExecutorServiceServicer_to_server(FailingCommandExecutor(code, details), server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    protocol = AutomatedThermalCyclerProtocol(host="127.0.0.1", port=port)
    try:
        await protocol.open()

        with pytest.raises(error) as raised:
            await protocol.open_lid()

        assert type(raised.value) is error
        assert str(raised.value) == details
    finally:
        await protocol.close()
        await server.stop(grace=None)
