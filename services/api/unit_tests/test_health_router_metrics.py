from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from botcheck_api import metrics as api_metrics
from botcheck_api.shared import health_router


@pytest.mark.asyncio
async def test_observe_run_queue_depths_reads_known_arq_queues_via_zcard() -> None:
    redis_pool = type(
        "RedisPoolStub",
        (),
        {
            "zcard": AsyncMock(side_effect=[4, 2, 1, 3]),
        },
    )()

    await health_router._observe_run_queue_depths(redis_pool)

    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:judge")._value.get() == 4
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:cache")._value.get() == 2
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:scheduler")._value.get() == 1
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:eval")._value.get() == 3
    assert redis_pool.zcard.await_args_list[0].args == ("arq:judge",)
    assert redis_pool.zcard.await_args_list[1].args == ("arq:cache",)
    assert redis_pool.zcard.await_args_list[2].args == ("arq:scheduler",)
    assert redis_pool.zcard.await_args_list[3].args == ("arq:eval",)


@pytest.mark.asyncio
async def test_observe_run_queue_depths_falls_back_to_llen_when_zcard_is_unavailable() -> None:
    redis_pool = type(
        "RedisPoolStub",
        (),
        {
            "llen": AsyncMock(side_effect=[4, 2, 1, 3]),
        },
    )()

    await health_router._observe_run_queue_depths(redis_pool)

    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:judge")._value.get() == 4
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:cache")._value.get() == 2
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:scheduler")._value.get() == 1
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:eval")._value.get() == 3
    assert redis_pool.llen.await_args_list[0].args == ("arq:judge",)
    assert redis_pool.llen.await_args_list[1].args == ("arq:cache",)
    assert redis_pool.llen.await_args_list[2].args == ("arq:scheduler",)
    assert redis_pool.llen.await_args_list[3].args == ("arq:eval",)


@pytest.mark.asyncio
async def test_observe_run_queue_depths_defaults_to_zero_without_pool() -> None:
    await health_router._observe_run_queue_depths(None)

    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:judge")._value.get() == 0
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:cache")._value.get() == 0
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:scheduler")._value.get() == 0
    assert api_metrics.RUN_QUEUE_DEPTH.labels(queue="arq:eval")._value.get() == 0
