import dataclasses
from importlib.metadata import version

import typing_extensions as typing

from unitelabs.cdk.config import Config, ConnectorBaseConfig, Field, SiLAServerConfig

__version__ = version("unitelabs-applied-biosystems-atc")


@dataclasses.dataclass
class CommandExecutorConfig(Config):
    """
    Connection to the ATC command executor.

    The command executor (AutomatedThermalCyclerCommandExecutor.exe from https://github.com/plan5-labs/atc-sila2)
    runs on the Windows PC connected to the ATC and drives the instrument through the vendor API.
    """

    host: str = "localhost"
    """
    The host name or IP address of the PC running the command executor. The command executor only
    accepts connections from the same PC, so keep `localhost` unless you changed that.
    """

    port: typing.Annotated[int, Field(ge=1, le=65_535)] = 5141
    """The port the command executor listens on, `CommandExecutor.Port` in its `application.json`."""


@dataclasses.dataclass
class AutomatedThermalCyclerConfig(ConnectorBaseConfig):
    """Configuration for the Applied Biosystems Automated Thermal Cycler connector."""

    sila_server: SiLAServerConfig = dataclasses.field(
        default_factory=lambda: SiLAServerConfig(
            name="Applied Biosystems Automated Thermal Cycler",
            type="Thermocycler",
            description=(
                "A SiLA 2 connector for the Applied Biosystems Automated Thermal Cycler (ATC) "
                "made by Thermo Fisher Scientific, built with the UniteLabs CDK."
            ),
            version=str(__version__),
            vendor_url="https://github.com/plan5-labs/atc-sila2-connector",
            # The port of the original C# SiLA server, so existing clients find the connector.
            port=5140,
        )
    )

    simulation_mode: bool = True
    """
    Whether to start with a simulated ATC instead of the real one. Set it to `false` to control the
    instrument through the command executor.
    """

    command_executor: CommandExecutorConfig = dataclasses.field(default_factory=CommandExecutorConfig)
    """Connection to the ATC command executor, used outside simulation mode."""
