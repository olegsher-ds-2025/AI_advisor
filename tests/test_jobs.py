import pytest

from scheduler import jobs


def test_steps_run_in_order_and_first_failure_stops_the_pipeline(monkeypatch):
    calls = []

    def step(name, fail=False):
        def call():
            calls.append(name)
            if fail:
                raise RuntimeError(name)
        return call

    monkeypatch.setattr(jobs, "build_steps", lambda top, watch: {"a": step("a"), "b": step("b", fail=True), "c": step("c")})

    with pytest.raises(SystemExit):
        jobs.run(None, 10, 50)

    assert calls == ["a", "b"]
