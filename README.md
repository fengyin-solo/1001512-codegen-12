# 气象观测站网运维平台

面向区域气象观测站网的站点入网、传感器检定、观测数据质控、供电通信保障与运维结算的一体化运行监控后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 观测站点 | `station` | 观测站点 | 站点编码、站点名称、站点类别 |
| 观测传感器 | `sensor` | 观测传感器 | 传感器编号、所属站点、观测要素 |
| 观测记录 | `observation` | 观测记录 | 记录编号、所属站点、观测要素 |
| 数据质控 | `quality` | 质控任务 | 质控编号、质控时段、涉及站点 |
| 设备标定 | `calibration` | 标定记录 | 标定编号、标定对象、标定机构 |
| 数据传输 | `transmission` | 传输链路 | 链路编号、所属站点、传输方式 |
| 供电保障 | `power` | 供电单元 | 供电编号、所属站点、供电方式 |
| 站网布局 | `layout` | 站网规划 | 规划编号、规划区域、目标站距 |
| 巡检任务 | `inspection` | 巡检单 | 巡检单号、巡检站点、巡检人员 |
| 故障处置 | `fault` | 故障记录 | 故障编号、涉及站点、故障现象 |
| 备件器材 | `sparepart` | 备件器材 | 备件编号、备件名称、适用型号 |
| 元数据登记 | `metainfo` | 元数据记录 | 元数据编号、关联站点、元数据类型 |
| 告警监测 | `alarm` | 告警记录 | 告警编号、告警来源、告警类型 |
| 通信设备 | `comm` | 通信设备 | 设备编号、设备名称、设备型号 |
| 服务保障 | `service` | 服务事项 | 事项编号、服务对象、服务类别 |
| 运维合同 | `contract` | 运维合同 | 合同编号、服务单位、合同金额 |
| 经费结算 | `settlement` | 结算单 | 结算单号、关联合同、结算周期 |
| 人员培训 | `training` | 培训记录 | 培训编号、培训主题、培训对象 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 观测记录成批导入

观测记录页支持上传 CSV 文件成批导入（`POST /api/observation/import`）：

- 文件表头固定为 `记录编号,所属站点,观测要素,观测时刻,观测数值,数值单位`，模板可从
  `GET /api/observation/template` 下载；记录编号留空时按 `OBSE-序号` 自动补号。
- 逐行校验、逐行落库：观测数值不是数字、观测时刻不是合法日期时间、缺必填字段的行
  单独标为失败并说明原因，单行失败不回滚整批。
- 同一站点、同一观测要素、同一观测时刻的重复记录（文件内或库内已存在）只保留一条，
  重复行在结果里标注跳过。
- 返回按站点分组的成功/失败/重复计数与每一行的结果；导入后页面按当前筛选条件刷新，
  列表条数与统计卡片同口径（`GET /api/observation/stats`）。
- `GET /api/observation/export` 按当前条件导出 CSV（UTF-8 BOM，Excel 可直接打开），
  列里带记录编号与数值单位，条数与列表一致。
- 后端回归测试：`cd backend && .venv/bin/python -m unittest discover -s tests`。
