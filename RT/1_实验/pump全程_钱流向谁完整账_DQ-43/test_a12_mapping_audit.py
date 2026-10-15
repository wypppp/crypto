"""逐钱包解释覆盖新增桥接、201度拆分和G来源不入实体。"""

import a12_mapping_audit as A


def edge(k, a, b, x=""):
    return {"kind": k, "a": a, "b": b, "x": x}


def test_added_nonseed_bridge_has_per_wallet_path():
    old = [edge("S", "b", "c")]
    new = old + [edge("S", "a", "b")]
    differences, out = A.explain(old, new, set())
    assert out["mapping_difference_wallets"] == 2
    assert all(d["added_path_edges"] == [("a", "b")] for d in differences)
    assert out["unexplained_wallets"] == 0


def test_degree_201_splits_but_t_still_connects():
    old = [edge("S", "h", f"u{i:03}") for i in range(200)]
    new = old + [edge("S", "h", "u200"), edge("T", "u000", "u001")]
    differences, out = A.explain(old, new, set())
    assert out["removed_legal_links"] == 200
    assert len(differences) == 200
    assert all(d["removed_path_edges"] for d in differences)
    assert out["added_link_kinds"] == ["T"]


def test_g_funder_and_exchange_semantics():
    rows = [edge("G", "f", "b", "2"), edge("G", "f", "c", "2")]
    assert A.graph_map(A.links(rows, set()))[1] == {"b": "b", "c": "b"}
    assert A.links(rows, {"f"}) == {}
    assert (
        A.links([edge("G", "f", "b", "201"), edge("G", "f", "c", "201")], set()) == {}
    )
