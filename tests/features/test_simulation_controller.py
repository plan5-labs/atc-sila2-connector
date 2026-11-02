import pytest

from tests.conftest import PROTOCOL_FILE, free_port, wait_for_status
from tests.features.conftest import run
from unitelabs.applied_biosystems_atc.features.simulation_controller import SimulationController
from unitelabs.applied_biosystems_atc.io import AutomatedThermalCyclerProtocol, SimulatedCommandExecutor, Status
from unitelabs.cdk.features.core.simulation_controller import StartRealModeFailed, StartSimulationModeFailed


@pytest.fixture
async def command_executor():
    """A simulated command executor standing in for the real one."""

    command_executor = SimulatedCommandExecutor(run_duration=1000, time_scale=0.01)
    await command_executor.start()
    yield command_executor
    await command_executor.stop()


@pytest.fixture
async def controller(command_executor):
    host, _, port = command_executor.address.rpartition(":")
    protocol = AutomatedThermalCyclerProtocol(host=host, port=int(port))
    simulator = SimulatedCommandExecutor(time_scale=0.01)
    controller = SimulationController(protocol, simulator)
    await controller.start_simulation_mode()
    yield controller
    await protocol.close()
    await simulator.stop()


async def test_simulation_mode_drives_simulator(controller, command_executor):
    await controller.protocol.load(PROTOCOL_FILE)

    assert await controller.simulation_mode()
    assert controller.simulator.protocol_file == PROTOCOL_FILE
    assert command_executor.protocol_file is None


async def test_real_mode_drives_command_executor(controller, command_executor):
    await controller.start_real_mode()
    await controller.protocol.load(PROTOCOL_FILE)

    assert not await controller.simulation_mode()
    assert command_executor.protocol_file == PROTOCOL_FILE
    assert controller.simulator.address == ""


async def test_stays_in_simulation_mode_without_command_executor(controller):
    controller.protocol.port = free_port()

    with pytest.raises(StartRealModeFailed, match=r"AutomatedThermalCyclerCommandExecutor\.exe"):
        await controller.start_real_mode()

    assert await controller.simulation_mode()
    await wait_for_status(controller.protocol, Status.IDLE)
    await controller.protocol.load(PROTOCOL_FILE)


async def test_refuses_simulation_mode_during_real_run(controller):
    await controller.start_real_mode()
    await controller.protocol.load(PROTOCOL_FILE)
    await controller.protocol.validate(0)
    await controller.protocol.start_run()
    await wait_for_status(controller.protocol, Status.RUNNING)

    with pytest.raises(StartSimulationModeFailed, match="StopRun"):
        await controller.start_simulation_mode()

    assert not await controller.simulation_mode()


async def test_connector_starts_in_simulation_mode(client):
    assert await client.SimulationController.SimulationMode.read() is True


async def test_connector_reports_failed_switch_to_real_mode(client):
    with pytest.raises(client.SimulationController.StartRealModeFailed):
        await client.SimulationController.StartRealMode()

    await run(client.AutomatedThermalCyclerController.Load, ProtocolFileData=PROTOCOL_FILE)
