# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-03

### Added

- SiLA 2 connector for the Applied Biosystems Automated Thermal Cycler (ATC), built on the UniteLabs CDK. It is a port of the C# SiLA server in [plan5-labs/atc-sila2](https://github.com/plan5-labs/atc-sila2).
- `org.riken/instruments/AutomatedThermalCyclerController/v1` feature, compatible with the C# server: the commands `Load`, `Validate`, `OpenLid`, `CloseLid`, `StartRun`, `StopRun`, `Reset` and `GetInstrumentState`, and the properties `ElapsedTime`, `RemainingTime` and `Status`.
- Control of the instrument through the existing command executor, over gRPC on `localhost:5141` by default.
- Simulation mode, on by default, with a simulated command executor, and the `SimulationController` feature to switch between simulation and real mode.

[0.1.0]: https://github.com/plan5-labs/atc-sila2-connector/tree/v0.1.0
