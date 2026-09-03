"""Tests for StoriesUsagePlanner (budget -> chunks the player would emit)."""

import random

from Resolucion_script_rosseta.aplicacion.services.stories_usage_planner import (
    StoriesUsagePlanner,
)


class TestStoriesUsagePlanner:
    def test_chunks_add_up_to_the_budget(self):
        planner = StoriesUsagePlanner(rng=random.Random(7))
        chunks = planner.chunks(4000)
        assert sum(chunks) == 4000

    def test_chunks_respect_the_configured_size(self):
        planner = StoriesUsagePlanner(chunk_min_sec=100, chunk_max_sec=200, rng=random.Random(3))
        chunks = planner.chunks(1000)
        # Todos menos el último, que se ajusta al resto.
        assert all(100 <= chunk <= 200 for chunk in chunks[:-1])
        assert chunks[-1] <= 200

    def test_a_budget_smaller_than_one_chunk_is_a_single_send(self):
        planner = StoriesUsagePlanner(chunk_min_sec=300, chunk_max_sec=900)
        assert planner.chunks(120) == [120]

    def test_no_budget_means_no_sends(self):
        planner = StoriesUsagePlanner()
        assert planner.chunks(0) == []
        assert planner.chunks(-60) == []

    def test_inverted_bounds_are_straightened_out(self):
        planner = StoriesUsagePlanner(chunk_min_sec=900, chunk_max_sec=300)
        assert planner.chunk_min_sec == 300
        assert planner.chunk_max_sec == 900

    def test_hours_to_seconds(self):
        assert StoriesUsagePlanner.hours_to_seconds(1.5) == 5400
        assert StoriesUsagePlanner.hours_to_seconds(-2) == 0

