import typing_extensions as typing

from unitelabs.cdk.features.core.simulation_controller import (
    SimulationControllerBase,
    StartRealModeFailed,
    StartSimulationModeFailed,
)

from ...io import AutomatedThermalCyclerProtocol, CommandExecutorUnavailable, SimulatedCommandExecutor, Status


class SimulationController(SimulationControllerBase):
    """
    This Feature provides control over the simulation behaviour of a SiLA Server.

    A SiLA Server can run in two modes:
    (a) Real Mode - with real activities, e.g. addressing or controlling real hardware,
        e.g. through serial/CANBus commands, writing to real databases, moving real objects etc.
    (b) Simulation Mode - where every command is only simulated and responses are just example returns.

    Note that certain commands and properties might not be affected by this feature if they
    do not interact with the real world.
    """

    def __init__(self, protocol: AutomatedThermalCyclerProtocol, simulator: SimulatedCommandExecutor):
        super().__init__()
        self.protocol = protocol
        self.simulator = simulator

    @typing.override
    async def start_simulation_mode(self) -> None:
        """
        Set the SiLA Server to run in Simulation Mode, i.e. all following commands are executed in simulation mode.

        The Simulation Mode can only be entered, if all hardware operations have been safely terminated
        or are in a controlled, safe state.

        The simulation mode can be stopped by issuing the 'Start Real Mode' command.

        Raises:
          StartSimulationModeFailed: If the server cannot change to Simulation Mode.
        """

        if self._simulation_mode:
            return

        if self.protocol.status.current is Status.RUNNING:
            msg = (
                "The ATC is running a protocol. Wait for the run to finish, or stop it with the "
                "'AutomatedThermalCyclerController.StopRun' command, before entering simulation mode."
            )
            raise StartSimulationModeFailed(msg)

        await self.protocol.open(await self.simulator.start())
        self._simulation_mode = True

    @typing.override
    async def start_real_mode(self) -> None:
        """
        Set the SiLA Server to run in real mode.

        In real-mode all following commands are executed with real-world
        interactions, like serial port/CAN communication, motor actions etc.

        If the server is in Simulation Mode it can be interrupted at any time. A re-initialization of
        the hardware might be required. The Real Mode can be stopped by issuing the 'Start Simulation Mode' command.

        Raises:
          StartRealModeFailed: If the server cannot change to Real Mode.
        """

        if not self._simulation_mode:
            return

        try:
            await self.protocol.open()
        except CommandExecutorUnavailable as error:
            await self.protocol.open(self.simulator.address)
            raise StartRealModeFailed(str(error)) from error

        await self.simulator.stop()
        self._simulation_mode = False

    @typing.override
    async def simulation_mode(self) -> bool:
        """Whether or not the SiLA Server is in Simulation Mode."""

        return self._simulation_mode
