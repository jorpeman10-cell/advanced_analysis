# 月会执行跟进模块需求文档

## 1. 背景

当前 v2 工具已经能分析顾问表现、项目转化、现金流和经营风险，但管理动作仍停留在“看见问题”。月会后形成的跟进计划、顾问任务和管理要求没有结构化沉淀，也无法在下个月自动核查完成情况。

本模块目标是把月会结论变成可追踪的经营任务，并在下月基于真实业务数据做复盘。

## 2. 产品目标

新增一个“执行跟进”模块，用于：

- 记录每月月会的管理重点、责任人、任务和指标目标。
- 将定性任务拆解成可量化指标。
- 到下个月自动从系统数据中拉取完成情况，而不是依赖人工勾选。
- 输出任务完成率、未完成原因、管理建议和下月延续动作。

核心闭环：

`月会计划 -> 指标拆解 -> 数据追踪 -> 下月复盘 -> 管理动作更新`

核心原则：

> 凡是可量化任务，都必须绑定一个系统数据核查器。任务不是普通待办，而是可追溯、可复算、可审计的经营目标。

## 3. 典型场景

### 场景 A：顾问改善任务

月会要求 Larry Gao 下个月改善：

- BD 新增 2 家客户
- 新增面试 5 个
- 推荐到面试比例达到 50%
- 新增 Offer 1 个

系统下月自动核查：

- Larry 实际新增 BD 客户数
- 实际新增面试数
- 推荐数、面试数、推面比
- Offer 新增数
- 是否完成、差距多少、问题在哪个环节

### 场景 B：回款专项任务

月会要求某顾问或管理者：

- 跟进 3 个逾期客户
- 本月回款目标 30 万
- 重点催收某客户历史 Invoice

系统下月核查：

- 实际回款金额
- 逾期金额是否下降
- 指定客户/发票是否完成回款
- 未完成客户列表

### 场景 C：团队经营任务

月会要求临床团队：

- 新增 Forecast 100 万
- Offer 未回款下降 20%
- 一面到 Offer 提升到 40%

系统下月按团队汇总复盘。

## 4. 用户角色

- 管理者：创建月会计划、分配任务、查看复盘。
- Team Lead：跟进团队和顾问任务。
- 顾问：查看自己任务和完成情况。
- AI Agent：基于任务和数据生成复盘解释、风险提醒和下月建议。

## 5. 功能范围

### 5.0 管理任务智能解析

支持管理者用自然语言输入月会行动项，由系统解析成结构化任务。

示例输入：

> Larry 下个月重点改善 BD 和转化：BD 2 家客户，新增面试 5 个，推面比达到 50%，新增 Offer 1 个。

解析结果：

| 字段 | 解析值 |
| --- | --- |
| 责任对象 | Larry Gao |
| 责任类型 | 顾问 |
| 执行周期 | 下个月 |
| 管理主题 | 顾问产能 / 项目转化 |
| 任务 1 | BD新增客户数 >= 2 |
| 任务 2 | 新增面试数 >= 5 |
| 任务 3 | 推荐到面试比例 >= 50% |
| 任务 4 | 新增Offer数 >= 1 |
| 优先级 | 中/高，默认由管理者确认 |

#### 解析方式

第一期建议采用“规则解析 + LLM 辅助”的混合方式：

1. 规则解析负责高确定性信息：
   - 人名、团队名、客户名
   - 数字目标
   - 百分比目标
   - 时间词：本月、下月、下季度、月底前
   - 常见指标关键词：BD、面试、推荐、推面比、Offer、回款、Forecast、逾期

2. LLM 辅助负责模糊表达：
   - “提高转化”
   - “加强 BD”
   - “重点催收”
   - “减少低质量项目”
   - “下月要看到结果”

3. 解析后必须进入确认界面：
   - 不直接静默创建任务
   - 展示解析出的指标和目标
   - 管理者可以修改责任人、周期、指标、目标值

#### 解析置信度

