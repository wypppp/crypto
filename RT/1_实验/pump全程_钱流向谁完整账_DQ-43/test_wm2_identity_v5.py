"""手算反例；不加载全量数据或计算真实S3。"""

from dataclasses import replace

import pytest

import a14_full as F
import s3_ref as R
from wm2_identity_v5 import Proof, StrongRows, activity, attach, entity_at, size_bins


def row(k, a, b=None, x=None):
    return {"kind": k, "a": a, "b": b, "x": x}


def mapped(rows):
    return R.entities([r for r in rows if r["kind"] != "V"])[0]


def test_nonseed_bridge_and_representative():
    rows = [row("V", "b"), row("V", "c"), row("S", "a", "b"), row("S", "a", "c")]
    assert mapped(rows) == {"a": "a", "b": "a", "c": "a"}
    assert mapped(StrongRows(rows)) == {}
    assert mapped(StrongRows([*rows, row("V", "a")])) == mapped(rows)


def test_service_degree_before_seed_filter():
    rows = [row("V", "hub"), row("V", "s0")]
    rows += [row("S", "hub", f"s{i}") for i in range(201)]
    assert list(StrongRows(rows)) == rows[:2]
    # 若错误地先只留两种子，就会把原服务节点重新启用。
    assert mapped([*rows[:2], row("S", "hub", "s0")])


@pytest.mark.parametrize(
    "fanout,cex,merged", [(200, (), True), (201, (), False), (200, ("f",), False)]
)
def test_g_keeps_nonseed_source_and_full_fanout(fanout, cex, merged):
    rows = [
        row("V", "a"),
        row("V", "b"),
        row("G", "f", "a", fanout),
        row("G", "f", "b", fanout),
    ]
    emap, _ = R.entities([r for r in StrongRows(rows) if r["kind"] != "V"], cex)
    assert (emap.get("b", "b") == "a") == merged
    assert "f" not in emap


def test_distribution_bins_hand_counts():
    assert size_bins(
        {1: 10, 2: 3, 3: 4, 5: 6, 6: 7, 11: 8, 21: 9, 51: 10, 201: 11}
    ) == {
        "2": 3,
        "3-5": 10,
        "6-10": 7,
        "11-20": 8,
        "21-50": 9,
        "51-200": 10,
        ">200": 11,
    }
    out = F.concentration([row("V", f"s{i}") for i in range(100)])
    assert out["largest_entity_W_seed_fraction"] == 0.01
    assert out["concentration_passed"]


FIXED = {"seed": "E", "nonseed_member": "E", "other_seed": "F"}
ANCHOR = (100, 2, 1, 0)
P = Proof("S", "nonseed_member", (100, 2, 0, 0), 1, 2, 50_000_000)


def get(proofs=(P,), **kwargs):
    return attach("q", ANCHOR, FIXED, proofs, {}, coverage_complete=True, **kwargs)


def test_attachment_nonseed_member_and_same_second_order():
    assert get().entity == "E"
    assert get([replace(P, key=ANCHOR)]).status == "unattached"
    assert get([replace(P, key=(100, 2, 2, 0))]).status == "unattached"
    assert get([replace(P, lamports=49_999_999)]).status == "unattached"
    assert get([replace(P, degree_other=201)]).status == "unattached"
    assert get(cex=("nonseed_member",)).status == "unattached"


def test_no_merge_no_chaining_and_ambiguous():
    other = replace(P, other="other_seed")
    assert get([P, other]).status == "ambiguous"
    assert get([replace(P, other="new_attached_q")]).status == "unattached"
    assert (
        attach("seed", ANCHOR, FIXED, [other], {}, coverage_complete=True).entity == "E"
    )
    assert FIXED == {"seed": "E", "nonseed_member": "E", "other_seed": "F"}


def test_unknown_is_not_unique_and_g_multiple_targets():
    assert (
        attach("q", ANCHOR, FIXED, [P], {}, coverage_complete=False).status == "unknown"
    )
    g = replace(P, kind="G", other="f", fanout=200, window_first=True)
    assert (
        attach(
            "q", ANCHOR, FIXED, [g], {"f": {"E", "F"}}, coverage_complete=True
        ).status
        == "ambiguous"
    )
    assert (
        attach("q", ANCHOR, FIXED, [g], {"f": {"E"}}, coverage_complete=True).entity
        == "E"
    )
    with pytest.raises(ValueError, match="扇出缺失"):
        get([replace(g, fanout=None)])


def test_event_before_anchor_does_not_inherit_future_identity():
    attachments = {"q": get()}
    assert entity_at("q", (100, 2, 0, 0), FIXED, attachments) == "q"
    assert entity_at("q", (100, 2, 1, 1), FIXED, attachments) == "E"


def test_activity_hand_counts_includes_any_buy_not_only_mature():
    # 买入已归属；没有成熟字段，最后30分钟买入照样计活动。
    out = activity(range(10), (0, 1), [0, 0, *range(2, 9)])
    assert out["groups"] == {
        "selected": {"n": 2, "active": 1},
        "eligible": {"n": 10, "active": 8},
        "nonselected": {"n": 8, "active": 7},
    }
    assert out["low_activity_flag"] is True  # .5 vs .8, 差-.3，比.625。
    assert activity([], [], ["q"])["low_activity_flag"] is None
    assert activity([1], [1], [])["low_activity_flag"] is None
    with pytest.raises(ValueError, match="子集"):
        activity([1], [2], [])
