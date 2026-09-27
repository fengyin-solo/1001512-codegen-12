"""观测记录接口：维护观测记录，覆盖成批导入、提交质控、标记疑误、作废记录等动作。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, ImportPayload, PageResult
from app.services.observation import IMPORT_COLUMNS, ObservationService

router = APIRouter(prefix="/api/observation", tags=["观测记录"])

service = ObservationService()

LIST_FIELDS = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
EXPORT_FIELDS = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
STATUSES = ["待质控", "质控通过", "疑误标记", "已作废"]


def _csv_response(rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    """按固定列拼装 UTF-8（带 BOM，Excel 直接打开不乱码）CSV。"""
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in EXPORT_FIELDS})
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、站点、要素与状态过滤观测记录列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, station=station, element=element, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def entry_stats(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
) -> dict[str, int]:
    """按当前筛选条件统计记录条数与各质控标识数量，口径与列表完全一致。"""
    return service.summarize(keyword=keyword, station=station, element=element, status=status)


@router.get("/template")
def download_template() -> StreamingResponse:
    """下载成批导入模板：表头与导入列严格一致，附两行示例。"""
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(IMPORT_COLUMNS)
    writer.writerow(["", "STAT-0001", "气温", "2026-09-27 08:00:00", "21.6", "℃"])
    writer.writerow(["", "STAT-0001", "相对湿度", "2026-09-27 08:00:00", "68", "%"])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="observation_import_template.csv"'},
    )


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
) -> StreamingResponse:
    """按当前过滤条件导出 CSV：列里带记录编号与数值单位，条数与列表、统计对得上。"""
    items, total = service.list_entries(
        keyword=keyword, station=station, element=element, status=status, page=1, size=100000
    )
    response = _csv_response(items, "observation_records.csv")
    response.headers["X-Total-Count"] = str(total)
    return response


@router.post("/import")
def import_entries(payload: ImportPayload) -> dict[str, Any]:
    """成批导入观测记录：逐行校验、逐行落库，单行失败只记录原因不回滚整批。

    同一站点、同一观测要素、同一观测时刻的重复记录（文件内或库内）只保留一条。
    """
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="导入文件为空，请选择按模板填写后的文件")
    try:
        return service.import_rows(payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条观测记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条观测记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="观测记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条观测记录执行提交质控、标记疑误、作废记录；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
