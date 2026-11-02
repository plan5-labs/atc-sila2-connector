import functools

import pytest
from sila.client import Client, ClientConfig
from sila.framework import CommandExecutionStatus

import unitelabs.applied_biosystems_atc
from tests.conftest import TIMEOUT, free_port
from unitelabs.applied_biosystems_atc import AutomatedThermalCyclerConfig, create_app
from unitelabs.applied_biosystems_atc.io import SimulatedCommandExecutor
from unitelabs.cdk.main import init


async def run(command, **parameters):
    """Execute an observable command, wait for it to finish and return its responses."""

    execution = await command(**parameters)
    async for info in await execution.subscribe_status():
        if info.status in (CommandExecutionStatus.FINISHED_SUCCESSFULLY, CommandExecutionStatus.FINISHED_WITH_ERROR):
            break

    return await execution.get_responses(timeout=TIMEOUT * 1000)


@pytest.fixture
async def connector(monkeypatch):
    """The connector in simulation mode, with a simulated ATC running 100 times faster than real time."""

    monkeypatch.setattr(
        unitelabs.applied_biosystems_atc,
        "SimulatedCommandExecutor",
        functools.partial(SimulatedCommandExecutor, run_duration=5, lid_duration=1, time_scale=0.01),
    )

    config = AutomatedThermalCyclerConfig(discovery=None)
    config.sila_server.hostname = "127.0.0.1"
    config.sila_server.port = free_port()
    config.command_executor.host = "127.0.0.1"
    config.command_executor.port = free_port()

    app = await init(functools.partial(create_app, config=config))
    await app.start()
    yield app
    await app.stop()


@pytest.fixture
async def client(connector):
    """A SiLA client connected to the connector."""

    client = Client(ClientConfig(hostname="127.0.0.1", port=connector.config.sila_server.port, tls=False))
    await client.open()
    yield client
    await client.close()
