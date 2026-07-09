import os
from natconv.logparse import parse_convergence


def test_parse_series():
    log = open(os.path.join(os.path.dirname(__file__), "fixtures", "sample_solver.log")).read()
    d = parse_convergence(log)
    assert d["T_avg"] == [451.16, 491.37]
    assert d["T_max"] == [508.6, 543.2]
    assert d["qr"] == [-1794.0, -2639.0]
    assert len(d["T_avg"]) == 2
