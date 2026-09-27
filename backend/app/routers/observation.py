"""观测记录接口：维护观测记录，覆盖批量导入、提交质控、标记疑误、作废记录等动作。"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.observation import IMPORT_FIELDS, ObservationService

router = APIRouter(prefix="/api/observation", tags=["观测记录"])

service = ObservationService()

LIST_FIELDS = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
STATUSES = ["待质控", "质控通过", "疑误标记", "已作废"]


def _decode_upload(raw: bytes) -> str:
    """导入文件按 UTF-8（含 BOM）优先、GBK 兜底解码，都不通就明确报错。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="文件编码无法识别，请使用 UTF-8 或 GBK 编码的 CSV 文件")


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号、站点、要素与状态过滤观测记录列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, station=station, element=element, page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
) -> dict[str, int]:
    """按当前筛选条件统计条数，口径与列表一致，供页面卡片核对。"""
    return service.stats(keyword=keyword, status=status, station=station, element=element)


@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="待质控、质控通过、疑误标记、已作废"),
    station: str | None = Query(default=None, description="按所属站点检索"),
    element: str | None = Query(default=None, description="按观测要素检索"),
) -> Response:
    """导出当前过滤条件下的观测记录 CSV，列里带记录编号与数值单位。"""
    items, _ = service.list_entries(
        keyword=keyword, status=status, station=station, element=element, page=1, size=10000,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(LIST_FIELDS)
    for item in items:
        writer.writerow([item.get(field, "") for field in LIST_FIELDS])
    content = "\ufeff" + buffer.getvalue()  # 带 BOM，Excel 打开不乱码
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="observation_export.csv"'},
    )


@router.post("/import")
async def import_entries(file: UploadFile = File(..., description="观测记录 CSV 文件")) -> dict[str, Any]:
    """成批导入观测记录：按站点分组写入，逐行返回成功或失败原因，单行失败不回滚整批。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传的文件是空的，请确认文件内容后重新上传")
    text = _decode_upload(raw)
    reader = csv.DictReader(io.StringIO(text))
    headers = [str(name).strip() for name in (reader.fieldnames or [])]
    missing_headers = [field for field in IMPORT_FIELDS if field not in headers]
    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=f"文件缺少必需列：{'、'.join(missing_headers)}；表头应为 {','.join(IMPORT_FIELDS)}",
        )
    raw_rows = list(reader)
    if not raw_rows:
        raise HTTPException(status_code=400, detail="文件里没有数据行，至少填写一行观测记录")
    return service.import_rows(raw_rows)


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
