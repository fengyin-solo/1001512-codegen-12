"""观测记录业务规则：状态流转、字段校验、批量导入与筛选口径都收在这里。"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "observation"
REQUIRED_FIELDS = ["记录编号", "所属站点", "观测要素"]
STATUS_ORDER = ["待质控", "质控通过", "疑误标记", "已作废"]
ACTION_RULES = {"提交质控": "质控通过", "标记疑误": "疑误标记", "作废记录": "已作废"}
NEGATIVE_ACTIONS = ["作废记录"]

# 记录状态与质控标识的对应关系：列表、导出、统计都从这里取，保证刷新后两边一致。
QC_FLAG_BY_STATUS = {"待质控": "未质控", "质控通过": "合格", "疑误标记": "疑误", "已作废": "作废"}

# 批量导入时文件里每一行必须具备的列。
IMPORT_FIELDS = ["所属站点", "观测要素", "观测时刻", "观测数值", "数值单位"]

# 观测时刻允许的写法，导入时统一归一成 %Y-%m-%d %H:%M:%S 再落库。
MOMENT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
)
MOMENT_FORMAT_HINT = "YYYY-MM-DD HH:MM:SS（也支持 YYYY-MM-DD HH:MM、YYYY-MM-DD）"

RECORD_NO_PATTERN = re.compile(r"^OBSE-(\d+)$")


def parse_moment(raw: str) -> tuple[str | None, str | None]:
    """把观测时刻归一成标准格式；解析不了时说明期望的格式。"""
    text = raw.strip()
    for fmt in MOMENT_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S"), None
        except ValueError:
            continue
    return None, f"观测时刻「{raw}」格式不对：应为 {MOMENT_FORMAT_HINT}，例如 2026-09-27 08:00:00"


def parse_value(raw: str) -> tuple[float | int | None, str | None]:
    """把观测数值解析成数字；不是数字时说明应该长什么样。"""
    text = raw.strip()
    try:
        number = float(text)
    except ValueError:
        return None, f"观测数值「{raw}」不是数字：应为整数或小数，例如 23.5"
    if not math.isfinite(number):
        return None, f"观测数值「{raw}」不是有效数字：不能为无穷大或 NaN"
    if number.is_integer():
        return int(number), None
    return number, None


def dedup_key(station: Any, element: Any, moment: Any) -> tuple[str, str, str]:
    """同一站点、同一要素、同一时刻视为重复记录。"""
    moment_text = str(moment or "").strip()
    normalized, _ = parse_moment(moment_text)
    return (
        str(station or "").strip(),
        str(element or "").strip(),
        normalized or moment_text,
    )


class ObservationService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        station: str | None = None,
        element: str | None = None,
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

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        """让记录状态、质控标识始终跟着内部状态走，避免刷新后两边对不上。"""
        status = str(row.get("status") or STATUS_ORDER[0])
        row["status"] = status
        row["记录状态"] = status
        row["质控标识"] = QC_FLAG_BY_STATUS.get(status, QC_FLAG_BY_STATUS[STATUS_ORDER[0]])
        return row

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        station: str | None = None,
        element: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._normalize(row) for row in self._filter_rows(
            keyword=keyword, status=status, station=station, element=element,
        )]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def stats(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        station: str | None = None,
        element: str | None = None,
    ) -> dict[str, int]:
        """按与列表完全相同的条件统计，保证页面卡片数字和列表条数对得上。"""
        rows = self._filter_rows(keyword=keyword, status=status, station=station, element=element)
        today = date.today().strftime("%Y-%m-%d")
        return {
            "total": len(rows),
            "today": sum(1 for row in rows if str(row.get("观测时刻", "")).startswith(today)),
            "pending": sum(1 for row in rows if row.get("status") == "待质控"),
            "abnormal": sum(1 for row in rows if row.get("status") == "疑误标记"),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._normalize(entry)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("观测时刻", "观测数值", "数值单位"):
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._normalize(entry), []

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
        return self._normalize(entry), f"观测记录已{action}"

    @staticmethod
    def _next_record_no(rows: list[dict[str, Any]]) -> str:
        """在已有编号基础上顺延，生成 OBSE-XXXX 形式的记录编号。"""
        serial = 0
        for row in rows:
            match = RECORD_NO_PATTERN.match(str(row.get("记录编号", "")))
            if match:
                serial = max(serial, int(match.group(1)))
        return f"OBSE-{serial + 1:04d}"

    def import_rows(self, raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
        """成批写入观测记录。

        逐行校验、逐行落库：一行不合格只影响这一行，不回滚整批；
        数值、时刻的格式问题单独汇总；同站同要素同时刻只保留第一条。
        """
        rows = store.rows(MODULE)
        existing_keys = {
            dedup_key(row.get("所属站点"), row.get("观测要素"), row.get("观测时刻")) for row in rows
        }
        next_id = max((int(row.get("id", 0)) for row in rows), default=0)

        results: list[dict[str, Any]] = []
        format_errors: list[dict[str, Any]] = []
        station_groups: dict[str, dict[str, Any]] = {}
        imported = failed = duplicated = 0

        for line, raw in enumerate(raw_rows, start=2):  # 文件第 1 行是表头
            station = str(raw.get("所属站点") or "").strip()
            element = str(raw.get("观测要素") or "").strip()
            moment_raw = str(raw.get("观测时刻") or "").strip()
            value_raw = str(raw.get("观测数值") or "").strip()
            unit = str(raw.get("数值单位") or "").strip()

            group = station_groups.setdefault(station or "（未填写站点）", {
                "station": station or "（未填写站点）", "imported": 0, "failed": 0, "duplicated": 0,
            })
            result = {"line": line, "station": station, "element": element, "moment": moment_raw,
                      "result": "", "reason": None, "record_no": None}

            problems: list[str] = []
            missing = [label for label, text in (("所属站点", station), ("观测要素", element),
                                                 ("观测时刻", moment_raw), ("观测数值", value_raw))
                       if not text]
            if missing:
                problems.append(f"缺少必填字段：{'、'.join(missing)}")

            value: float | int | None = None
            if value_raw:
                value, error = parse_value(value_raw)
                if error:
                    problems.append(error)
                    format_errors.append({"line": line, "field": "观测数值", "value": value_raw,
                                          "reason": error})
            moment: str | None = None
            if moment_raw:
                moment, error = parse_moment(moment_raw)
                if error:
                    problems.append(error)
                    format_errors.append({"line": line, "field": "观测时刻", "value": moment_raw,
                                          "reason": error})

            if problems:
                failed += 1
                group["failed"] += 1
                result["result"] = "失败"
                result["reason"] = "；".join(problems)
                results.append(result)
                continue

            key = dedup_key(station, element, moment)
            if key in existing_keys:
                duplicated += 1
                group["duplicated"] += 1
                result["result"] = "重复跳过"
                result["reason"] = "同一站点同一要素同一时刻已有记录，仅保留一条"
                results.append(result)
                continue

            next_id += 1
            record_no = self._next_record_no(rows)
            entry = {
                "id": next_id,
                "记录编号": record_no,
                "所属站点": station,
                "观测要素": element,
                "观测时刻": moment,
                "观测数值": value,
                "数值单位": unit,
                "status": STATUS_ORDER[0],
                "pending": True,
                "abnormal": False,
            }
            rows.append(entry)
            existing_keys.add(key)
            imported += 1
            group["imported"] += 1
            result["result"] = "成功"
            result["record_no"] = record_no
            result["moment"] = moment
            results.append(result)

        total = len(raw_rows)
        return {
            "ok": failed == 0,
            "message": f"共解析 {total} 行：成功 {imported} 条、失败 {failed} 条、重复跳过 {duplicated} 条",
            "total_rows": total,
            "imported": imported,
            "failed": failed,
            "duplicated": duplicated,
            "stations": list(station_groups.values()),
            "rows": results,
            "format_errors": format_errors,
        }
