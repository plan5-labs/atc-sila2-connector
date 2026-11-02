import pathlib
import xml.etree.ElementTree as ElementTree

import pytest
from sila.framework import DefinedExecutionError

from tests.conftest import PROTOCOL_FILE
from tests.features.conftest import run
from unitelabs.applied_biosystems_atc.features.simulation_controller import SimulationController

FEATURE = "org.riken/instruments/AutomatedThermalCyclerController/v1"

ORIGINAL_DEFINITION = pathlib.Path(__file__).with_name("AutomatedThermalCyclerController-v1_0.sila.xml")
"""The feature definition of the C# SiLA server, copied unchanged from https://github.com/plan5-labs/atc-sila2."""

NAMESPACE = "{http://www.sila-standard.org}"


def text(element: ElementTree.Element, tag: str) -> str:
    """The text of the child `tag`, with whitespace and non-breaking hyphens normalized."""

    child = element.find(NAMESPACE + tag)
    value = "" if child is None or child.text is None else child.text
    return " ".join(value.replace("\N{NON-BREAKING HYPHEN}", "-").split())


def data_type(element: ElementTree.Element) -> tuple:
    """A data type element as nested tuples of tag, text and children."""

    return (
        element.tag.removeprefix(NAMESPACE),
        (element.text or "").strip(),
        tuple(data_type(child) for child in element),
    )


def elements(element: ElementTree.Element, tag: str) -> tuple:
    return tuple(
        (text(child, "Identifier"), text(child, "DisplayName"), data_type(child.find(NAMESPACE + "DataType")))
        for child in element.iter(NAMESPACE + tag)
    )


def errors(element: ElementTree.Element) -> frozenset[str]:
    return frozenset(
        (identifier.text or "").strip()
        for identifier in element.iterfind(f"{NAMESPACE}DefinedExecutionErrors/{NAMESPACE}Identifier")
    )


def interface(definition: str) -> dict:
    """Reduce a feature definition to what SiLA clients depend on, ignoring the order of elements."""

    feature = ElementTree.fromstring(definition)
    result: dict = {
        "Originator": feature.get("Originator"),
        "Category": feature.get("Category"),
        "FeatureVersion": feature.get("FeatureVersion"),
        "MaturityLevel": feature.get("MaturityLevel", "Draft"),
        "Identifier": text(feature, "Identifier"),
        "DisplayName": text(feature, "DisplayName"),
    }

    for command in feature.iterfind(NAMESPACE + "Command"):
        result[f"Command {text(command, 'Identifier')}"] = {
            "DisplayName": text(command, "DisplayName"),
            "Observable": text(command, "Observable"),
            "Parameters": elements(command, "Parameter"),
            "Responses": elements(command, "Response"),
            "IntermediateResponses": elements(command, "IntermediateResponse"),
            "DefinedExecutionErrors": errors(command),
        }

    for property_ in feature.iterfind(NAMESPACE + "Property"):
        result[f"Property {text(property_, 'Identifier')}"] = {
            "DisplayName": text(property_, "DisplayName"),
            "Observable": text(property_, "Observable"),
            "DataType": data_type(property_.find(NAMESPACE + "DataType")),
            "DefinedExecutionErrors": errors(property_),
        }

    for error in feature.iterfind(NAMESPACE + "DefinedExecutionError"):
        result[f"DefinedExecutionError {text(error, 'Identifier')}"] = text(error, "DisplayName")

    return result


def descriptions(definition: str) -> dict[str, str]:
    """All descriptions of a feature definition by the identifier path of their element."""

    result = {}

    def visit(element: ElementTree.Element, path: str) -> None:
        identifier = text(element, "Identifier")
        path = f"{path}/{identifier}" if identifier else path
        if element.find(NAMESPACE + "Description") is not None:
            result[path] = text(element, "Description")
        for child in element:
            if child.tag != NAMESPACE + "DataType":
                visit(child, path)

    visit(ElementTree.fromstring(definition), "")
    return result


