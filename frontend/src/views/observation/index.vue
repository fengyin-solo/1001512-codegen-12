<template>
  <section class="page" data-module="observation">
    <header class="page-head">
      <div>
        <h2>观测记录管理</h2>
        <p class="page-desc">维护观测记录，围绕记录编号、所属站点、观测要素、观测时刻做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记观测记录</button>
        <button class="btn primary" type="button" :disabled="importing" @click="triggerImport">
          {{ importing ? '正在导入…' : '批量导入观测记录' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出观测记录清单</button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,text/csv"
          class="visually-hidden"
          @change="handleImportFile"
        />
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
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
        <span>记录状态</span>
        <select v-model="filters['记录状态']">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <section v-if="importResult" class="import-panel">
      <header class="import-head">
        <strong>{{ importResult.message }}</strong>
        <button class="link" type="button" @click="importResult = null">收起结果</button>
      </header>

      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">文件总行数</span>
          <strong class="stat-value">{{ importResult.total_rows }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">导入成功</span>
          <strong class="stat-value">{{ importResult.imported }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">失败行数</span>
          <strong class="stat-value">{{ importResult.failed }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">重复跳过</span>
          <strong class="stat-value">{{ importResult.duplicated }}</strong>
        </article>
      </div>

      <h3 class="import-subtitle">按站点分组写入结果</h3>
      <table class="data-table">
        <thead>
          <tr><th>所属站点</th><th>成功</th><th>失败</th><th>重复跳过</th></tr>
        </thead>
        <tbody>
          <tr v-for="group in importResult.stations" :key="group.station">
            <td>{{ group.station }}</td>
            <td>{{ group.imported }}</td>
            <td>{{ group.failed }}</td>
            <td>{{ group.duplicated }}</td>
          </tr>
        </tbody>
      </table>

      <template v-if="importResult.format_errors.length">
        <h3 class="import-subtitle">格式问题行（数值 / 时刻）</h3>
        <table class="data-table">
          <thead>
            <tr><th>文件行号</th><th>问题字段</th><th>填写内容</th><th>问题说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in importResult.format_errors" :key="`fmt-${index}`">
              <td>{{ item.line }}</td>
              <td>{{ item.field }}</td>
              <td>{{ item.value || '（空）' }}</td>
              <td class="error-text">{{ item.reason }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <h3 class="import-subtitle">逐行导入结果</h3>
      <table class="data-table">
        <thead>
          <tr><th>文件行号</th><th>所属站点</th><th>观测要素</th><th>观测时刻</th><th>结果</th><th>记录编号</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in importResult.rows" :key="row.line">
            <td>{{ row.line }}</td>
            <td>{{ row.station || '—' }}</td>
            <td>{{ row.element || '—' }}</td>
            <td>{{ row.moment || '—' }}</td>
            <td>
              <span class="tag" :class="tagClass(row.result)">{{ row.result }}</span>
            </td>
            <td>{{ row.record_no ?? '—' }}</td>
            <td>{{ row.reason ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

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
          <td :colspan="columns.length + 1" class="empty-state">暂无观测记录数据，可先登记观测记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测记录记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface StationGroup {
  station: string
  imported: number
  failed: number
  duplicated: number
}

interface ImportRowResult {
  line: number
  station: string
  element: string
  moment: string
  result: string
  reason: string | null
  record_no: string | null
}

interface FormatError {
  line: number
  field: string
  value: string
  reason: string
}

interface ImportResult {
  ok: boolean
  message: string
  total_rows: number
  imported: number
  failed: number
  duplicated: number
  stations: StationGroup[]
  rows: ImportRowResult[]
  format_errors: FormatError[]
}

const ENDPOINT = '/api/observation'
const columns = ["记录编号", "所属站点", "观测要素", "观测时刻", "观测数值", "数值单位", "质控标识", "记录状态"]
const actions = ["提交质控", "标记疑误", "作废记录"]
const statuses = ["待质控", "质控通过", "疑误标记", "已作废"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref([
  { label: '记录总条数', value: 0 },
  { label: '今日观测条数', value: 0 },
  { label: '待质控记录', value: 0 },
  { label: '疑误标记数', value: 0 },
])

const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const importResult = ref<ImportResult | null>(null)

function buildQuery(): URLSearchParams {
  const query = new URLSearchParams()
  if (filters.value['记录编号']) query.set('keyword', filters.value['记录编号'])
  if (filters.value['所属站点']) query.set('station', filters.value['所属站点'])
  if (filters.value['观测要素']) query.set('element', filters.value['观测要素'])
  if (filters.value['记录状态']) query.set('status', filters.value['记录状态'])
  return query
}

function tagClass(result: string): string {
  if (result === '成功') return 'tag-ok'
  if (result === '重复跳过') return 'tag-dup'
  return 'tag-fail'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  const query = buildQuery().toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '观测记录登记入口尚未接入审批流'
}

function triggerImport() {
  fileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  errorMessage.value = ''
  importing.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const response = await request(`${ENDPOINT}/import`, { method: 'POST', body: form })
    if (!response.ok) {
      let detail = `批量导入失败（接口返回 ${response.status}）`
      try {
        const data = await response.json()
        if (data?.detail) detail = String(data.detail)
      } catch {
        // 保留默认提示
      }
      throw new Error(detail)
    }
    importResult.value = (await response.json()) as ImportResult
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量导入失败'
  } finally {
    importing.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('观测记录动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery().toString()
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats?${query}`),
    ])
    if (!listResponse.ok) {
      throw new Error('观测记录列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const data = await statsResponse.json()
      stats.value = [
        { label: '记录总条数', value: data.total ?? 0 },
        { label: '今日观测条数', value: data.today ?? 0 },
        { label: '待质控记录', value: data.pending ?? 0 },
        { label: '疑误标记数', value: data.abnormal ?? 0 },
      ]
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测记录列表读取失败'
  }
}

onMounted(reload)
</script>
