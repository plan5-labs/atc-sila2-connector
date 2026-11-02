import collections.abc
from importlib.metadata import version

from unitelabs.cdk import Connector

from .config import AutomatedThermalCyclerConfig
from .features.automated_thermal_cycler_controller import AutomatedThermalCyclerController
from .features.simulation_controller import SimulationController
from .io import AutomatedThermalCyclerProtocol, SimulatedCommandExecutor

__version__ = version("unitelabs-applied-biosystems-atc")


async def create_app(config: AutomatedThermalCyclerConfig) -> collections.abc.AsyncGenerator[Connector, None]:
    """Create the connector application."""

    app = Connector(config)

    protocol = AutomatedThermalCyclerProtocol(host=config.command_executor.host, port=config.command_executor.port)
    simulator = SimulatedCommandExecutor()
    simulation_controller = SimulationController(protocol, simulator)

    try:
        if config.simulation_mode:
            await simulation_controller.start_simulation_mode()
        else:
            await protocol.open()

        app.register(AutomatedThermalCyclerController(protocol))
        app.register(simulation_controller)

        yield app
    finally:
        await protocol.close()
        await simulator.stop()
