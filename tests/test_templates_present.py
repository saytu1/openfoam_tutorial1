import os

BASE = os.path.join(os.path.dirname(__file__), "..", "natconv", "templates")


def test_key_templates_exist():
    for f in ["blockMeshDict.tmpl", "snappyHexMeshDict.tmpl", "controlDict.tmpl",
              "decomposeParDict.tmpl", "boundaryRadiationProperties.tmpl",
              "0.orig/T.tmpl", "fvSchemes", "thermophysicalProperties"]:
        assert os.path.exists(os.path.join(BASE, f)), f


def test_snappy_has_errorreduction():
    txt = open(os.path.join(BASE, "snappyHexMeshDict.tmpl")).read()
    assert "errorReduction" in txt
