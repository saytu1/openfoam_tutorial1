from natconv.params import Geometry, Heat, Params


def make_valid():
    return Params(geometry=Geometry(kind="cylinder", D=0.0065, L=0.10),
                  heat=Heat(mode="flux", value=8500.0, emissivity=0.95))


def test_valid_params_have_no_errors():
    assert make_valid().validate() == []


def test_bad_emissivity_reported():
    p = make_valid(); p.heat.emissivity = 1.5
    assert any("emissivity" in e for e in p.validate())


def test_bad_heat_mode_reported():
    p = make_valid(); p.heat.mode = "xxx"
    assert any("mode" in e for e in p.validate())


def test_bad_geometry_kind_reported():
    p = make_valid(); p.geometry.kind = "torus"
    assert any("kind" in e for e in p.validate())


def test_enclosure_factor_range():
    p = make_valid(); p.enclosure_factor = 5.0
    assert any("enclosure" in e for e in p.validate())