每个解析结果给出置信度：

| 置信度 | 处理方式 |
| --- | --- |
| High | 自动填入，用户确认即可 |
| Medium | 高亮提醒用户检查 |
| Low | 不自动创建，要求用户手动选择指标 |

#### 解析输出结构

```json
{
  "source_text": "Larry 下个月改善：BD 2 家客户，新增面试 5 个，推面比 50%，新增 Offer 1 个",
  "owner_type": "consultant",
  "owner_name": "Larry Gao",
  "period": "next_month",
  "tasks": [
    {
      "metric": "new_bd_clients",
      "operator": ">=",
      "target_value": 2,
      "unit": "count",
      "confidence": "Medium"
    },
    {
      "metric": "new_interviews",
      "operator": ">=",
      "target_value": 5,
      "unit": "count",
      "confidence": "High"
    },
    {
      "metric": "referral_to_interview_rate",
      "operator": ">=",
      "target_value": 0.5,
      "unit": "percent",
      "confidence": "High"
    },
    {
      "metric": "new_offers",
      "operator": ">=",
      "target_value": 1,
      "unit": "count",
      "confidence": "High"
    }
  ]
}
```

#### 解析边界

第一期不建议让 LLM 自己定义新指标。LLM 只能把自然语言映射到系统已有指标模板；如果没有匹配指标，则输出“需要人工定义”。

例如：

- “提升客户感觉”不能自动核查，需要改写成客户回访数、客户新增岗位数、客户面试反馈时效等可量化指标。
- “加强团队管理”不能自动核查，需要拆成周会次数、任务完成率、低绩效顾问改善等指标。

### 5.1 月会计划录入

新增页面或 Tab：`执行跟进`

字段建议：

- 月会月份：例如 `2026-05`
- 计划名称：例如 `5月经营复盘行动项`
- 管理主题：现金流、顾问产能、项目转化、客户开发、Forecast、团队管理
- 责任类型：顾问、团队、客户、公司
- 责任对象：Larry Gao、临床团队、阿斯利康等
- 任务描述：自然语言输入
- 指标类型：从预设指标中选择
- 目标值
- 截止月份
- 优先级：高 / 中 / 低
- 状态：计划中 / 跟进中 / 已完成 / 未完成 / 延期 / 取消
- 备注

### 5.2 指标模板

第一期支持以下指标：

| 指标 | 口径 |
| --- | --- |
| BD新增客户数 | 统计期内新增客户/客户负责人变化，需根据数据库字段确认 |
| 新增项目数 | `joborder.dateAdded` 落在周期内 |
| 新增推荐数 | 推荐/简历提交数量 |
| 新增面试数 | 一面或客户面试数量 |
| 推面比 | 新增面试数 / 新增推荐数 |
| 一面到Offer | 新增Offer数 / 新增一面数 |
| 新增Offer数 | 有效 Offer / Invoice Added 数量 |
| Offer未回金额 | Invoice Added 阶段未回金额 |
| 开票未回金额 | Sent 阶段未回金额 |
| 总未回款储备 | Offer未回 + 开票未回 |
| 回款金额 | Received 且回款日期在周期内 |
| Forecast新增金额 | Forecast 新增或当前有效 Forecast 金额 |
| 逾期金额下降 | 上月逾期金额 - 本月逾期金额 |

### 5.3 系统数据核查器

每个任务保存时必须绑定一个 `metric_key`。下月复盘时，系统根据 `metric_key + 责任对象 + 复盘周期` 自动调用数据核查器，返回实际值和证据明细。

任务核查输入：

```json
{
  "metric_key": "new_interviews",
  "owner_type": "consultant",
  "owner_name": "Larry Gao",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "operator": ">=",
  "target_value": 5
}
```

任务核查输出：

