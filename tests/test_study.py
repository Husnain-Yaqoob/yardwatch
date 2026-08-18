from datetime import timedelta

from yardwatch import study


def test_sweep_returns_one_result_per_capacity():
    results = study.sweep([2, 3], nights=5)
    assert [r.capacity for r in results] == [2, 3]
    assert all(r.nights == 5 for r in results)


def test_more_bays_never_makes_the_slo_worse():
    """The capacities are paired on the same nights, so this must hold."""
    results = study.sweep([2, 3, 4], nights=40)
    slos = [r.mean_slo for r in results]
    assert slos == sorted(slos), f"SLO should improve with capacity, got {slos}"


def test_more_bays_never_increases_overflow():
    results = study.sweep([2, 4], nights=40)
    assert results[1].mean_overflow_minutes <= results[0].mean_overflow_minutes


def test_arrivals_are_independent_of_capacity():
    """Bay count must not change who turns up — otherwise the comparison is void."""
    results = study.sweep([2, 5], nights=30)
    assert results[0].mean_arrivals == results[1].mean_arrivals


def test_sweep_is_deterministic():
    first = study.sweep([2], nights=20)[0]
    second = study.sweep([2], nights=20)[0]
    assert first.mean_slo == second.mean_slo
    assert first.worst_peak_queue == second.worst_peak_queue


def test_stranded_rate_is_a_proportion():
    result = study.sweep([2], nights=25)[0]
    assert 0.0 <= result.stranded_rate <= 1.0


def test_a_longer_target_wait_cannot_lower_the_slo():
    tight = study.sweep([2], nights=30, target_wait=timedelta(minutes=5))[0]
    loose = study.sweep([2], nights=30, target_wait=timedelta(minutes=45))[0]
    assert loose.mean_slo >= tight.mean_slo


def test_markdown_table_has_a_row_per_capacity():
    table = study.as_markdown_table(study.sweep([2, 3], nights=5))
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    assert len(rows) == 3  # header + 2 capacities
