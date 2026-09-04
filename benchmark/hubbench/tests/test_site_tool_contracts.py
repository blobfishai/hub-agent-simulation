from copy import deepcopy

from hubbench.site_data import load_families, tool_records


def test_same_tool_name_retains_each_family_schema():
    entries = [
        {"slug": "legal", "tools": [{"name": "task.submit", "inputSchema": {"required": ["matter_id"]}}]},
        {"slug": "clinic", "tools": [{"name": "task.submit", "inputSchema": {"required": ["purchase_order"]}}]},
    ]
    before = deepcopy(entries)
    rows = tool_records(entries)
    assert len(rows) == 2
    assert {row["family"]: row["inputSchema"]["required"] for row in rows} == {
        "legal": ["matter_id"], "clinic": ["purchase_order"],
    }
    assert all(row["name"] == "task.submit" for row in rows)
    assert entries == before


def test_explorer_preserves_every_released_family_contract():
    entries = load_families()
    rows = tool_records(entries)
    expected = {(entry["slug"], tool["name"]): tool for entry in entries for tool in entry["tools"]}
    assert len(rows) == len(expected) == 554
    assert len({(row["family"], row["name"]) for row in rows}) == len(rows)
    for row in rows:
        source = expected[(row["family"], row["name"])]
        assert row["inputSchema"] == source.get("inputSchema", {})
        assert row["annotations"] == source.get("annotations", {})
        assert row["_meta"]["hubbench"]["families"] == [row["family"]]
