import socket

import pytest

from unitelabs.applied_biosystems_atc.io import AutomatedThermalCyclerProtocol, SimulatedCommandExecutor, Status
from unitelabs.applied_biosystems_atc.io import protocol as protocol_module
from unitelabs.cdk import Replay

PROTOCOL_FILE = b'<?xml version="1.0" encoding="UTF-8"?><Protocol><Stage/></Protocol>'
"""A protocol file the simulated ATC accepts."""

TIMEOUT = 5.0
"""Seconds a test waits for an expected update."""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def wait_for_status(protocol: AutomatedThermalCyclerProtocol, status: Status) -> None:
    await protocol.status.wait_for(lambda current: current is status, timeout=TIMEOUT, replay=Replay.CURRENT)


@pytest.fixture(autouse=True)
def fast_timeouts(monkeypatch):
    """Shorten the waits of the protocol, so tests about unreachable command executors stay fast."""

    monkeypatch.setattr(protocol_module, "OPEN_TIMEOUT", 0.5)
    monkeypatch.setattr(protocol_module, "RESUBSCRIBE_DELAY", 0.05)


@pytest.fixture
async def simulator():
    """A simulated command executor running 100 times faster than real time."""

    simulator = SimulatedCommandExecutor(run_duration=5, lid_duration=1, time_scale=0.01)
    await simulator.start()
    yield simulator
    await simulator.stop()


@pytest.fixture
async def protocol(simulator):
    """A protocol connected to the simulated command executor."""

    protocol = AutomatedThermalCyclerProtocol()
    await protocol.open(simulator.address)
    await wait_for_status(protocol, Status.IDLE)
    yield protocol
    await protocol.close()
