<template>
  <section class="page" data-module="observation">
    <header class="page-head">
      <div>
        <h2>观测记录管理</h2>
        <p class="page-desc">维护观测记录，围绕记录编号、所属站点、观测要素、观测时刻做登记、成批导入、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记观测记录</button>
        <button class="btn primary" type="button" @click="openImport">成批导入</button>
        <button class="btn" type="button" @click="exportRows">导出观测记录清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statsCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>质控标识</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无观测记录数据，可先登记或成批导入观测记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测记录（与上方统计同口径）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="importVisible" class="modal-mask" @click.self="closeImport">
      <div class="modal">
        <div class="modal-head">
          <h3>观测记录成批导入</h3>
          <button class="link" type="button" @click="closeImport">关闭</button>
        </div>
        <p class="modal-tip">
          请按模板整理 CSV 文件：列依次为「记录编号、所属站点、观测要素、观测时刻、观测数值、数值单位」，
          记录编号可留空由系统补号。逐行校验，单行失败不影响其它行；同一站点同一要素同一时刻只保留一条。
        </p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="downloadTemplate">下载导入模板</button>
          <input ref="fileInput" class="file-input" type="file" accept=".csv,text/csv,text/plain" @change="onFileChange" />
          <button class="btn primary" type="button" :disabled="!fileContent || importing" @click="submitImport">
            {{ importing ? '导入中…' : '开始导入' }}
          </button>
          <span v-if="pickedName" class="file-name">已选择：{{ pickedName }}</span>
        </div>

        <div v-if="importSummary" class="import-summary">
          <strong>{{ importSummary.message }}</strong>
          <table class="data-table group-table">
            <thead>
              <tr><th>所属站点</th><th>成功</th><th>失败</th><th>重复跳过</th></tr>
            </thead>
            <tbody>
              <tr v-for="g in importSummary.groups" :key="g.station">
                <td>{{ g.station }}</td>
                <td class="num-ok">{{ g.success }}</td>
                <td class="num-fail">{{ g.failed }}</td>
                <td class="num-dup">{{ g.duplicated }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <table v-if="importResults.length" class="data-table import-table">
          <thead>
            <tr>
              <th>文件行号</th>
              <th>所属站点</th>
              <th>观测要素</th>
              <th>观测时刻</th>
              <th>观测数值</th>
              <th>数值单位</th>
              <th>结果</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in importResults" :key="r.line" :class="rowStateClass(r)">
              <td>第 {{ r.line }} 行</td>
              <td>{{ r.values['所属站点'] || '—' }}</td>
              <td>{{ r.values['观测要素'] || '—' }}</td>
              <td>{{ r.values['观测时刻'] || '—' }}</td>
              <td>{{ r.values['观测数值'] || '—' }}</td>
              <td>{{ r.values['数值单位'] || '—' }}</td>
              <td>{{ rowStateText(r) }}</td>
              <td>{{ r.reason }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="importError" class="error-text">{{ importError }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ImportLine = {
  line: number
  ok: boolean
  duplicated: boolean
  reason: string
  values: Record<string, string>
}
type ImportSummary = {
  message: string
  groups: { station: string; success: number; failed: number; duplicated: number }[]
}

const ENDPOINT = '/api/observation'
const columns = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
const actions = ["提交质控", "标记疑误", "作废记录"]
const statuses = ["待质控", "质控通过", "疑误标记", "已作废"]
const filterFields = ["记录编号", "所属站点", "观测要素"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({
  记录编号: '',
  所属站点: '',
  观测要素: '',
  status: '',
})
const stats = ref({ total: 0, pending: 0, suspicious: 0, passed: 0, discarded: 0 })

const statsCards = computed(() => [
  { label: '当前条件记录条数', value: stats.value.total },
  { label: '待质控记录', value: stats.value.pending },
  { label: '质控通过', value: stats.value.passed },
  { label: '疑误标记数', value: stats.value.suspicious },
])

function activeQuery(includeStatus = true) {
  const params: Record<string, string> = {
    keyword: filters.value['记录编号']?.trim() ?? '',
    station: filters.value['所属站点']?.trim() ?? '',
    element: filters.value['观测要素']?.trim() ?? '',
  }
  if (includeStatus && filters.value.status) {
    params.status = filters.value.status
  }
  return new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v))).toString()
}

function resetFilters() {
  filters.value = { 记录编号: '', 所属站点: '', 观测要素: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export?${activeQuery(true)}`, '_blank')
}

function openCreate() {
  errorMessage.value = '观测记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('观测记录动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录操作失败'
  }
}

async function reloadStats() {
  // 统计与列表、卡片严格同口径：记录编号/站点/要素/质控标识条件全部带上
  const response = await request(`${ENDPOINT}/stats?${activeQuery(true)}`)
  if (response.ok) {
    stats.value = await response.json()
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const query = activeQuery(true)
    const response = await request(`${ENDPOINT}?${query}&size=200`)
    if (!response.ok) {
      throw new Error('观测记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录列表读取失败'
  }
}

// ---- 成批导入 ----
const importVisible = ref(false)
const importing = ref(false)
const pickedName = ref('')
const fileContent = ref('')
const importResults = ref<ImportLine[]>([])
const importSummary = ref<ImportSummary | null>(null)
const importError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

function openImport() {
  importVisible.value = true
  importError.value = ''
}

function closeImport() {
  importVisible.value = false
}

function downloadTemplate() {
  window.open(`${ENDPOINT}/template`, '_blank')
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }
  pickedName.value = file.name
  importError.value = ''
  const reader = new FileReader()
  reader.onload = () => {
    fileContent.value = String(reader.result ?? '')
  }
  reader.onerror = () => {
    importError.value = '文件读取失败，请重新选择'
  }
  reader.readAsText(file, 'utf-8')
}

function rowStateText(r: ImportLine) {
  if (!r.ok) return '失败'
  return r.duplicated ? '重复跳过' : '成功'
}

function rowStateClass(r: ImportLine) {
  if (!r.ok) return 'row-fail'
  return r.duplicated ? 'row-dup' : 'row-ok'
}

async function submitImport() {
  if (!fileContent.value.trim()) {
    importError.value = '文件内容为空，请重新选择'
    return
  }
  importing.value = true
  importError.value = ''
  importResults.value = []
  importSummary.value = null
  try {
    const response = await request(`${ENDPOINT}/import`, {
      method: 'POST',
      body: JSON.stringify({ content: fileContent.value, filename: pickedName.value }),
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload?.detail ?? '导入失败，请检查文件格式')
    }
    importSummary.value = { message: payload.message, groups: payload.groups ?? [] }
    importResults.value = payload.results ?? []
    await reload()
  } catch (error) {
    importError.value = error instanceof Error ? error.message : '导入失败'
  } finally {
    importing.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 16px;
  z-index: 100;
  overflow-y: auto;
}
.modal {
  background: #fff;
  border-radius: 10px;
  width: min(960px, 100%);
  padding: 18px 20px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.2);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-tip { color: var(--muted); font-size: 12px; line-height: 1.7; }
.modal-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.file-input { font-size: 12px; }
.file-name { color: var(--muted); font-size: 12px; }
.import-summary { margin-bottom: 12px; font-size: 13px; }
.group-table { margin-top: 8px; width: auto; }
.group-table td, .group-table th { padding: 5px 14px; }
.import-table td, .import-table th { font-size: 12px; }
.num-ok { color: #067647; }
.num-fail { color: #b42318; }
.num-dup { color: #b54708; }
.row-ok td { background: #f0fdf4; }
.row-fail td { background: #fef3f2; }
.row-dup td { background: #fffaeb; }
</style>
