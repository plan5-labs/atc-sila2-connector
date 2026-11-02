import asyncio
import collections.abc

import typing_extensions as typing

from unitelabs.cdk import Replay, Subject

T = typing.TypeVar("T")


async def watch(subject: Subject[T]) -> collections.abc.AsyncIterator[T]:
    """
    Yield the current value of a subject and then every change, until the consumer is cancelled.

    A CDK `Subscription` ends its iteration when the task iterating it is cancelled, swallowing the
    cancellation. Servers that cancel a subscription and then await it for the `CancelledError`
    would see the end of iteration instead (and log a `RuntimeError`), so this restores the
    cancellation.

    Args:
      subject: The subject to watch.

    Yields:
      The current value, then every change.
    """

    subscription = subject.subscribe(replay=Replay.CURRENT)
    try:
        async for value in subscription:
            yield value
    finally:
        subscription.terminate()

    # The subscription is never closed otherwise, so the iteration only ends by cancellation.
    raise asyncio.CancelledError
