"""观测记录业务规则：状态流转、字段校验、成批导入与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "observation"
REQUIRED_FIELDS = ["记录编号", "所属站点", "观测要素"]
STATUS_ORDER = ["待质控", "质控通过", "疑误标记", "已作废"]
ACTION_RULES = {"提交质控": "质控通过", "标记疑误": "疑误标记", "作废记录": "已作废"}
NEGATIVE_ACTIONS = ["作废记录"]

# 成批导入固定按这套表头识别列；记录编号可留空，由系统补号。
IMPORT_COLUMNS = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位"]
IMPORT_REQUIRED = ["所属站点", "观测要素", "观测时刻", "观测数值"]
TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
]
NUMBER_PATTERN = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


def _parse_time(raw: str) -> str | None:
    """把观测时刻归一成 YYYY-MM-DD HH:MM:SS；解析不了返回 None。"""
    text = raw.strip()
    for pattern in TIME_FORMATS:
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _parse_number(raw: str) -> int | float | None:
    """观测数值必须是有限数字；科学计数法、小数、正负号都接受。"""
    text = raw.strip()
    if not NUMBER_PATTERN.match(text):
        return None
    value = float(text)
    if not value == value or value in (float("inf"), float("-inf")):
        return None
    return int(value) if value.is_integer() else value


class ObservationService:
    def _filtered(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        element: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
        if station:
            rows = [row for row in rows if station in str(row.get("所属站点", ""))]
        if element:
            rows = [row for row in rows if element in str(row.get("观测要素", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        element: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered(keyword=keyword, station=station, element=element, status=status)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summarize(
        self,
        *,
        keyword: str | None = None,
        station: str | None = None,
        element: str | None = None,
        status: str | None = None,
    ) -> dict[str, int]:
        """按当前筛选条件统计总条数与各质控状态条数，供页面卡片核对。"""
        rows = self._filtered(keyword=keyword, station=station, element=element, status=status)
        return {
            "total": len(rows),
            "pending": sum(1 for row in rows if row.get("status") == "待质控"),
            "suspicious": sum(1 for row in rows if row.get("status") == "疑误标记"),
            "passed": sum(1 for row in rows if row.get("status") == "质控通过"),
            "discarded": sum(1 for row in rows if row.get("status") == "已作废"),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def import_rows(self, content: str) -> dict[str, Any]:
        """成批导入观测记录：逐行校验、逐行落库，单行失败不影响其它行。

        同一站点、同一要素、同一时刻的记录文件内与库内都只保留一条；
        返回每一行的成功/失败/重复结果与原因，并按站点分组汇总。
        """
        reader = csv.reader(io.StringIO(content.lstrip("\ufeff")))
        header_row = next(reader, None)
        if header_row is None or not any(cell.strip() for cell in header_row):
            raise ValueError("导入文件为空，请按模板填写后再上传")
        header = [cell.strip() for cell in header_row]
        missing_columns = [name for name in IMPORT_REQUIRED if name not in header]
        if missing_columns:
            raise ValueError(
                "表头缺少必要列：" + "、".join(missing_columns)
                + f"；标准表头为：{','.join(IMPORT_COLUMNS)}"
            )
        index = {name: header.index(name) for name in header if name}

        def cell(row: list[str], name: str) -> str:
            pos = index.get(name)
            if pos is None or pos >= len(row):
                return ""
            return row[pos].strip()

        rows = store.rows(MODULE)
        existing_keys = {self._dedupe_key(row) for row in rows}
        existing_codes = {str(row.get("记录编号", "")).strip() for row in rows if row.get("记录编号")}
        seen_keys: set[tuple[str, str, str]] = set()
        seen_codes: set[str] = set()

        results: list[dict[str, Any]] = []
        groups: dict[str, dict[str, int]] = {}
        counters = {"success": 0, "failed": 0, "duplicated": 0}
        line_no = 1  # 表头占第 1 行

        for raw_row in reader:
            line_no += 1
            if not raw_row or not any(cell.strip() for cell in raw_row):
                continue  # 空行不计入结果
            values = {name: cell(raw_row, name) for name in IMPORT_COLUMNS}
            station = values["所属站点"]
            group = groups.setdefault(station, {"success": 0, "failed": 0, "duplicated": 0})

            reasons: list[str] = []
            missing = [name for name in IMPORT_REQUIRED if not values[name]]
            if missing:
                reasons.append("缺少必填字段：" + "、".join(missing))

            number_value: int | float | None = None
            if values["观测数值"]:
                number_value = _parse_number(values["观测数值"])
                if number_value is None:
                    reasons.append(f"观测数值「{values['观测数值']}」不是数字")

            observed_at = ""
            if values["观测时刻"]:
                observed_at = _parse_time(values["观测时刻"]) or ""
                if not observed_at:
                    reasons.append(
                        f"观测时刻「{values['观测时刻']}」格式不对，应为 YYYY-MM-DD HH:MM:SS"
                    )

            code = values["记录编号"]

            # 字段本身不合格的行直接判失败，不再参与去重，避免错误数据互相吞掉。
            if reasons:
                counters["failed"] += 1
                group["failed"] += 1
                results.append({
                    "line": line_no,
                    "ok": False,
                    "duplicated": False,
                    "reason": "；".join(reasons),
                    "values": values,
                })
                continue

            # 站点+要素+时刻相同就是重复记录（哪怕记录编号也照抄了一份），只保留一条；
            # 三要素不同却撞了记录编号，才是真正的编号冲突，按失败处理。
            dedupe_key = (station, values["观测要素"], observed_at)
            if dedupe_key in seen_keys or dedupe_key in existing_keys:
                counters["duplicated"] += 1
                group["duplicated"] += 1
                first_line = self._first_line(results, dedupe_key)
                tail = f"，与第 {first_line} 行内容重复" if first_line else "，库内已有同一时刻记录"
                results.append({
                    "line": line_no,
                    "ok": True,
                    "duplicated": True,
                    "reason": "同一站点同一要素同一时刻的重复记录只保留一条" + tail,
                    "values": values,
                })
                continue

            if code and (code in existing_codes or code in seen_codes):
                counters["failed"] += 1
                group["failed"] += 1
                results.append({
                    "line": line_no,
                    "ok": False,
                    "duplicated": False,
                    "reason": f"记录编号「{code}」已被其它站点或要素的记录占用",
                    "values": values,
                })
                continue

            entry_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
            if not code:
                code = f"OBSE-{entry_id:04d}"
            entry = {
                "id": entry_id,
                "status": "待质控",
                "pending": True,
                "abnormal": False,
                "记录编号": code,
                "所属站点": station,
                "观测要素": values["观测要素"],
                "观测时刻": observed_at,
                "观测数值": number_value,
                "数值单位": values["数值单位"],
                "质控标识": "待质控",
                "记录状态": "待质控",
            }
            rows.append(entry)
            seen_keys.add(dedupe_key)
            seen_codes.add(code)
            counters["success"] += 1
            group["success"] += 1
            results.append({
                "line": line_no,
                "ok": True,
                "duplicated": False,
                "reason": "导入成功",
                "entry": entry,
                "values": values,
            })

        group_rows = [
            {"station": station, **counts}
            for station, counts in sorted(groups.items(), key=lambda item: item[0])
        ]
        message = (
            f"导入完成：成功 {counters['success']} 条，"
            f"失败 {counters['failed']} 条，重复跳过 {counters['duplicated']} 条"
        )
        return {
            "ok": True,
            "message": message,
            "total": sum(counters.values()),
            **counters,
            "groups": group_rows,
            "results": results,
        }

    @staticmethod
    def _dedupe_key(row: dict[str, Any]) -> tuple[str, str, str]:
        raw_time = str(row.get("观测时刻", "") or "").strip()
        observed_at = _parse_time(raw_time) or raw_time
        return (
            str(row.get("所属站点", "") or "").strip(),
            str(row.get("观测要素", "") or "").strip(),
            observed_at,
        )

    @staticmethod
    def _first_line(results: list[dict[str, Any]], key: tuple[str, str, str]) -> int | None:
        for item in results:
            entry = item.get("entry")
            if not entry:
                continue
            if (
                entry.get("所属站点") == key[0]
                and entry.get("观测要素") == key[1]
                and entry.get("观测时刻") == key[2]
            ):
                return int(item["line"])
        return None

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"观测记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        # 质控标识与记录状态两个展示列跟着状态流转同步，列表刷新后保持一致。
        entry["质控标识"] = target
        entry["记录状态"] = target
        return entry, f"观测记录已{action}"
