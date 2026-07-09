from natconv.postprocess import read_scalar_field, read_vector_field


def test_read_scalar(tmp_path):
    p = tmp_path / "T"
    p.write_text("dimensions [0 0 0 1 0 0 0];\n"
                 "internalField   nonuniform List<scalar> \n3\n(\n298.1\n400.2\n555.3\n)\n;\n")
    assert read_scalar_field(str(p)) == [298.1, 400.2, 555.3]


def test_read_vector(tmp_path):
    p = tmp_path / "C"
    p.write_text("internalField   nonuniform List<vector> \n2\n(\n(0 0 0)\n(1 2 3)\n)\n;\n")
    assert read_vector_field(str(p)) == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
