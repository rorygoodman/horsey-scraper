"""Tests for common.jsonio: dataclass tree → camelCase dict → atomic JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from common.jsonio import to_camel_dict, write_json
from common.markettype import MarketType


@dataclass(frozen=True)
class Leaf:
    win_price: float | None
    selection_id: int | None


@dataclass(frozen=True)
class Node:
    market_name: str
    lay: dict
    children: list = field(default_factory=list)


RENAME = {
    "win_price": "winPrice",
    "selection_id": "selectionId",
    "market_name": "marketName",
}


class TestToCamelDict:
    def test_renames_fields(self):
        out = to_camel_dict(Leaf(win_price=2.5, selection_id=66986352), RENAME)
        assert out == {"winPrice": 2.5, "selectionId": 66986352}

    def test_none_preserved(self):
        out = to_camel_dict(Leaf(win_price=None, selection_id=None), RENAME)
        assert out == {"winPrice": None, "selectionId": None}

    def test_int_stays_int(self):
        out = to_camel_dict(Leaf(win_price=5.0, selection_id=832048), RENAME)
        assert isinstance(out["selectionId"], int)
        assert isinstance(out["winPrice"], float)

    def test_markettype_dict_keys_become_names(self):
        node = Node(
            market_name="x",
            lay={MarketType.WIN: 2.72, MarketType.TOP_2: 1.99},
        )
        out = to_camel_dict(node, RENAME)
        assert out["lay"] == {"WIN": 2.72, "TOP_2": 1.99}

    def test_markettype_value_becomes_name(self):
        @dataclass(frozen=True)
        class Holder:
            t: MarketType

        assert to_camel_dict(Holder(MarketType.TOP_4), {}) == {"t": "TOP_4"}

    def test_nested_dataclasses_and_lists(self):
        node = Node(
            market_name="race",
            lay={MarketType.WIN: None},
            children=[Leaf(1.0, 2), Leaf(None, None)],
        )
        out = to_camel_dict(node, RENAME)
        assert out["children"] == [
            {"winPrice": 1.0, "selectionId": 2},
            {"winPrice": None, "selectionId": None},
        ]

    def test_field_order_preserved(self):
        out = to_camel_dict(Node("n", {}, []), RENAME)
        assert list(out.keys()) == ["marketName", "lay", "children"]


class TestWriteJson:
    def test_writes_and_reads_back(self, tmp_path: Path):
        target = tmp_path / "out.json"
        write_json(Leaf(2.5, 7), RENAME, target)
        assert json.loads(target.read_text()) == {"winPrice": 2.5, "selectionId": 7}

    def test_atomic_no_tmp_left(self, tmp_path: Path):
        target = tmp_path / "out.json"
        write_json(Leaf(2.5, 7), RENAME, target)
        assert not (tmp_path / "out.json.tmp").exists()

    def test_two_space_indent(self, tmp_path: Path):
        target = tmp_path / "out.json"
        write_json(Leaf(2.5, 7), RENAME, target)
        assert '\n  "winPrice"' in target.read_text()
