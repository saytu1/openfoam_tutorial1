from natconv.params import Evaporator


def test_default_valid():
    assert Evaporator().validate() == []


def test_tube_count():
    e = Evaporator()
    assert e.n_rows * e.n_cols == 12


def test_bad_counts_reported():
    e = Evaporator(n_rows=0)
    assert any("n_rows" in m for m in e.validate())


def test_fin_thinner_than_pitch():
    e = Evaporator(fin_thickness=0.002, fin_pitch_x=0.008)   # m
    assert e.validate() == []
    e2 = Evaporator(fin_thickness=0.02, fin_pitch_x=0.01)
    e2.fin_pitch_x = 0.01; e2.fin_thickness = 0.02
    assert any("fin" in m for m in e2.validate())
