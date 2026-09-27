"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ImportPayload(BaseModel):
    """成批导入时提交的记录文件文本内容（前端读取 CSV/文本文件后原样传入）。"""

    content: str = ""
    filename: str | None = None



class StationEntry(BaseModel):
    """观测站点明细结构。"""

    field_0: str | None = None  # 站点编码
    field_1: str | None = None  # 站点名称
    field_2: str | None = None  # 站点类别
    field_3: str | None = None  # 经纬度坐标
    field_4: str | None = None  # 海拔高度
    field_5: str | None = None  # 建站年份
    field_6: str | None = None  # 值守方式
    field_7: str | None = None  # 站点状态

class SensorEntry(BaseModel):
    """观测传感器明细结构。"""

    field_0: str | None = None  # 传感器编号
    field_1: str | None = None  # 所属站点
    field_2: str | None = None  # 观测要素
    field_3: str | None = None  # 设备型号
    field_4: str | None = None  # 出厂序列号
    field_5: str | None = None  # 安装高度
    field_6: str | None = None  # 检定有效期
    field_7: str | None = None  # 传感器状态

class ObservationEntry(BaseModel):
    """观测记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 所属站点
    field_2: str | None = None  # 观测要素
    field_3: str | None = None  # 观测时刻
    field_4: str | None = None  # 观测数值
    field_5: str | None = None  # 数值单位
    field_6: str | None = None  # 质控标识
    field_7: str | None = None  # 记录状态

class QualityEntry(BaseModel):
    """质控任务明细结构。"""

    field_0: str | None = None  # 质控编号
    field_1: str | None = None  # 质控时段
    field_2: str | None = None  # 涉及站点
    field_3: str | None = None  # 质控规则
    field_4: str | None = None  # 检出疑误数
    field_5: str | None = None  # 质控人员
    field_6: str | None = None  # 质控日期
    field_7: str | None = None  # 质控状态

class CalibrationEntry(BaseModel):
    """标定记录明细结构。"""

    field_0: str | None = None  # 标定编号
    field_1: str | None = None  # 标定对象
    field_2: str | None = None  # 标定机构
    field_3: str | None = None  # 标定项目
    field_4: str | None = None  # 标定结论
    field_5: str | None = None  # 有效期至
    field_6: str | None = None  # 标定人员
    field_7: str | None = None  # 标定状态

class TransmissionEntry(BaseModel):
    """传输链路明细结构。"""

    field_0: str | None = None  # 链路编号
    field_1: str | None = None  # 所属站点
    field_2: str | None = None  # 传输方式
    field_3: str | None = None  # 上报频次
    field_4: str | None = None  # 最近上报时刻
    field_5: str | None = None  # 缺报次数
    field_6: str | None = None  # 链路带宽
    field_7: str | None = None  # 链路状态

class PowerEntry(BaseModel):
    """供电单元明细结构。"""

    field_0: str | None = None  # 供电编号
    field_1: str | None = None  # 所属站点
    field_2: str | None = None  # 供电方式
    field_3: str | None = None  # 蓄电池容量
    field_4: str | None = None  # 上次放电测试
    field_5: str | None = None  # 备电时长
    field_6: str | None = None  # 责任人员
    field_7: str | None = None  # 供电状态

class LayoutEntry(BaseModel):
    """站网规划明细结构。"""

    field_0: str | None = None  # 规划编号
    field_1: str | None = None  # 规划区域
    field_2: str | None = None  # 目标站距
    field_3: str | None = None  # 拟建站数
    field_4: str | None = None  # 已建站数
    field_5: str | None = None  # 编制人员
    field_6: str | None = None  # 审批人员
    field_7: str | None = None  # 规划状态

class InspectionEntry(BaseModel):
    """巡检单明细结构。"""

    field_0: str | None = None  # 巡检单号
    field_1: str | None = None  # 巡检站点
    field_2: str | None = None  # 巡检人员
    field_3: str | None = None  # 巡检日期
    field_4: str | None = None  # 巡检项目
    field_5: str | None = None  # 发现问题数
    field_6: str | None = None  # 巡检时长
    field_7: str | None = None  # 巡检状态

class FaultEntry(BaseModel):
    """故障记录明细结构。"""

    field_0: str | None = None  # 故障编号
    field_1: str | None = None  # 涉及站点
    field_2: str | None = None  # 故障现象
    field_3: str | None = None  # 发生时刻
    field_4: str | None = None  # 影响要素
    field_5: str | None = None  # 处置人员
    field_6: str | None = None  # 恢复时刻
    field_7: str | None = None  # 故障状态

class SparepartEntry(BaseModel):
    """备件器材明细结构。"""

    field_0: str | None = None  # 备件编号
    field_1: str | None = None  # 备件名称
    field_2: str | None = None  # 适用型号
    field_3: str | None = None  # 结存数量
    field_4: str | None = None  # 计量单位
    field_5: str | None = None  # 存放库位
    field_6: str | None = None  # 保管人员
    field_7: str | None = None  # 备件状态

class MetainfoEntry(BaseModel):
    """元数据记录明细结构。"""

    field_0: str | None = None  # 元数据编号
    field_1: str | None = None  # 关联站点
    field_2: str | None = None  # 元数据类型
    field_3: str | None = None  # 版本号
    field_4: str | None = None  # 变更内容
    field_5: str | None = None  # 登记人员
    field_6: str | None = None  # 生效日期
    field_7: str | None = None  # 元数据状态

class AlarmEntry(BaseModel):
    """告警记录明细结构。"""

    field_0: str | None = None  # 告警编号
    field_1: str | None = None  # 告警来源
    field_2: str | None = None  # 告警类型
    field_3: str | None = None  # 触发阈值
    field_4: str | None = None  # 触发时刻
    field_5: str | None = None  # 处置人员
    field_6: str | None = None  # 关闭时刻
    field_7: str | None = None  # 告警状态

class CommEntry(BaseModel):
    """通信设备明细结构。"""

    field_0: str | None = None  # 设备编号
    field_1: str | None = None  # 设备名称
    field_2: str | None = None  # 设备型号
    field_3: str | None = None  # 所属站点
    field_4: str | None = None  # 安装日期
    field_5: str | None = None  # 上次检修日
    field_6: str | None = None  # 责任人
    field_7: str | None = None  # 设备状态

class ServiceEntry(BaseModel):
    """服务事项明细结构。"""

    field_0: str | None = None  # 事项编号
    field_1: str | None = None  # 服务对象
    field_2: str | None = None  # 服务类别
    field_3: str | None = None  # 响应时限
    field_4: str | None = None  # 受理人员
    field_5: str | None = None  # 完成时刻
    field_6: str | None = None  # 评价结果
    field_7: str | None = None  # 事项状态

class ContractEntry(BaseModel):
    """运维合同明细结构。"""

    field_0: str | None = None  # 合同编号
    field_1: str | None = None  # 服务单位
    field_2: str | None = None  # 合同金额
    field_3: str | None = None  # 服务期限
    field_4: str | None = None  # 考核方式
    field_5: str | None = None  # 签订人员
    field_6: str | None = None  # 到期日期
    field_7: str | None = None  # 合同状态

class SettlementEntry(BaseModel):
    """结算单明细结构。"""

    field_0: str | None = None  # 结算单号
    field_1: str | None = None  # 关联合同
    field_2: str | None = None  # 结算周期
    field_3: str | None = None  # 应付金额
    field_4: str | None = None  # 已付金额
    field_5: str | None = None  # 审核人员
    field_6: str | None = None  # 付款日期
    field_7: str | None = None  # 结算状态

class TrainingEntry(BaseModel):
    """培训记录明细结构。"""

    field_0: str | None = None  # 培训编号
    field_1: str | None = None  # 培训主题
    field_2: str | None = None  # 培训对象
    field_3: str | None = None  # 授课人员
    field_4: str | None = None  # 培训课时
    field_5: str | None = None  # 考核成绩
    field_6: str | None = None  # 培训日期
    field_7: str | None = None  # 培训状态
