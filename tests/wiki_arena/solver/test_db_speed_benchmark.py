import pytest
import pytest_asyncio
import time
from statistics import mean, stdev
from typing import Callable, Awaitable
import random

from wiki_arena.solver.static_db import StaticSolverDB, static_solver_db

REPEAT = 100
SEED = 42

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def solver_db():
    return static_solver_db

@pytest_asyncio.fixture(scope="function")
async def random_page_ids(solver_db: StaticSolverDB):
    import random
    SEED = 42
    REPEAT = 100

    random.seed(SEED)
    total_pages, _ = await solver_db.get_database_stats()

    sampled_ids = []
    tried = set()
    while len(sampled_ids) < REPEAT:
        candidate = random.randint(1, total_pages)
        if candidate in tried:
            continue
        tried.add(candidate)
        try:
            title = await solver_db.get_page_title(candidate)
            if title:
                sampled_ids.append(candidate)
        except Exception:
            continue
    return sampled_ids

@pytest_asyncio.fixture(scope="function")
async def random_page_titles(solver_db: StaticSolverDB, random_page_ids):
    titles = []
    for page_id in random_page_ids:
        try:
            title = await solver_db.get_page_title(page_id)
            if title:
                titles.append(title)
        except Exception:
            continue
    return titles


# ──────────────────────────────────────────────────────────────────────────────
# Timer Utility
# ──────────────────────────────────────────────────────────────────────────────

async def time_async_fn(
    fn: Callable,
    *static_args,
    repeat=REPEAT,
    arg_generator_fn: Callable[[], Awaitable[tuple]] = None,
):
    times = []
    for _ in range(repeat):
        args = static_args
        if arg_generator_fn:
            args = await arg_generator_fn()
        t0 = time.perf_counter()
        await fn(*args)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
    return times


# ──────────────────────────────────────────────────────────────────────────────
# Individual Performance Tests (using random pages)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_page_id_lookup_speed(solver_db: StaticSolverDB, random_page_titles):
    async def arg_gen():
        return (random_page_titles.pop(), -1)
    times = await time_async_fn(solver_db.get_page_id, arg_generator_fn=arg_gen)
    print(f"🧠 get_page_id(random, ns=-1): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 100


@pytest.mark.asyncio
async def test_page_title_lookup_speed(solver_db: StaticSolverDB, random_page_ids):
    async def arg_gen():
        return (random_page_ids.pop(),)
    times = await time_async_fn(solver_db.get_page_title, arg_generator_fn=arg_gen)
    print(f"📘 get_page_title(random): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 100


@pytest.mark.asyncio
async def test_outgoing_links_speed(solver_db: StaticSolverDB, random_page_ids):
    async def arg_gen():
        return (random_page_ids.pop(),)
    times = await time_async_fn(solver_db.get_outgoing_links, arg_generator_fn=arg_gen)
    print(f"🔗 get_outgoing_links(random): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 150


@pytest.mark.asyncio
async def test_incoming_links_speed(solver_db: StaticSolverDB, random_page_ids):
    async def arg_gen():
        return (random_page_ids.pop(),)
    times = await time_async_fn(solver_db.get_incoming_links, arg_generator_fn=arg_gen)
    print(f"🔗 get_incoming_links(random): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 150


@pytest.mark.asyncio
async def test_outgoing_link_counts_speed(solver_db: StaticSolverDB, random_page_ids):
    async def arg_gen():
        return ([random_page_ids.pop()],)
    times = await time_async_fn(solver_db.fetch_outgoing_links_count, arg_generator_fn=arg_gen)
    print(f"📈 fetch_outgoing_links_count(random): {mean(times):.2f} ± {stdev(times):.2f} ms")


@pytest.mark.asyncio
async def test_incoming_link_counts_speed(solver_db: StaticSolverDB, random_page_ids):
    async def arg_gen():
        return ([random_page_ids.pop()],)
    times = await time_async_fn(solver_db.fetch_incoming_links_count, arg_generator_fn=arg_gen)
    print(f"📈 fetch_incoming_links_count(random): {mean(times):.2f} ± {stdev(times):.2f} ms")


# ──────────────────────────────────────────────────────────────────────────────
# Other Static Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_database_stats(solver_db: StaticSolverDB):
    pages, links = await solver_db.get_database_stats()
    print(f"📊 DB Stats: {pages:,} pages, {links:,} total links")
    assert pages > 0 and links > 0


@pytest.mark.asyncio
async def test_empty_batch_inputs(solver_db: StaticSolverDB):
    titles = await solver_db.batch_get_page_ids([])
    ids = await solver_db.batch_get_page_titles([])
    print(f"🧪 Empty batch inputs returned {len(titles)} ids, {len(ids)} titles")
    assert titles == {} and ids == []