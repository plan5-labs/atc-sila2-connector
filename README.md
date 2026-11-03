# Applied Biosystems Automated Thermal Cycler

A SiLA 2 connector, built on the [UniteLabs CDK](https://gitlab.com/unitelabs/cdk/python-cdk), for the Applied Biosystems Automated Thermal Cycler (ATC), model A31487 by Thermo Fisher Scientific.

The connector is a Python port of the C# SiLA server in [plan5-labs/atc-sila2](https://github.com/plan5-labs/atc-sila2). It serves the same `AutomatedThermalCyclerController` feature, with the same identifiers, data types and errors, so existing SiLA clients keep working. It drives the instrument through the same command executor.

## How it works

```text
SiLA client ── SiLA 2, port 5140 ──▶ this connector ── gRPC, localhost:5141 ──▶ AutomatedThermalCyclerCommandExecutor.exe ── vendor API ──▶ ATC
```

- The **command executor** is the Windows (.NET Framework 4.8) program from atc-sila2. It wraps the proprietary vendor API (`atc-api`) and owns the connection to the instrument. It checks the preconditions of every command and tracks the status of the instrument.
- The **connector** forwards SiLA commands to the command executor and translates its errors into the defined execution errors of the feature. It also mirrors the executor's status, elapsed time and remaining time to any number of SiLA clients.
- The command executor only accepts connections from the same PC, so run the connector on the Windows PC that is connected to the ATC.

## SiLA features

| Feature | Purpose |
| --- | --- |
| `org.riken/instruments/AutomatedThermalCyclerController/v1` | Controls the ATC, identical to the feature of the C# server. Observable commands: `Load`, `Validate`, `OpenLid`, `CloseLid`, `StartRun`, `StopRun`, `Reset`. Unobservable command: `GetInstrumentState`. Observable properties: `ElapsedTime`, `RemainingTime`, `Status`. |
| `org.silastandard/core/SimulationController/v1` | Switches between the simulated ATC and the real one while the connector runs. |
| `org.silastandard/core/SiLAService/v1`, `ConnectionConfigurationService/v1` | Standard features provided by the CDK. |

A typical run calls `Load` (the protocol file as UTF-8 XML bytes), then `Validate`, `CloseLid` and `StartRun`. Then watch `Status` (`2` while running, back to `1` when idle) and `RemainingTime`.

## Getting started

### Prerequisites

- Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).
- To control the instrument: the ATC, connected to a Windows PC that runs `AutomatedThermalCyclerCommandExecutor.exe`. Build the executor as described in the [atc-sila2 README](https://github.com/plan5-labs/atc-sila2#commandexecutor-windows-only). It needs the vendor DLLs, which neither repository includes.

Without the instrument, the connector runs in simulation mode (the default).

### Install

```sh
git clone https://github.com/plan5-labs/atc-sila2-connector.git
cd atc-sila2-connector
uv sync
```

### Configure

Create a `config.json` in the current directory, and list every setting with its description:

```sh
uv run config create
uv run config show
```

The settings that matter most:

| Setting | Default | Description |
| --- | --- | --- |
| `simulation_mode` | `true` | Set it to `false` to control the instrument through the command executor. |
| `command_executor.host` | `localhost` | The PC running the command executor. |
| `command_executor.port` | `5141` | Must match `CommandExecutor.Port` in the executor's `application.json`. |
| `sila_server.port` | `5140` | The SiLA port. The default is the port of the C# server. |
| `sila_server.tls` | `false` | The C# server used TLS by default. To serve TLS again, run `uv run --with cryptography certificate generate`. |

The server name and type default to `Applied Biosystems Automated Thermal Cycler` and `Thermocycler`. If a client depends on the values of the C# server (both `AutomatedThermalCyclerController`), set `sila_server.name` and `sila_server.type` to match.

### Start

```sh
uv run connector start
```

To control the instrument, start the command executor first, then start the connector with `simulation_mode` set to `false`. If the command executor does not answer within 10 seconds, the connector stops with an error that names the address it tried.

To interact with the connector, use any SiLA 2 client, e.g. the [SiLA Browser](https://gitlab.com/unitelabs/sila2/sila-browser).

## Simulation mode

In simulation mode, the connector runs a simulated command executor in the same process. Commands take the same path as in real mode: the same gRPC calls, the same status handling, the same error translation.

The simulated ATC behaves like this:

- It is always connected.
- It accepts any well-formed XML document as a protocol file, without checking its contents. A malformed or empty file fails with `InvalidProtocol`.
- The lid takes 3 seconds to open or close.
- A run takes 2 minutes.
- Starting a run with the lid open fails with `InstrumentErrorOccurred`.

Use the `SimulationController` feature to switch modes while the connector runs:

- `StartRealMode` fails with `StartRealModeFailed` if no command executor answers. The connector then stays in simulation mode.
- `StartSimulationMode` is refused while the real ATC runs a protocol.

## Differences from the C# SiLA server

The SiLA interface is unchanged. The connector behaves differently in these deliberate ways:

- **Commands run one at a time.** The C# server forwarded concurrent commands to the command executor in parallel. The executor keeps the loaded protocol and the status in shared state, so the connector waits for one command to finish before it forwards the next. `GetInstrumentState` doesn't wait.
- **Clearer error for an unreachable executor.** If the command executor can't be reached, commands fail with `NotInitialized` (the C# server used `InstrumentErrorOccurred`). A command that takes longer than 300 seconds fails with `InstrumentErrorOccurred`.
- **No 24-hour rollover.** `ElapsedTime` and `RemainingTime` keep counting hours past 24. The C# server rolled over to `00:00:00`.
- **One subscription per stream.** The connector holds one subscription per command executor stream, shares it among all SiLA clients, and cancels it when it's no longer needed. The C# server opened one executor stream per SiLA subscription, so two SiLA clients could interfere with each other (see [Command executor behavior](#command-executor-behavior)). It also left the executor stream open after the SiLA client unsubscribed ([atc-sila2#3](https://github.com/plan5-labs/atc-sila2/issues/3)).
- **New feature.** The `SimulationController` feature is added.
- **Different defaults.** TLS is off, and the server name and type differ (see [Configure](#configure)).

## Command executor behavior

The connector relays the following behavior of the command executor unchanged, in real and simulation mode:

- **Status is re-derived before each command.** Before every command except `GetInstrumentState`, the executor derives `Status` from the instrument state. After a failed lid or run command sets `Status` to `3` (Error), the next command resets it to `1` (Idle) if the instrument reports idle.
- **`Reset` can't currently succeed.** Its status check passes only while the instrument itself reports an error. In that case, `Reset` fails with "The instrument error has not been resolved." Fixing this needs a change in the command executor ([atc-sila2#1](https://github.com/plan5-labs/atc-sila2/issues/1)).
- **`Status` isn't polled.** It changes only on commands and on run events.

The executor's streams also have bugs that show only in real mode, because the simulated executor doesn't reproduce them ([atc-sila2#2](https://github.com/plan5-labs/atc-sila2/issues/2)):

- **Subscribers of the same stream cancel each other.** Don't run another client of the command executor, such as the C# server, alongside the connector. If the connector's status stream is cancelled, the connector reports `NotConnected` for about 5 seconds, until it subscribes again.
- **Elapsed-time subscriptions leak.** Each time the connector restarts while the executor stays connected to the ATC, the executor keeps one more elapsed-time handler. After a restart, `ElapsedTime` can briefly replay stale values.

## Development

Set up the environment, run the tests and lint the sources:

```sh
uv sync --all-extras
uv run pytest
uv run ruff format src/ && uv run ruff check src/ --fix
```

To reload the connector whenever a source file changes, run `uv run connector dev`.

GitHub Actions (`.github/workflows/tests.yml`) runs the lint checks and the tests on every pull request and on pushes to `main`. The tests run on Ubuntu and Windows, with Python 3.10 and 3.14.

The tests run against the simulated command executor. `tests/features/test_automated_thermal_cycler_controller.py` compares the feature definition the connector serves with the one of the C# server, in `tests/features/AutomatedThermalCyclerController-v1_0.sila.xml`. Keep that test passing to stay compatible with existing clients.

### Project layout

```text
src/unitelabs/applied_biosystems_atc/
  __init__.py                    # create_app: protocol, simulator and features
  config.py                      # connector configuration
  features/
    automated_thermal_cycler_controller/  # the SiLA feature of the C# server
    simulation_controller/                # switching between simulated and real ATC
  io/                            # no SiLA knowledge
    protocol.py                  # gRPC client of the command executor, error translation
    simulation.py                # simulated command executor
    errors.py                    # the defined execution errors
    command_executor/            # executor .proto and generated stubs
```

### Command executor stubs

`io/command_executor/command_executor.proto` is a copy of the command executor's `.proto` file. After changing it, regenerate the Python stubs:

```sh
cd src
uv run python -m grpc_tools.protoc -I . --python_out=. --pyi_out=. --grpc_python_out=. \
  unitelabs/applied_biosystems_atc/io/command_executor/command_executor.proto
```

The generated code requires at least the grpcio-tools and protobuf versions it was generated with. If you regenerate with a newer grpcio-tools, raise the minimum `grpcio` and `protobuf` versions in `pyproject.toml` to match.

### Template updates

The project follows the UniteLabs [connector-factory](https://gitlab.com/unitelabs/cdk/connector-factory) template, recorded in `.cruft.json`. To pull in later template changes, run `cruft update`.
