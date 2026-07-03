"""CSV parser/writer quirks on synthetic inputs (ports celeri_ui semantics
plus the plan's intentional fixes)."""

from __future__ import annotations

from celeri_builder.io.block_io import read_blocks
from celeri_builder.io.segment_io import read_segments, write_segments
from celeri_builder.io.tabular import Table, read_table, write_table
from celeri_builder.io.velocity_io import read_velocities
from celeri_builder.model.schema import SEGMENT_FIELDS


def test_crlf_equals_lf():
    lf = "name,lon,lat\nalpha,1.5,2.5\nbeta,3.25,4.0\n"
    crlf = lf.replace("\n", "\r\n")
    assert read_table(crlf) == read_table(lf)


def test_blank_lines_skipped():
    table = read_table("name,flag\n\n  \na,1\n\nb,2\n\n")
    assert [row["name"] for row in table.rows] == ["a", "b"]


def test_whitespace_padded_quoted_name():
    table = read_table('name,lon\n  "  padded name  "  ,1.0\n')
    assert table.rows[0]["name"] == "padded name"
    # re-quoted (it contains whitespace) and lon gets 6 decimals
    assert write_table(table).split("\n")[1] == '"padded name",1.000000'


def test_comma_bearing_string_quoted_on_write():
    out = write_table(Table(columns=["name"], rows=[{"name": "a, b"}]))
    assert out == 'name\n"a, b"\n'


def test_numeric_looking_name_007_stays_string():
    table = read_table("name,flag\n007,1\n")
    value = table.rows[0]["name"]
    assert value == "007"
    assert isinstance(value, str)
    assert write_table(table).split("\n")[1] == "007,1"


def test_plain_integer_name_coerces_to_int():
    table = read_table("name\n2\n")
    assert table.rows[0]["name"] == 2
    assert isinstance(table.rows[0]["name"], int)


def test_unknown_extra_column_preserved_with_values_and_order():
    text = (
        "name,lon1,lat1,lon2,lat2,weird,zed\n"
        "seg1,1.0,2.0,3.0,4.0,banana,x\n"
        "seg2,5.0,6.0,7.0,8.0,42,y\n"
    )
    graph = read_segments(text)
    assert graph.segments[0]["weird"] == "banana"
    assert graph.segments[1]["weird"] == 42
    out = write_segments(graph)
    header = out.split("\n")[0].split(",")
    assert header == [*SEGMENT_FIELDS, "weird", "zed"]
    reread = read_table(out)
    assert [row["weird"] for row in reread.rows] == ["banana", 42]
    assert [row["zed"] for row in reread.rows] == ["x", "y"]


def test_missing_known_columns_synthesized_with_read_defaults():
    text = "lon1,lat1,lon2,lat2\n1.0,2.0,3.0,4.0\n"
    graph = read_segments(text)
    seg = graph.segments[0]
    assert seg["name"] == ""
    assert seg["dip"] == 0
    assert seg["locking_depth"] == 0
    out_row = read_table(write_segments(graph)).rows[0]
    assert out_row["dip"] == 0
    assert out_row["name"] == ""


def test_empty_cell_gets_read_default():
    text = "name,lon1,lat1,lon2,lat2,dip\nseg1,1.0,2.0,3.0,4.0,\n"
    assert read_segments(text).segments[0]["dip"] == 0


def test_empty_file():
    table = read_table("")
    assert table.columns == []
    assert table.rows == []
    assert write_table(table) == ""
    assert read_segments("").segments == ()
    assert read_blocks("") == ()
    assert read_velocities("") == ()


def test_header_only_gives_zero_rows():
    table = read_table("name,lon,lat\n")
    assert table.columns == ["name", "lon", "lat"]
    assert table.rows == []
    assert read_blocks("name,interior_lon\n") == ()


def test_six_decimal_rule_applies_to_lon_lat_substring_names():
    table = Table(
        columns=["euler_lon_sig", "plain_sig", "lat_thing", "count"],
        rows=[{"euler_lon_sig": 1.5, "plain_sig": 1.5, "lat_thing": 2, "count": 7}],
    )
    out = write_table(table)
    assert out == "euler_lon_sig,plain_sig,lat_thing,count\n1.500000,1.5,2.000000,7\n"
