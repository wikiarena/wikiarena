import pytest
import pytest_asyncio
import time
from statistics import mean, stdev
from typing import List

from wiki_arena.solver.static_db import StaticSolverDB, static_solver_db

REPEAT = 100

@pytest_asyncio.fixture(scope="function")
async def solver_db():
    return static_solver_db


async def time_async_fn(fn, *args, repeat=REPEAT):
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        await fn(*args)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)
    return times


@pytest.mark.asyncio
async def test_page_id_lookup_speed(solver_db: StaticSolverDB):
    title = "United_States"
    times = await time_async_fn(solver_db.get_page_id, title)
    print(f"\n🧠 get_page_id('{title}'): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 100


@pytest.mark.asyncio
async def test_page_title_lookup_speed(solver_db: StaticSolverDB):
    page_id = await solver_db.get_page_id("United_States")
    assert page_id is not None
    times = await time_async_fn(solver_db.get_page_title, page_id)
    print(f"📘 get_page_title({page_id}): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 100


@pytest.mark.asyncio
async def test_outgoing_links_speed(solver_db: StaticSolverDB):
    page_id = await solver_db.get_page_id("United_States")
    assert page_id is not None
    times = await time_async_fn(solver_db.get_outgoing_links, page_id)
    print(f"🔗 get_outgoing_links({page_id}): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 150


@pytest.mark.asyncio
async def test_incoming_links_speed(solver_db: StaticSolverDB):
    page_id = await solver_db.get_page_id("United_States")
    assert page_id is not None
    times = await time_async_fn(solver_db.get_incoming_links, page_id)
    print(f"🔗 get_incoming_links({page_id}): {mean(times):.2f} ± {stdev(times):.2f} ms")
    assert mean(times) < 150


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 5, 20, 100, 500])
async def test_batch_title_scaling(solver_db: StaticSolverDB, batch_size):
    page_id = await solver_db.get_page_id("United_States")
    ids = await solver_db.get_outgoing_links(page_id)
    sample_ids = ids[:batch_size]
    times = await time_async_fn(solver_db.batch_get_page_titles, sample_ids)
    print(f"📦 batch_get_page_titles({batch_size}): {mean(times):.2f} ± {stdev(times):.2f} ms")


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [1, 5, 20, 100, 500])
async def test_batch_id_scaling(solver_db: StaticSolverDB, batch_size):
    base_titles = ["Philosophy", "Science", "Mathematics", "History", "Art", "Economy", "Language", "Culture", "Law", "Religion"]
    titles = base_titles * (batch_size // len(base_titles) + 1)
    titles = titles[:batch_size]
    times = await time_async_fn(solver_db.batch_get_page_ids, titles)
    print(f"🧠 batch_get_page_ids({batch_size}): {mean(times):.2f} ± {stdev(times):.2f} ms")


@pytest.mark.asyncio
async def test_link_counts(solver_db: StaticSolverDB):
    page_id = await solver_db.get_page_id("United_States")
    outgoing = await solver_db.get_outgoing_links(page_id)
    incoming = await solver_db.get_incoming_links(page_id)
    print(f"📈 Link counts for 'United_States': {len(outgoing)} outgoing, {len(incoming)} incoming")
    assert isinstance(outgoing, list) and isinstance(incoming, list)


@pytest.mark.asyncio
async def test_redirect_resolution_time(solver_db: StaticSolverDB):
    title = "United_States"
    times = await time_async_fn(solver_db.get_page_id, title)
    print(f"↪️ Redirect resolution '{title}': {mean(times):.2f} ± {stdev(times):.2f} ms")


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