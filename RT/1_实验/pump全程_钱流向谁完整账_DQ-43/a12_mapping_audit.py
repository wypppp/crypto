"""完整S映射与旧映射的逐钱包差异证明；身份和路径只写raw。"""

import csv
import gzip
import hashlib
import json
from collections import defaultdict, deque
from decimal import Decimal

import a10_check as C
import s3_ref as R


def links(edges, cex):
    neighbors = {k: defaultdict(set) for k in ("S", "T")}
    funders = defaultdict(set)
    for e in edges:
        k, a, b = e["kind"], e["a"], e["b"]
        if k in neighbors:
            neighbors[k][a].add(b)
            neighbors[k][b].add(a)
        elif k == "G" and e.get("x") not in (None, ""):
            x = Decimal(str(e["x"]))
            if x.is_finite() and 0 <= x <= 200 and x == int(x) and a not in cex:
                funders[a].add(b)
    out = defaultdict(set)
    for k, nb in neighbors.items():
        for a, bs in nb.items():
            for b in bs:
                if (
                    a != b
                    and not ({a, b} & cex)
                    and len(bs) <= 200
                    and len(nb[b]) <= 200
                ):
                    out[tuple(sorted((a, b)))].add(k)
    for bs in funders.values():
        for b in bs - {min(bs)}:
            out[tuple(sorted((min(bs), b)))].add("G")
    return dict(out)


def graph_map(pairs):
    graph = defaultdict(set)
    for a, b in pairs:
        graph[a].add(b)
        graph[b].add(a)
    found, emap = set(), {}
    for root in sorted(graph):
        if root in found:
            continue
        todo, component = [root], set()
        while todo:
            u = todo.pop()
            if u in component:
                continue
            component.add(u)
            todo.extend(graph[u] - component)
        found |= component
        if len(component) > 1:
            emap.update({u: min(component) for u in component})
    return graph, emap


def path(graph, a, b):
    todo, prev = deque([a]), {a: None}
    while todo:
        u = todo.popleft()
        if u == b:
            out = []
            while prev[u] is not None:
                out.append(tuple(sorted((u, prev[u]))))
                u = prev[u]
            return out
        for v in sorted(graph[u]):
            if v not in prev:
                prev[v] = u
                todo.append(v)
    raise ValueError("实体代表缺可达路径")


def explain(old_edges, new_edges, cex):
    old_links, new_links = links(old_edges, cex), links(new_edges, cex)
    old_graph, old_map = graph_map(old_links)
    new_graph, new_map = graph_map(new_links)
    assert old_map == R.entities(old_edges, cex)[0]
    assert new_map == R.entities(new_edges, cex)[0]
    added, removed = (
        new_links.keys() - old_links.keys(),
        old_links.keys() - new_links.keys(),
    )
    differences = []
    for u in sorted(old_map.keys() | new_map.keys()):
        a, b = old_map.get(u, u), new_map.get(u, u)
        if a == b:
            continue
        old_path, new_path = path(old_graph, u, a), path(new_graph, u, b)
        new_evidence, old_evidence = set(new_path) & added, set(old_path) & removed
        assert new_evidence or old_evidence, "映射改变缺逐条路径证据"
        differences.append(
            {
                "wallet": u,
                "old_entity": a,
                "new_entity": b,
                "added_path_edges": sorted(new_evidence),
                "removed_path_edges": sorted(old_evidence),
                "added_kinds": sorted(
                    set().union(*(new_links[p] for p in new_evidence))
                ),
                "removed_kinds": sorted(
                    set().union(*(old_links[p] for p in old_evidence))
                ),
            }
        )
    return differences, {
        "independent_graph_equals_frozen_reference": True,
        "added_legal_links": len(added),
        "removed_legal_links": len(removed),
        "mapping_difference_wallets": len(differences),
        "explained_wallets": len(differences),
        "unexplained_wallets": 0,
        "added_link_kinds": sorted(set().union(*(new_links[p] for p in added))),
        "removed_link_kinds": sorted(set().union(*(old_links[p] for p in removed))),
    }


def main():
    with gzip.open(C.SM.CEX, "rt", newline="") as f:
        cex = {r["address"] for r in csv.DictReader(f)}
    old_edges, new_edges = C.raw(C.SM.EDGE), C.raw(C.EDGE)
    differences, out = explain(old_edges, new_edges, cex)
    old_map = json.loads((C.SM.H / "runs/s3_smoke_emap.json").read_text())["emap"]
    assert R.entities(old_edges, cex)[0] == old_map
    dest = C.SM.H / "raw/dune/a12_mapping_path_evidence.json.gz"
    with gzip.open(dest, "wt") as f:
        json.dump(differences, f, ensure_ascii=False)
    out.update(
        private_evidence=str(dest.relative_to(C.SM.H)),
        private_evidence_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
    )
    (C.SM.H / "runs/a12_mapping_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