@pytest.fixture
async def served_definition(client) -> str:
    responses = await client.SiLAService.GetFeatureDefinition(FeatureIdentifier=FEATURE)
    return responses.FeatureDefinition


class TestFeatureDefinition:
    async def test_matches_interface_of_original_server(self, served_definition):
        assert interface(served_definition) == interface(ORIGINAL_DEFINITION.read_text(encoding="utf-8-sig"))

    async def test_matches_descriptions_of_original_server(self, served_definition):
        assert descriptions(served_definition) == descriptions(ORIGINAL_DEFINITION.read_text(encoding="utf-8-sig"))


class TestRun:
    async def test_runs_protocol_to_completion(self, client):
        atc = client.AutomatedThermalCyclerController
        statuses = await atc.Status.subscribe()
        assert await anext(statuses) == 1

        await run(atc.Load, ProtocolFileData=PROTOCOL_FILE)
        await run(atc.Validate, MaxSampleVolume=0.0)
        await run(atc.CloseLid)
        await run(atc.StartRun)

        assert await anext(statuses) == 2
        assert await anext(statuses) == 1
        statuses.close()

    async def test_reports_instrument_state_during_run(self, connector, client):
        connector.get_feature(SimulationController).simulator.run_duration = 1000
        atc = client.AutomatedThermalCyclerController
        await run(atc.Load, ProtocolFileData=PROTOCOL_FILE)
        await run(atc.Validate, MaxSampleVolume=0.0)
        await run(atc.CloseLid)

        await run(atc.StartRun)

        assert (await atc.GetInstrumentState()).InstrumentState == 2
        await run(atc.StopRun)

    async def test_streams_run_time(self, client):
        atc = client.AutomatedThermalCyclerController
        await run(atc.Load, ProtocolFileData=PROTOCOL_FILE)
        await run(atc.Validate, MaxSampleVolume=0.0)
        await run(atc.CloseLid)
        remaining_times = await atc.RemainingTime.subscribe()
        assert await anext(remaining_times) == "00:00:00"

        await run(atc.StartRun)

        values = [await anext(remaining_times) for _ in range(6)]
        remaining_times.close()
        assert values == ["00:00:05", "00:00:04", "00:00:03", "00:00:02", "00:00:01", "00:00:00"]

    async def test_reports_elapsed_time_while_idle(self, client):
        elapsed_time = await client.AutomatedThermalCyclerController.ElapsedTime.subscribe()

        assert await anext(elapsed_time) == "00:00:00"
        elapsed_time.close()


class TestErrors:
    @pytest.mark.parametrize(
        ("command", "parameters", "error"),
        [
            ("Load", {"ProtocolFileData": b"<Protocol>"}, "InvalidProtocol"),
            ("Validate", {"MaxSampleVolume": 0.0}, "ProtocolNotLoaded"),
            ("StartRun", {}, "ProtocolNotLoaded"),
            ("StopRun", {}, "InvalidInstrumentStatusError"),
            ("Reset", {}, "InvalidInstrumentStatusError"),
        ],
    )
    async def test_raises_defined_execution_error(self, client, command, parameters, error):
        with pytest.raises(DefinedExecutionError) as raised:
            await run(getattr(client.AutomatedThermalCyclerController, command), **parameters)

        assert raised.value.fully_qualified_identifier == f"{FEATURE}/DefinedExecutionError/{error}"

    async def test_raises_instrument_error_when_starting_with_lid_open(self, client):
        atc = client.AutomatedThermalCyclerController
        await run(atc.Load, ProtocolFileData=PROTOCOL_FILE)
        await run(atc.Validate, MaxSampleVolume=0.0)
        await run(atc.OpenLid)
        statuses = await atc.Status.subscribe()

        with pytest.raises(atc.InstrumentErrorOccurred):
            await run(atc.StartRun)

        assert [await anext(statuses), await anext(statuses)] == [1, 3]
        statuses.close()