```json
{
  "actual_value": 3,
  "target_value": 5,
  "completion_rate": 0.6,
  "is_completed": false,
  "gap": 2,
  "evidence_rows": [
    {
      "date": "2026-06-08",
      "client": "AstraZeneca",
      "position": "Medical Manager",
      "candidate": "Candidate A",
      "stage": "1st Interview"
    }
  ],
  "data_source": "process_data/clientinterview",
  "calculated_at": "2026-07-01 09:30:00"
}
```

#### 指标核查映射

| metric_key | 指标 | 责任对象 | 数据来源 | 实际值计算 |
| --- | --- | --- | --- | --- |
| `new_referrals` | 新增推荐数 | 顾问/团队 | v2 process data | 周期内推荐/简历提交数量 |
| `new_interviews` | 新增面试数 | 顾问/团队 | v2 process data | 周期内一面或客户面试数量 |
| `referral_to_interview_rate` | 推面比 | 顾问/团队 | v2 conversion data | 新增面试数 / 新增推荐数 |
| `interview_to_offer_rate` | 一面到Offer | 顾问/团队 | v2 conversion data | 新增Offer数 / 新增一面数 |
| `new_offers` | 新增Offer数 | 顾问/团队 | invoice + invoiceassignment | 周期内有效 `Invoice Added` 数量 |
| `offer_unpaid_amount` | Offer未回金额 | 顾问/团队 | invoice + invoiceassignment | 当前有效 `Invoice Added` 分配金额 |
| `invoice_unpaid_amount` | 开票未回金额 | 顾问/团队 | invoice + invoiceassignment | 当前有效 `Sent` 分配金额 |
| `total_unpaid_amount` | 总未回款储备 | 顾问/团队 | v2 offer_outcomes | Offer未回 + 开票未回 |
| `collection_amount` | 回款金额 | 顾问/团队 | invoice + invoiceassignment | 周期内 `Received` 分配金额 |
| `new_forecast_amount` | Forecast新增金额 | 顾问/团队 | forecast + forecastassignment | 周期内新增或有效 Forecast 金额 |
| `overdue_amount_reduction` | 逾期金额下降 | 客户/公司 | cashflow invoices | 上期逾期金额 - 本期逾期金额 |
| `new_bd_clients` | BD新增客户数 | 顾问/团队 | 待确认数据库字段 | 周期内新增客户或新增客户负责人 |

#### 证据明细要求

每个核查器不能只返回一个数，必须返回可追溯明细：

- 推荐/面试类：客户、职位、候选人、阶段日期、顾问
- Offer类：客户、职位、发票/Offer ID、状态、分配金额、顾问角色
- 回款类：客户、发票ID、回款日期、分配金额
- Forecast类：客户、职位、Forecast金额、阶段、预计关闭日期
- 逾期类：客户、发票ID、到期日、逾期天数、未回金额

这样管理者可以从“是否完成”点进去看到“系统为什么这么判断”。

#### 完成判定

支持以下操作符：

| operator | 含义 |
| --- | --- |
| `>=` | 实际值大于等于目标 |
| `<=` | 实际值小于等于目标 |
| `=` | 实际值等于目标 |
| `decrease_by` | 较基准下降指定金额或比例 |
| `increase_by` | 较基准提升指定金额或比例 |

完成率规则：

- 数量/金额增长类：`actual_value / target_value`，上限 100%
- 比例类：`actual_rate / target_rate`，上限 100%
- 下降类：`actual_reduction / target_reduction`，上限 100%
- 完成率可以显示超过目标的超额值，但主完成率不超过 100%，避免误导。

### 5.4 任务类型

任务分为三类：

1. 数值目标
   - 例如：新增面试 >= 5
   - 系统可自动判断完成/未完成

2. 比例目标
   - 例如：推面比 >= 50%
   - 系统计算实际比例并判断

3. 清单任务
   - 例如：跟进阿斯利康、武田、辉瑞三个客户
   - 第一期可手动勾选，第二期再做客户维度自动核查

### 5.5 自动复盘

每个任务展示：

- 目标值
- 实际值
- 完成率
- 完成状态
- 差距
- 数据证据
- AI 复盘建议

