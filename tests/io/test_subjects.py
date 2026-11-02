import asyncio

import pytest

from unitelabs.applied_biosystems_atc.io import watch
from unitelabs.cdk import Subject


async def test_yields_current_value_then_changes():
    subject = Subject[int](maxsize=10, initial_value=1)
    values = watch(subject)

    assert await anext(values) == 1
    subject.update(2)
    assert await anext(values) == 2


async def test_ends_with_cancellation_of_consumer():
    subject = Subject[int](maxsize=10, initial_value=1)
    values = watch(subject)
    await anext(values)

    pending = asyncio.ensure_future(anext(values))
    await asyncio.sleep(0)
    pending.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not subject.subscribers
