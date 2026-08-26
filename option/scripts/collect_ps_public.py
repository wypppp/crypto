#!/usr/bin/env python3
"""Collect auditable public-side evidence from Hebei's pollution-source site.

The collector deliberately stays within requests made by the public web UI.  The
``catalog`` command fetches only region, dictionary, enterprise and port metadata;
it never downloads monitoring values.  The separate ``snapshot`` command fetches
a bounded date window only for explicitly selected public-study points.  Raw
responses, response headers and hashes are retained so derived tables can be
reproduced.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASE_URL = "https://111.62.218.180:9920"
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")

PS_FIELDS = (
    "regionId,monitorTypeId,psName,enable,regulationIndustryId,"
    "isRubbish,psState,psTypeId,prRegionId"
)

DICTIONARIES = {
    "regulation_industry": {"type": "regulationIndustry", "enable": "1", "index": "0"},
    "ps_type": {"type": "psType", "enable": "1", "index": "0"},
    "monitor_type": {"type": "monitorTypeCode", "enable": "1", "index": "0"},
    "port_type": {"contType": "port_type", "enable": "1", "index": "0"},
}

# These terms implement section 5 of 06-内部元数据目录模板.md.  A match is
# discovery evidence only.  It never proves product, facility or outlet topology.
CANDIDATE_TERMS = {
    "A01": ["浮法", "玻璃熔窑", "熔化窑", "熔窑", "冷修", "锡槽", "退火窑"],
    "A02": ["纯碱", "氨碱", "联碱", "石灰窑", "碳化", "煅烧", "重碱", "轻碱干燥", "重碱干燥"],
    "A03": ["氧化铝", "流态化焙烧", "氢氧化铝焙烧", "熟料窑", "焙烧炉"],
    "A04": ["烧结机头", "烧结机尾", "烧结", "球团", "竖炉", "链篦机", "高炉", "热风炉", "出铁场", "制氧"],
    "A05": ["焦炉", "炉组", "装煤", "推焦", "焦侧", "机侧", "干熄焦", "湿熄焦", "结焦"],
    "A06": ["螺纹", "棒材轧线", "棒材", "方坯连铸", "钢坯加热炉", "转炉", "电炉"],
    "A13": ["热轧加热炉", "热连轧", "热轧", "热卷", "板坯连铸", "粗轧", "精轧", "卷取", "转炉"],
    "A07": ["PVC", "聚氯乙烯", "VCM", "氯乙烯", "PVC干燥", "聚合", "氯化氢"],
    "A08": ["氯碱", "电解槽", "片碱", "蒸发", "氯气", "烧碱"],
    "A09": ["合成氨", "气化炉", "转化炉", "尿素", "造粒塔", "高塔", "颗粒干燥", "硫回收"],
    "A10": ["玉米淀粉", "浸泡", "胚芽", "纤维", "蛋白粉", "淀粉干燥", "变性淀粉"],
    "A11": ["大豆压榨", "压榨", "浸出", "脱溶", "烘干", "豆粕", "豆油", "己烷"],
    "A12": ["再生铅", "二次铅", "废铅蓄电池", "还原炉", "熔炼炉", "回转炉", "精炼锅"],
}

PORT_TEXT_FIELDS = (
    "portName",
    "portNameSuffix",
    "outputName",
    "parentName",
    "productionNodeCode",
    "productionProcessCode",
    "samplingLocationStackArea",
)

PORT_EXPORT_FIELDS = (
    "id",
    "psId",
    "portCode",
    "portName",
    "portNameSuffix",
    "portTypeId",
    "monitorTypeId",
    "outputId",
    "outputName",
    "parentCode",
    "parentName",
    "productionNodeCode",
    "productionProcessCode",
    "samplingLocationStackArea",
    "regionId",
    "regionCode",
    "regionName",
    "enable",
    "portState",
    "networkStatus",
    "updateTime",
)
# Request only projections that the live endpoint currently serves correctly.
# Adding parentName/parentCode or region fields makes the public backend emit a
# reproducible SQL alias error (HTTP 400); region is joined from psInfo instead.
PORT_QUERY_FIELDS = (
    "id",
    "psId",
    "portCode",
    "portName",
    "portNameSuffix",
    "portTypeId",
    "outputId",
    "outputName",
    "productionNodeCode",
    "productionProcessCode",
    "samplingLocationStackArea",
)
PORT_FIELDS = ",".join(PORT_QUERY_FIELDS)


def iso_now() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def compact_now() -> str:
    return datetime.now(SHANGHAI).strftime("%Y%m%dT%H%M%S%z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


@dataclass
class FetchResult:
    url: str
    fetched_at: str
    status: int
    headers: dict[str, str]
    body: bytes
    method: str = "GET"
    request_body_sha256: str | None = None

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.body)


class PublicClient:
    def __init__(
        self,
        base_url: str,
        *,
        verify_tls: bool,
        use_env_proxy: bool,
        timeout: float,
        min_interval: float,
        retries: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.min_interval = min_interval
        self.retries = retries
        self.last_request = 0.0
        if verify_tls:
            self.context = ssl.create_default_context()
        else:
            self.context = ssl._create_unverified_context()  # noqa: SLF001
        proxy_handler = urllib.request.ProxyHandler() if use_env_proxy else urllib.request.ProxyHandler({})
        self.opener = urllib.request.build_opener(
            proxy_handler,
            urllib.request.HTTPSHandler(context=self.context),
        )

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get(self, path: str, params: dict[str, Any] | None = None) -> FetchResult:
        query = urllib.parse.urlencode(
            [(key, str(value)) for key, value in (params or {}).items() if value is not None]
        )
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "X-ACCESS": "ANONYMOUS",
                "User-Agent": "hebei-public-catalog-audit/1.0",
            },
            method="GET",
        )
        return self._execute(request, url)

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> FetchResult:
        query = urllib.parse.urlencode(
            [(key, str(value)) for key, value in (params or {}).items() if value is not None]
        )
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "X-ACCESS": "ANONYMOUS",
                "User-Agent": "hebei-public-catalog-audit/1.0",
            },
            method="POST",
        )
        result = self._execute(request, url)
        result.method = "POST"
        result.request_body_sha256 = sha256_bytes(body)
        return result

    def _execute(self, request: urllib.request.Request, url: str) -> FetchResult:
        for attempt in range(self.retries + 1):
            self._wait()
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
                    self.last_request = time.monotonic()
                    return FetchResult(
                        url=url,
                        fetched_at=iso_now(),
                        status=response.status,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        body=body,
                        method=request.get_method(),
                    )
            except urllib.error.HTTPError as error:
                self.last_request = time.monotonic()
                if error.code not in {429, 500, 502, 503, 504} or attempt >= self.retries:
                    raise
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else (2**attempt + random.random())
                time.sleep(min(delay, 60.0))
            except (urllib.error.URLError, TimeoutError):
                self.last_request = time.monotonic()
                if attempt >= self.retries:
                    raise
                time.sleep(min(2**attempt + random.random(), 60.0))
        raise RuntimeError("unreachable")


class RunWriter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.records: list[dict[str, Any]] = []

    def save(self, relative_path: str, result: FetchResult) -> Any:
        path = self.root / "raw" / relative_path
        atomic_write(path, result.body)
        self.records.append(
            {
                "path": str(path.relative_to(self.root)),
                "url": result.url,
                "method": result.method,
                "request_body_sha256": result.request_body_sha256,
                "fetched_at": result.fetched_at,
                "http_status": result.status,
                "content_type": result.headers.get("content-type"),
                "content_length_header": result.headers.get("content-length"),
                "last_modified": result.headers.get("last-modified"),
                "etag": result.headers.get("etag"),
                "size_bytes": len(result.body),
                "sha256": result.sha256,
            }
        )
        return json.loads(result.body)


def flatten_regions(items: Iterable[dict[str, Any]]) -> dict[str, dict[str, str | None]]:
    result: dict[str, dict[str, str | None]] = {}

    def visit(item: dict[str, Any], province: str | None, city: str | None) -> None:
        level = str(item.get("level") or "")
        title = item.get("title")
        current_province = title if level == "1" else province
        current_city = title if level == "2" else city
        result[str(item.get("key"))] = {
            "region_name": title,
            "province": current_province,
            "city": current_city,
            "county": title if level == "3" else None,
            "region_level": level,
        }
        for child in item.get("children") or []:
            visit(child, current_province, current_city)

    for root in items:
        visit(root, None, None)
    return result


def dictionary_map(payload: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("key")): str(item.get("value") or item.get("title") or "")
        for item in payload.get("content", [])
        if item.get("key") is not None
    }


def fetch_pages(
    client: PublicClient,
    writer: RunWriter,
    *,
    path: str,
    name: str,
    base_params: dict[str, Any],
    page_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected_total: int | None = None
    expected_pages: int | None = None
    page = 1
    while expected_pages is None or page <= expected_pages:
        params = dict(base_params)
        params.update({"index": page, "size": page_size})
        result = client.get(path, params)
        payload = writer.save(f"{name}/page-{page:04d}.json", result)
        content = payload.get("content") or []
        rows.extend(content)
        page_total = int(payload.get("totalElements", len(content)))
        page_count = int(payload.get("totalPages", 1))
        if expected_total is None:
            expected_total = page_total
            expected_pages = page_count
        elif page_total != expected_total or page_count != expected_pages:
            raise RuntimeError(
                f"{name} changed during collection: "
                f"expected {expected_total}/{expected_pages}, got {page_total}/{page_count}"
            )
        print(
            f"{name}: page {page}/{expected_pages}, rows {len(rows)}/{expected_total}",
            file=sys.stderr,
            flush=True,
        )
        page += 1
    if expected_total is None or len(rows) != expected_total:
        raise RuntimeError(f"{name}: expected {expected_total} rows but collected {len(rows)}")
    unique_by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    conflicting_duplicate_ids: set[str] = set()
    for row in rows:
        identifier = row.get("id")
        if not identifier:
            raise RuntimeError(f"{name}: row without id")
        key = str(identifier)
        if key in unique_by_id:
            duplicate_ids.add(key)
            if row != unique_by_id[key]:
                conflicting_duplicate_ids.add(key)
        else:
            unique_by_id[key] = row
    if conflicting_duplicate_ids:
        raise RuntimeError(
            f"{name}: conflicting duplicate ids: {sorted(conflicting_duplicate_ids)}"
        )
    unique_rows = list(unique_by_id.values())
    return unique_rows, {
        "source_reported_row_count": expected_total,
        "raw_row_count": len(rows),
        "unique_id_count": len(unique_rows),
        "exact_duplicate_row_count": len(rows) - len(unique_rows),
        "duplicate_id_count": len(duplicate_ids),
        "duplicate_ids": sorted(duplicate_ids),
        "conflicting_duplicate_id_count": 0,
        "page_count": expected_pages,
        "page_size": page_size,
    }


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def match_terms(texts: Iterable[str], terms: Iterable[str]) -> list[str]:
    haystack = "\n".join(value for value in texts if value)
    return sorted({term for term in terms if term.lower() in haystack.lower()})


def derive_tables(
    root: Path,
    *,
    regions: list[dict[str, Any]],
    dictionaries: dict[str, dict[str, Any]],
    enterprises: list[dict[str, Any]],
    ports: list[dict[str, Any]],
    enterprise_audit: dict[str, Any],
    port_audit: dict[str, Any],
) -> dict[str, Any]:
    derived = root / "derived"
    region_by_id = flatten_regions(regions)
    industry_by_id = dictionary_map(dictionaries["regulation_industry"])
    ps_type_by_id = dictionary_map(dictionaries["ps_type"])
    monitor_type_by_id = dictionary_map(dictionaries["monitor_type"])
    port_type_by_id = dictionary_map(dictionaries["port_type"])
    enterprise_by_id = {str(row["id"]): row for row in enterprises}

    enterprise_rows: list[dict[str, Any]] = []
    for row in enterprises:
        region = region_by_id.get(str(row.get("regionId")), {})
        monitor_ids = str(row.get("monitorTypeId") or "").split(",")
        enterprise_rows.append(
            {
                "enterprise_public_id": row.get("id"),
                "enterprise_name_public": row.get("psName"),
                "enable": row.get("enable"),
                "province": region.get("province"),
                "city": region.get("city"),
                "county": region.get("county"),
                "region_id": row.get("regionId"),
                "regulation_industry_id": row.get("regulationIndustryId"),
                "regulation_industry_name": industry_by_id.get(
                    str(row.get("regulationIndustryId")), ""
                ),
                "ps_type_id": row.get("psTypeId"),
                "ps_type_name": ps_type_by_id.get(str(row.get("psTypeId")), ""),
                "monitor_type_ids": row.get("monitorTypeId"),
                "monitor_type_names": "|".join(
                    monitor_type_by_id.get(value, value) for value in monitor_ids if value
                ),
                "ps_state": row.get("psState"),
                "is_rubbish": row.get("isRubbish"),
            }
        )
    enterprise_fields = list(enterprise_rows[0]) if enterprise_rows else []
    write_csv(derived / "enterprises.csv", enterprise_fields, enterprise_rows)

    port_rows: list[dict[str, Any]] = []
    orphan_ports = 0
    for row in ports:
        ps = enterprise_by_id.get(str(row.get("psId")))
        if ps is None:
            orphan_ports += 1
        region = region_by_id.get(str((ps or {}).get("regionId")), {})
        item = {field: row.get(field) for field in PORT_EXPORT_FIELDS}
        item.update(
            {
                "enterprise_name_public": (ps or {}).get("psName"),
                "province": region.get("province"),
                "city": region.get("city"),
                "county": region.get("county"),
                "port_type_name": port_type_by_id.get(str(row.get("portTypeId")), ""),
            }
        )
        port_rows.append(item)
    port_fields = list(port_rows[0]) if port_rows else []
    write_csv(derived / "ports.csv", port_fields, port_rows)

    hit_rows: list[dict[str, Any]] = []
    hit_counts: Counter[str] = Counter()
    enterprise_hit_counts: Counter[str] = Counter()
    port_hit_counts: Counter[str] = Counter()
    ps_ids_with_point_hit: defaultdict[str, set[str]] = defaultdict(set)

    for candidate_id, terms in CANDIDATE_TERMS.items():
        for ps in enterprises:
            matches = match_terms(
                [
                    str(ps.get("psName") or ""),
                    industry_by_id.get(str(ps.get("regulationIndustryId")), ""),
                ],
                terms,
            )
            if matches:
                region = region_by_id.get(str(ps.get("regionId")), {})
                hit_rows.append(
                    {
                        "candidate_id": candidate_id,
                        "hit_scope": "enterprise_or_industry_name",
                        "enterprise_public_id": ps.get("id"),
                        "enterprise_name_public": ps.get("psName"),
                        "city": region.get("city"),
                        "county": region.get("county"),
                        "port_id": "",
                        "port_name": "",
                        "port_type_id": "",
                        "port_type_name": "",
                        "matched_terms": "|".join(matches),
                        "matched_fields": "psName|regulationIndustryName",
                        "mapping_status": "discovery_only_unverified",
                    }
                )
                enterprise_hit_counts[candidate_id] += 1

        for port in ports:
            texts = [str(port.get(field) or "") for field in PORT_TEXT_FIELDS]
            matches = match_terms(texts, terms)
            if not matches:
                continue
            ps = enterprise_by_id.get(str(port.get("psId")), {})
            region = region_by_id.get(str(ps.get("regionId")), {})
            matched_fields = [
                field
                for field in PORT_TEXT_FIELDS
                if match_terms([str(port.get(field) or "")], terms)
            ]
            hit_rows.append(
                {
                    "candidate_id": candidate_id,
                    "hit_scope": "monitoring_point_or_process_field",
                    "enterprise_public_id": port.get("psId"),
                    "enterprise_name_public": ps.get("psName"),
                    "city": region.get("city"),
                    "county": region.get("county"),
                    "port_id": port.get("id"),
                    "port_name": port.get("portName"),
                    "port_type_id": port.get("portTypeId"),
                    "port_type_name": port_type_by_id.get(str(port.get("portTypeId")), ""),
                    "matched_terms": "|".join(matches),
                    "matched_fields": "|".join(matched_fields),
                    "mapping_status": "discovery_only_unverified",
                }
            )
            port_hit_counts[candidate_id] += 1
            ps_ids_with_point_hit[candidate_id].add(str(port.get("psId")))

    hit_rows.sort(
        key=lambda row: (
            str(row["candidate_id"]),
            str(row["hit_scope"]),
            str(row["enterprise_name_public"]),
            str(row["port_name"]),
        )
    )
    hit_fields = list(hit_rows[0]) if hit_rows else []
    write_csv(derived / "candidate_discovery_hits.csv", hit_fields, hit_rows)

    for candidate_id in CANDIDATE_TERMS:
        hit_counts[candidate_id] = enterprise_hit_counts[candidate_id] + port_hit_counts[candidate_id]

    ports_by_type = Counter(str(row.get("portTypeId") or "unknown") for row in ports)
    populated_port_fields = {
        field: sum(row.get(field) not in {None, ""} for row in ports)
        for field in PORT_EXPORT_FIELDS
    }
    joined_ps_ids = {
        str(row.get("psId"))
        for row in ports
        if row.get("psId") and str(row.get("psId")) in enterprise_by_id
    }
    orphan_ps_ids = {
        str(row.get("psId"))
        for row in ports
        if row.get("psId") and str(row.get("psId")) not in enterprise_by_id
    }
    enterprises_with_ports = len(joined_ps_ids)
    summary = {
        "derived_at": iso_now(),
        "source_role": "public_platform_catalog_not_internal_cems",
        "enterprise_count": len(enterprises),
        "port_count": len(ports),
        "source_reported_enterprise_rows": enterprise_audit["source_reported_row_count"],
        "source_reported_port_rows": port_audit["source_reported_row_count"],
        "exact_duplicate_port_rows": port_audit["exact_duplicate_row_count"],
        "duplicate_port_ids": port_audit["duplicate_ids"],
        "enterprises_with_enabled_ports": enterprises_with_ports,
        "enabled_enterprises_without_enabled_port_in_catalog": len(enterprises) - enterprises_with_ports,
        "orphan_ports_not_joined_to_enabled_enterprise": orphan_ports,
        "orphan_enterprise_ids_referenced_by_enabled_ports": len(orphan_ps_ids),
        "ports_by_type": {
            key: {"name": port_type_by_id.get(key, ""), "count": count}
            for key, count in sorted(ports_by_type.items())
        },
        "populated_port_fields": populated_port_fields,
        "candidate_discovery": {
            candidate_id: {
                "enterprise_or_industry_name_hits": enterprise_hit_counts[candidate_id],
                "monitoring_point_or_process_field_hits": port_hit_counts[candidate_id],
                "enterprises_with_point_hits": len(ps_ids_with_point_hit[candidate_id]),
                "total_hit_rows": hit_counts[candidate_id],
            }
            for candidate_id in CANDIDATE_TERMS
        },
        "limitations": [
            "Public names and identifiers are retained exactly as published; they are not internal anonymous IDs.",
            "A term hit is discovery evidence only and does not establish product, core facility, capacity or outlet topology.",
            "The public catalog does not by itself establish first-visible lag, revision behavior or internal/public identity.",
            "No monitoring values were downloaded by this catalog command.",
        ],
    }
    write_json(derived / "summary.json", summary)
    return summary


def summary_markdown(summary: dict[str, Any], run_id: str) -> str:
    lines = [
        f"# 河北公开污染源目录审计：{run_id}",
        "",
        f"> 生成：{summary['derived_at']}",
        "> 性质：公开平台目录发现，不是内部 `INT-CEMS` 元数据交付，也不证明 `G2/G3`。",
        "",
        "## 完整性计数",
        "",
        "| 项目 | 计数 |",
        "| --- | ---: |",
        f"| 启用企业 | {summary['enterprise_count']} |",
        f"| 接口声明的启用监测点行 | {summary['source_reported_port_rows']} |",
        f"| 去除完全相同重复行后的唯一启用监测点 ID | {summary['port_count']} |",
        f"| 完全相同的重复监测点行 | {summary['exact_duplicate_port_rows']} |",
        f"| 至少有一个启用监测点的启用企业 | {summary['enterprises_with_enabled_ports']} |",
        f"| 未在启用监测点目录中出现的启用企业 | {summary['enabled_enterprises_without_enabled_port_in_catalog']} |",
        f"| 无法连接到启用企业目录的监测点 | {summary['orphan_ports_not_joined_to_enabled_enterprise']} |",
        f"| 上述孤立点位涉及的非启用/缺失企业 ID | {summary['orphan_enterprise_ids_referenced_by_enabled_ports']} |",
        "",
        "## 候选检索词命中",
        "",
        "| 候选 | 企业/行业名命中 | 监测点/工序字段命中 | 有点位命中的企业 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for candidate_id, counts in summary["candidate_discovery"].items():
        lines.append(
            f"| `{candidate_id}` | {counts['enterprise_or_industry_name_hits']} | "
            f"{counts['monitoring_point_or_process_field_hits']} | "
            f"{counts['enterprises_with_point_hits']} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 命中只说明公开目录中存在相应文字，不说明监测点能唯一绑定指定产品的核心设备；",
            "- 公开目录 ID 不能代替内部稳定匿名 ID，也没有生产线—设施—排口共享拓扑；",
            "- 本轮没有下载小时数值，不能据此判断更新时延、修订行为或状态可识别性；",
            "- 原始响应逐页保存并在 `manifest.json` 中记录 URL、查询时间、响应头和 SHA-256。",
            "",
        ]
    )
    return "\n".join(lines)


def collect_catalog(args: argparse.Namespace) -> int:
    output = args.output or Path("option/data/runs") / compact_now()
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty run directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    started_at = iso_now()
    client = PublicClient(
        args.base_url,
        verify_tls=args.verify_tls,
        use_env_proxy=args.use_env_proxy,
        timeout=args.timeout,
        min_interval=args.min_interval,
        retries=args.retries,
    )
    writer = RunWriter(output)

    regions_result = client.get("/online_system/v5/regions/tree", {"id": "130000000"})
    regions = writer.save("regions.json", regions_result)

    dictionaries: dict[str, dict[str, Any]] = {}
    for name, params in DICTIONARIES.items():
        result = client.get("/online_system/v5/dictionary", params)
        dictionaries[name] = writer.save(f"dictionary-{name}.json", result)

    enterprises, enterprise_audit = fetch_pages(
        client,
        writer,
        path="/online_base/v5/psInfo",
        name="enterprises",
        base_params={"enable": "1", "fields": PS_FIELDS, "sort": "+id"},
        page_size=args.page_size,
    )
    ports, port_audit = fetch_pages(
        client,
        writer,
        path="/online_base/v5/portInfo",
        name="ports",
        base_params={"enable": "1", "fields": PORT_FIELDS, "sort": "+id"},
        page_size=args.page_size,
    )

    summary = derive_tables(
        output,
        regions=regions,
        dictionaries=dictionaries,
        enterprises=enterprises,
        ports=ports,
        enterprise_audit=enterprise_audit,
        port_audit=port_audit,
    )
    finished_at = iso_now()
    manifest = {
        "schema_version": "ps-public-catalog-manifest-v1",
        "run_id": output.name,
        "started_at": started_at,
        "finished_at": finished_at,
        "base_url": args.base_url,
        "tls_verification": args.verify_tls,
        "environment_proxy_used": args.use_env_proxy,
        "request_min_interval_seconds": args.min_interval,
        "request_timeout_seconds": args.timeout,
        "enterprise_pagination": enterprise_audit,
        "port_pagination": port_audit,
        "files": writer.records,
    }
    write_json(output / "manifest.json", manifest)
    atomic_write(
        output / "SUMMARY.md",
        summary_markdown(summary, output.name).encode("utf-8"),
    )
    print(output)
    return 0


def verify_run(args: argparse.Namespace) -> int:
    root = Path(args.run_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    failures = []
    for record in manifest.get("files", []):
        path = root / record["path"]
        if not path.exists():
            failures.append(f"missing: {record['path']}")
            continue
        actual = sha256_bytes(path.read_bytes())
        if actual != record["sha256"]:
            failures.append(f"hash mismatch: {record['path']}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"verified {len(manifest.get('files', []))} raw files")
    return 0


def flatten_columns(
    columns: Iterable[dict[str, Any]],
    *,
    path: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in columns:
        name = str(item.get("name") or "")
        current_path = path + (name,)
        children = item.get("children") or []
        result.append(
            {
                "id": item.get("id"),
                "name": name,
                "path": " > ".join(current_path),
                "pollutant_code": item.get("pollutantCode"),
                "checked": bool(item.get("checked")),
                "disabled": bool(item.get("disabled")),
                "info": item.get("info"),
                "is_leaf": not bool(children),
            }
        )
        if children:
            result.extend(flatten_columns(children, path=current_path))
    return result


def data_row_summary(data_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    template_times: list[str] = []
    numeric_times: list[str] = []
    for row in data_rows:
        measured_at = row.get("time")
        if measured_at:
            template_times.append(str(measured_at))
        has_numeric = False
        for key, value in row.items():
            if key == "time" or isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                has_numeric = True
                break
            normalized = str(value).split("_", 1)[0].strip()
            if normalized in {"", "-", "--"}:
                continue
            try:
                float(normalized)
                has_numeric = True
                break
            except ValueError:
                continue
        if has_numeric and measured_at:
            numeric_times.append(str(measured_at))
    template_times.sort()
    numeric_times.sort()
    return {
        "response_template_row_count": len(template_times),
        "earliest_template_row_time": template_times[0] if template_times else None,
        "latest_template_row_time": template_times[-1] if template_times else None,
        "rows_with_numeric_measurement": len(numeric_times),
        "earliest_numeric_measurement_time": numeric_times[0] if numeric_times else None,
        "latest_numeric_measurement_time": numeric_times[-1] if numeric_times else None,
    }


def collect_snapshot(args: argparse.Namespace) -> int:
    today = datetime.now(SHANGHAI).strftime("%Y-%m-%d")
    if args.date and (args.start_date or args.end_date):
        raise SystemExit("use either --date or --start-date/--end-date, not both")
    if args.end_date and not args.start_date:
        raise SystemExit("--end-date requires --start-date")
    start_date = args.start_date or args.date or today
    end_date = args.end_date or start_date
    try:
        start_day = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_day = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit("dates must use YYYY-MM-DD") from exc
    if end_day < start_day:
        raise SystemExit("end date must not precede start date")
    window_days = (end_day - start_day).days + 1

    output = args.output or Path("option/data/t026") / compact_now()
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty snapshot directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    client = PublicClient(
        args.base_url,
        verify_tls=args.verify_tls,
        use_env_proxy=args.use_env_proxy,
        timeout=args.timeout,
        min_interval=args.min_interval,
        retries=args.retries,
    )
    writer = RunWriter(output)
    with Path(args.points_csv).open("r", encoding="utf-8-sig", newline="") as handle:
        points = [row for row in csv.DictReader(handle) if row.get("enabled") == "1"]
    if not points:
        raise SystemExit("no enabled=1 rows in points CSV")

    field_rows: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for index, point in enumerate(points, start=1):
        point_key = f"{point['candidate_id']}-{point['port_id']}"
        common = {
            "psId": point["ps_id"],
            "portTypeId": point["port_type_id"],
            "portId": point["port_id"],
            "dataType": point.get("data_type") or "2061",
        }
        column_result = client.get("/online_statistics/v5/dataQuery/column", common)
        columns = writer.save(f"{point_key}/columns.json", column_result)
        flattened = flatten_columns(columns if isinstance(columns, list) else [])
        checked_headers = [
            str(item["id"])
            for item in flattened
            if item["checked"] and item["id"] is not None
        ]
        for item in flattened:
            item.update(
                {
                    "candidate_id": point["candidate_id"],
                    "ps_id": point["ps_id"],
                    "ps_name": point["ps_name"],
                    "port_id": point["port_id"],
                    "port_name": point["port_name"],
                    "port_type_id": point["port_type_id"],
                    "data_type": common["dataType"],
                }
            )
            field_rows.append(item)

        request_payload = {
            "index": 1,
            "size": args.page_size,
            **common,
            "startTime": f"{start_date} 00:00:00",
            "endTime": f"{end_date} 23:00:00",
            "headers": ",".join(checked_headers),
        }
        data_result = client.post_json(
            "/online_statistics/v5/dataQuery/list", request_payload
        )
        data_payload = writer.save(f"{point_key}/data.json", data_result)
        data_rows = data_payload.get("data") or [] if isinstance(data_payload, dict) else []
        row_summary = data_row_summary(row for row in data_rows if isinstance(row, dict))
        observations.append(
            {
                "candidate_id": point["candidate_id"],
                "ps_id": point["ps_id"],
                "ps_name": point["ps_name"],
                "port_id": point["port_id"],
                "port_name": point["port_name"],
                "port_type_id": point["port_type_id"],
                "data_type": common["dataType"],
                "measurement_date": (
                    start_date if start_date == end_date else f"{start_date}/{end_date}"
                ),
                "measurement_start_date": start_date,
                "measurement_end_date": end_date,
                "measurement_window_days": window_days,
                "Tseen_public": data_result.fetched_at,
                "Tavailable_public": "unknown_single_poll",
                "row_count_in_response": len(data_rows),
                "server_count": data_payload.get("count") if isinstance(data_payload, dict) else None,
                **row_summary,
                "checked_header_count": len(checked_headers),
                "column_response_sha256": column_result.sha256,
                "data_response_sha256": data_result.sha256,
                "request_body_sha256": data_result.request_body_sha256,
                "internal_point_id": point.get("internal_point_id") or "",
                "unique_mapping_status": point.get("unique_mapping_status") or "",
            }
        )
        print(
            f"snapshot: point {index}/{len(points)} {point['candidate_id']} "
            f"rows={len(data_rows)} fields={len(checked_headers)}",
            file=sys.stderr,
            flush=True,
        )

    fieldnames = [
        "candidate_id",
        "ps_id",
        "ps_name",
        "port_id",
        "port_name",
        "port_type_id",
        "data_type",
        "id",
        "name",
        "path",
        "pollutant_code",
        "checked",
        "disabled",
        "info",
        "is_leaf",
    ]
    write_csv(output / "field_dictionary.csv", fieldnames, field_rows)
    observation_fields = list(observations[0]) if observations else []
    write_csv(output / "observations.csv", observation_fields, observations)
    manifest = {
        "schema_version": "ps-public-snapshot-v2",
        "study_id": args.study_id,
        "run_id": output.name,
        "finished_at": iso_now(),
        "base_url": args.base_url,
        "tls_verification": args.verify_tls,
        "environment_proxy_used": args.use_env_proxy,
        "measurement_date": (
            start_date if start_date == end_date else f"{start_date}/{end_date}"
        ),
        "measurement_start_date": start_date,
        "measurement_end_date": end_date,
        "measurement_window_days": window_days,
        "points_csv": str(args.points_csv),
        "observations": observations,
        "files": writer.records,
        "interpretation": (
            "A bounded current-view public-source poll. A historical date window "
            "can test returned field shape and internal patterns, but cannot by "
            "itself establish historical first-available time or revision behavior. "
            "No snapshot establishes production state, capacity, market materiality "
            "or information advantage."
        ),
    }
    write_json(output / "manifest.json", manifest)
    print(output)
    return 0


def rebuild_snapshot_summary(args: argparse.Namespace) -> int:
    root = Path(args.snapshot_dir)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    observations = manifest.get("observations") or []
    for observation in observations:
        point_key = f"{observation['candidate_id']}-{observation['port_id']}"
        data_path = root / "raw" / point_key / "data.json"
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        rows = payload.get("data") or []
        observation.pop("earliest_measurement_time", None)
        observation.pop("latest_measurement_time", None)
        observation.update(data_row_summary(row for row in rows if isinstance(row, dict)))
    if observations:
        write_csv(root / "observations.csv", list(observations[0]), observations)
    manifest["observations"] = observations
    manifest["derived_summary_rebuilt_at"] = iso_now()
    write_json(manifest_path, manifest)
    print(root)
    return 0


def rebuild_run(args: argparse.Namespace) -> int:
    root = Path(args.run_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    def load_json(relative_path: str) -> Any:
        return json.loads((root / "raw" / relative_path).read_text(encoding="utf-8"))

    def load_pages(name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted((root / "raw" / name).glob("page-*.json")):
            rows.extend(json.loads(path.read_text(encoding="utf-8")).get("content") or [])
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("id"))
            if key in unique and row != unique[key]:
                raise RuntimeError(f"{name}: conflicting local rows for id {key}")
            unique[key] = row
        return list(unique.values())

    regions = load_json("regions.json")
    dictionaries = {
        name: load_json(f"dictionary-{name}.json") for name in DICTIONARIES
    }
    enterprises = load_pages("enterprises")
    ports = load_pages("ports")
    summary = derive_tables(
        root,
        regions=regions,
        dictionaries=dictionaries,
        enterprises=enterprises,
        ports=ports,
        enterprise_audit=manifest["enterprise_pagination"],
        port_audit=manifest["port_pagination"],
    )
    atomic_write(root / "SUMMARY.md", summary_markdown(summary, root.name).encode("utf-8"))
    print(root)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser("catalog", help="collect enabled enterprises and ports")
    catalog.add_argument("--base-url", default=DEFAULT_BASE_URL)
    catalog.add_argument("--output", type=Path)
    catalog.add_argument("--page-size", type=int, default=1000)
    catalog.add_argument("--min-interval", type=float, default=1.0)
    catalog.add_argument("--timeout", type=float, default=60.0)
    catalog.add_argument("--retries", type=int, default=4)
    catalog.add_argument(
        "--verify-tls",
        action="store_true",
        help="verify the TLS chain and hostname (the provided IP endpoint may not pass)",
    )
    catalog.add_argument(
        "--use-env-proxy",
        action="store_true",
        help="honor HTTP(S)_PROXY from the environment (direct connection is the default)",
    )
    catalog.set_defaults(func=collect_catalog)

    verify = subparsers.add_parser("verify", help="verify raw response hashes for a run")
    verify.add_argument("run_dir", type=Path)
    verify.set_defaults(func=verify_run)

    rebuild = subparsers.add_parser("rebuild", help="rebuild derived tables from saved raw pages")
    rebuild.add_argument("run_dir", type=Path)
    rebuild.set_defaults(func=rebuild_run)

    snapshot = subparsers.add_parser(
        "snapshot", help="save one public-source poll for selected study points"
    )
    snapshot.add_argument("points_csv", type=Path)
    snapshot.add_argument("--study-id", default="legacy-t026-public-pilot")
    snapshot.add_argument("--date", help="one measurement date in YYYY-MM-DD")
    snapshot.add_argument("--start-date", help="inclusive range start in YYYY-MM-DD")
    snapshot.add_argument("--end-date", help="inclusive range end in YYYY-MM-DD")
    snapshot.add_argument("--base-url", default=DEFAULT_BASE_URL)
    snapshot.add_argument("--output", type=Path)
    snapshot.add_argument("--page-size", type=int, default=1000)
    snapshot.add_argument("--min-interval", type=float, default=1.0)
    snapshot.add_argument("--timeout", type=float, default=120.0)
    snapshot.add_argument("--retries", type=int, default=4)
    snapshot.add_argument("--verify-tls", action="store_true")
    snapshot.add_argument("--use-env-proxy", action="store_true")
    snapshot.set_defaults(func=collect_snapshot)

    snapshot_rebuild = subparsers.add_parser(
        "snapshot-rebuild", help="rebuild snapshot observation summaries from saved raw responses"
    )
    snapshot_rebuild.add_argument("snapshot_dir", type=Path)
    snapshot_rebuild.set_defaults(func=rebuild_snapshot_summary)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
