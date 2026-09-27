"""观测记录批量导入的端到端校验：部分失败、去重、统计核对与导出列。"""
from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import SEED_ROWS
from app.store import store

client = TestClient(app)

HEADER = "所属站点,观测要素,观测时刻,观测数值,数值单位"


@pytest.fixture(autouse=True)
def reset_observation_table():
    """每个用例都从干净的种子数据出发，避免互相影响。"""
    rows = store.rows("observation")
    rows.clear()
    rows.extend(dict(row) for row in SEED_ROWS["observation"])
    yield


def upload(csv_text: str):
    return client.post(
        "/api/observation/import",
        files={"file": ("observations.csv", csv_text.encode("utf-8"), "text/csv")},
    )


def test_import_groups_by_station_and_keeps_partial_failures():
    csv_text = "\n".join([
        HEADER,
        "甲站,气温,2026-09-27 08:00:00,23.5,℃",
        "甲站,气温,2026-09-27 09:00:00,abc,℃",          # 数值不是数字
        "乙站,降水,2026-09-27 08:00:00,12.0,mm",
        "乙站,风速,2026-13-45 08:00,3.2,m/s",            # 时刻格式不对
    ])
    before = len(store.rows("observation"))

    response = upload(csv_text)

    assert response.status_code == 200
    result = response.json()
    # 一行不合格不回滚整批：2 行写入、2 行失败
    assert result["imported"] == 2
    assert result["failed"] == 2
    assert result["total_rows"] == 4
    assert len(store.rows("observation")) == before + 2

    # 按站点分组给出计数
    groups = {group["station"]: group for group in result["stations"]}
    assert groups["甲站"]["imported"] == 1 and groups["甲站"]["failed"] == 1
    assert groups["乙站"]["imported"] == 1 and groups["乙站"]["failed"] == 1

    # 数值、时刻问题单独列出并说明差在哪
    errors = {(item["line"], item["field"]): item for item in result["format_errors"]}
    assert (3, "观测数值") in errors and "不是数字" in errors[(3, "观测数值")]["reason"]
    assert (5, "观测时刻") in errors and "格式不对" in errors[(5, "观测时刻")]["reason"]

    # 逐行结果：成功行带记录编号，失败行带原因
    by_line = {row["line"]: row for row in result["rows"]}
    assert by_line[2]["result"] == "成功" and by_line[2]["record_no"]
    assert by_line[3]["result"] == "失败" and "不是数字" in by_line[3]["reason"]
    assert by_line[5]["result"] == "失败" and "格式不对" in by_line[5]["reason"]


def test_import_deduplicates_same_station_element_moment():
    csv_text = "\n".join([
        HEADER,
        "甲站,气温,2026-09-27 08:00:00,23.5,℃",
        "甲站,气温,2026-09-27 08:00,99.9,℃",   # 归一化后同一时刻，只保留一条
    ])
    before = len(store.rows("observation"))

    first = upload(csv_text).json()
    assert first["imported"] == 1
    assert first["duplicated"] == 1
    assert len(store.rows("observation")) == before + 1

    # 再次导入同一文件：与库里已有记录重复，一条都不再写入
    second = upload(csv_text).json()
    assert second["imported"] == 0
    assert second["duplicated"] == 2
    assert len(store.rows("observation")) == before + 1


def test_stats_match_list_total_under_current_filters():
    upload("\n".join([
        HEADER,
        "核对站,气温,2026-09-27 08:00:00,23.5,℃",
        "核对站,降水,2026-09-27 09:00:00,1.2,mm",
    ]))

    listing = client.get("/api/observation", params={"station": "核对站"}).json()
    stats = client.get("/api/observation/stats", params={"station": "核对站"}).json()

    assert stats["total"] == listing["total"] == 2
    # 列表刷新后质控标识与记录状态一致
    mapping = {"待质控": "未质控", "质控通过": "合格", "疑误标记": "疑误", "已作废": "作废"}
    for item in listing["items"]:
        assert item["质控标识"] == mapping[item["记录状态"]]
    assert stats["pending"] == 2


def test_export_csv_contains_record_no_and_unit():
    upload("\n".join([
        HEADER,
        "导出站,气温,2026-09-27 08:00:00,23.5,℃",
    ]))

    response = client.get("/api/observation/export", params={"station": "导出站"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][:2] == ["记录编号", "所属站点"]
    assert "数值单位" in rows[0]
    assert len(rows) == 2  # 表头 + 1 条记录
    record = dict(zip(rows[0], rows[1]))
    assert record["记录编号"].startswith("OBSE-")
    assert record["数值单位"] == "℃"
    assert record["观测数值"] == "23.5"


def test_import_rejects_bad_file():
    empty = client.post("/api/observation/import", files={"file": ("a.csv", b"", "text/csv")})
    assert empty.status_code == 400

    no_header = upload("站点,要素\n甲站,气温")
    assert no_header.status_code == 400
    assert "缺少必需列" in no_header.json()["detail"]
