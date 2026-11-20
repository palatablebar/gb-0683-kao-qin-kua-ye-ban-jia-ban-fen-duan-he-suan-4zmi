# 考勤跨夜班与加班分段核算

面向制造企业薪酬核算员，处理采信、判定、核算、复核与归档。

## 启动

```bash
docker compose up --build -d
```

访问 http://localhost:18252 。初次启动自动运行脏样例，可切换 clean.csv、legacy.csv 与 overtime.csv（晚到多留、早退与补卡场景）。顶部“运行批次”会重新计算，同源输入复用批次。

## 业务模块

- 打卡采信：`/m1_ingest`、`/api/m1_ingest`
- 班次日历：`/m2_mapping`、`/api/m2_mapping`
- 跨夜配对：`/m3_versions`、`/api/m3_versions`
- 缺卡复核：`/m4_segments`、`/api/m4_segments`
- 工时切段：`/m5_calculate`、`/api/m5_calculate`
- 薪资对账：`/m6_reconcile`、`/api/m6_reconcile`
- 周期归档：`/m7_archive`、`/api/m7_archive`

## 核心规则

跨夜按班次归属日配对，休息区间先扣除，再按法定日期和工时阈值切分倍率。完整数值、边界和异常定义见 `docs/DATA-DICTIONARY.md`。

晚到或早退后又在当天多留的班次：迟到早退记为纪律异常（金额恒0），多留时间按加班独立计酬，两类责任分列于同一份可付款结果、互不抵减，每条记录附来源行与计划窗口依据。补卡或审批参数变化产生新批次并使旧批次失效，同一凭据重跑不重复付款；行数、时间、金额三重对平方可封存导出，导出时重新对账；替换失败保留旧版结果与原始打卡。页面与导出只呈现当前有效批次的可付款结果。

## 验证

```bash
docker compose exec -T app pytest -q
docker compose config --quiet
```

原始样例在 `sample_data/`。测试在 `tests/`。封存文件是单份CSV，含运行清单、计算证据、隔离原因与对账。复核需提交当前版本，陈旧复核返回409。

## 数据与限制

SQLite保存在records命名卷，普通重启与构建不会清除。确认可丢弃本项目数据后，运行 `docker compose down -v` 再启动可重置。单文件上限2MB；不接入外部业务系统；历史规则由本项目样例定义，不代表实际行业标准。