示例：

| 责任人 | 任务 | 目标 | 实际 | 状态 | 差距 |
| --- | --- | --- | --- | --- | --- |
| Larry Gao | 新增面试 | 5 | 3 | 未完成 | 差 2 个 |
| Larry Gao | 推面比 | 50% | 37.5% | 未完成 | 差 12.5pct |
| Larry Gao | 新增Offer | 1 | 1 | 完成 | 达标 |

### 5.6 AI Agent 辅助

Agent 不直接替代数据核查，而是在系统计算完成后生成解释。Agent 必须引用核查器返回的实际值和证据明细，不能凭空判断任务是否完成：

- 哪些任务完成
- 哪些没完成
- 未完成主要卡在哪个业务环节
- 是数量不足、质量不足、客户推进慢，还是回款转化问题
- 下月是否延续、加码或调整目标

## 6. 数据设计

第一期建议使用本地 JSON 或轻量 CSV 存储，方便 Streamlit Cloud 使用；后续再迁移数据库。

文件建议：

`config/execution_followups.json`

结构：

```json
{
  "plans": [
    {
      "id": "2026-05-larry-performance",
      "meeting_month": "2026-05",
      "owner_type": "consultant",
      "owner_name": "Larry Gao",
      "theme": "顾问产能",
      "task": "改善新增客户和转化",
      "metric": "new_interviews",
      "operator": ">=",
      "target_value": 5,
      "period_start": "2026-06-01",
      "period_end": "2026-06-30",
      "priority": "High",
      "status": "active",
      "notes": ""
    }
  ]
}
```

### Streamlit Cloud 持久化问题

Streamlit Cloud 本地文件在 reboot 后可能丢失。可选方案：

1. 第一阶段：支持上传/下载计划 JSON。
2. 第二阶段：计划也支持写入 Streamlit Secrets 初始模板，但 Secrets 不适合频繁编辑。
3. 推荐阶段：接入 GitHub 文件存储或数据库表，真正持久化。

## 7. 页面设计

### Tab 1：本月行动计划

- 新增任务表单
- 当前任务列表
- 支持编辑、取消、延期
- 支持批量导出 JSON

### Tab 2：下月完成情况

- 选择复盘月份
- 自动计算任务完成情况
- 按顾问、团队、主题汇总
- 展示完成率和未完成差距

### Tab 3：AI 复盘

- 选择某次月会计划
- 展示数据证据
- 生成管理层复盘摘要
- 输出下月建议动作

## 8. 第一版开发范围

MVP 建议只做以下内容：

1. 新增 `执行跟进` Tab。
2. 支持手动添加顾问级任务。
3. 支持指标：新增推荐、新增面试、推面比、一面到Offer、新增Offer、回款金额、总未回款储备。
4. 用本地 JSON 保存任务。
5. 根据已有 v2 数据自动计算完成情况。
6. 输出任务完成表和简短 AI 复盘。

暂不做：

- 权限系统
- 多人协同编辑
- 复杂审批流
- 移动端体验
- 自动写回 Gllue

## 9. 验收标准

- 可以创建 Larry Gao 的月度任务：
  - BD 2 家客户
  - 新增面试 5 个
  - 推面比 50%
  - 新增 Offer 1 个
- 下月选择复盘周期后，系统能自动显示每项实际完成情况。
- 完成率不会超过 100%，比例指标显示清晰。
- 任务与当前 v2 顾问、项目、回款数据口径一致。
- reboot 后至少能通过导入 JSON 恢复计划；后续版本支持更稳定持久化。

## 10. 待确认问题

1. BD 新增客户的准确数据库字段是什么？
2. “新增面试”是否只算一面，还是所有客户面试？
3. “推面比”是推荐到一面，还是推荐到任意面试？
4. Offer 新增是否继续使用当前有效 `Invoice Added` 口径？
5. 执行计划是否需要多人同时编辑？
6. 计划是否要长期留档，用于季度/年度管理复盘？
