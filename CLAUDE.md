# GPUStack 自定义部署仓库

本项目是在官方 [GPUStack](https://github.com/gpustack/gpustack)（v2.1.2）基础上的二次开发。它新增了模型生命周期自动管理和请求级可观测性，同时保持可平滑同步到后续官方版本的能力。

## 自定义功能（基于官方 v2.1.2）

> 完整的逐功能 rebase 风险评估、更优实现建议、auto-scaling 实测结果见 **[feature-report/v2.1.2.md](gpustack.custom/feature-report/v2.1.2.md)**（2026-05-30 全量分析 + 双后端实测）。下表是速查。

| 功能 | 关键文件 | 描述 |
|------|---------|------|
| **自动伸缩** | `server/auto_scaling.py`(新) | 按队列深度扩、按预测负载缩；vLLM 用 KV、llama.cpp 用 `--parallel` 槽占用。实测扩/缩/drain 全通过 |
| **自动卸载** | `server/auto_unload.py`(新) | 空闲超时后把 `replicas` 置 0 释放显存 |
| **缩容 Drain** | `server/auto_drain.py`(新) | 缩容选中副本先标 `is_draining`，等网关端点收敛后再删，消除 404 竞态 |
| **运行时指标聚合** | `server/runtime_metrics_aggregator.py`(新) | 抓 worker `/metrics` 聚合成每模型快照（running/waiting/KV/TTFT/TPOT/吞吐） |
| **请求速率指标** | `server/auto_metrics.py`, `server/metrics_manager.py`(新) | 周期写 `last_request_time`、`avg_request_rate/process_rate`（驱动卸载/伸缩） |
| **请求级打点** | `routes/openai.py`(改) | 代理 handler 内联记录每请求延迟/token（建议挪中间件，见报告 §5.1） |
| **运行时负载列** | `hooks/columns/runtime-load-column.tsx`(新), `routes/models.py` 的 `get_runtime_snapshots`(改) | 模型列表实时负载列 + `/v1/models/runtime-snapshots` 端点 |
| **生命周期字段** | `migrations/_2026_04_14_0001_add_custom_v212_fields.py`(新), `schemas/models.py`(改) | 16 个生命周期/伸缩字段 + `model_instances.is_draining` |
| **冷启动自动加载** | `routes/token.py`, `routes/openai.py`(改), `utils/cold_start_gate.py`(新) | 请求到达且 `replicas=0` 时自动加载并长轮询等待就绪；gate 限制并发 waiter |
| **手动跨节点 GPU 修复** | `scheduler/scheduler.py`, `routes/models.py`, `gguf_resource_fit_selector.py`(改) | 手动选 GPU + 取消跨节点时不再被强制 distributed=true（三文件耦合，见报告 §3）|
| **绝对显存范围** | `utils/gpu_memory_range.py`(新), `vllm_resource_fit_selector.py`, `worker/backends/vllm.py`(改) | 用绝对 GiB 上下限反推 vLLM `--gpu-memory-utilization` |
| **放置打分** | `policies/scorers/placement_scorer.py`(改) | 非 Apple GPU 优先（×0.95 惩罚） |
| **网关指标 scrape** | `cmd/prerun.py`(改) + `gpustack.custom/` | Prometheus 追加 Higress 网关 job，给 llama.cpp 补请求/延迟指标 |
| **GGUF 兼容修复** | `routes/benchmarks.py`, `worker/benchmark/runner.py`, `worker/backends/base.py`(改) | GGUF tokenizer 源推导、llama.cpp 拆 `--flag=value`（均为通用 bug，宜上游 PR）|

> ⚠️ ModelScope 缓存改为由 `gpustack.custom/entrypoint-custom.sh` 做软链，**不再**改 `config/config.py`/`cmd/start.py`。

## 项目结构

```
gpustack-dev/                     # 本仓库（部署编排）
├── gpustack/                     # 子模块：后端分支（xuan-wei/gpustack, 分支: port/custom-features-v212）
├── gpustack-ui/                  # 子模块：前端分支（xuan-wei/gpustack-ui）
├── gpustack.custom/              # 部署配置（Dockerfile、compose、env、grafana、prometheus）
├── gpustack-data/                # 运行时数据（已加入 .gitignore）
└── gpustack-cache/               # 运行时缓存（含 model scope 缓存，已加入 .gitignore）
```

## 环境

- **Python**：conda 环境 `gpustack`（`conda activate gpustack`）
- **Node**：本地 node 及 pnpm 构建前端

## 构建

### 前端（gpustack-ui）

```bash
cd gpustack-ui
pnpm install
npm run build        # 输出到 gpustack-ui/dist/
```

### Docker 镜像

镜像构建目录为仓库根目录，请在仓库根目录执行：

```bash
# server（本机）
docker compose -f gpustack.custom/docker-compose-server.yaml \
               --env-file gpustack.custom/.env-server-dev build
# worker（远程节点同样命令换 worker 文件）
docker compose -f gpustack.custom/docker-compose-worker.yaml \
               --env-file gpustack.custom/.env-worker-dev build
```

Dockerfile.custom 会将自定义后端源码和前端打包 dist 叠加在官方 `gpustack/gpustack:v2.1.2` 镜像之上。

## 运行

```bash
docker compose -f gpustack.custom/docker-compose-server.yaml \
               --env-file gpustack.custom/.env-server-dev up -d
```

## 开发注意事项

- 后端自定义分支：`port/custom-features-v212` —— 基于官方 v2.1.2，35 个文件约 +2906 行（11 个新文件零冲突 + 24 个改官方文件）
- 自定义 Docker 镜像仅覆盖改动的源码，无须完整重构镜像
- 如需适配新官方版本：修改 Dockerfile.custom 中的 `OFFICIAL_TAG`，rebase 分支，然后重新构建

## 修改原则：让 rebase 到官方变简单

本项目是基于官方 v2.1.2 的二次开发，未来需要 rebase 到更新的官方版本。**所有改动应该以"未来 rebase 成本最低"为首要原则**：

1. **优先新增文件**，而不是修改官方文件。新增文件（如 `server/auto_metrics.py`）零冲突；修改官方文件（如 `routes/openai.py`）每次 rebase 都可能冲突。
2. **必须修改官方文件时，改动越小越好**。不顺手重构、不顺手 cleanup、不调整无关代码风格。
3. **碰到官方的 bug / 不一致时，原则上忍一忍不上游 PR**。除非这个 bug 高频影响我们，否则在自己 fork 里打 patch 比维护 PR 流程划算。本项目不追求把改动推回上游。
4. **想清楚是不是必须改后端**。能在 `gpustack.custom/`（prometheus/grafana/compose/env）里解决的，绝不动 `gpustack/` 子模块。

## Rebase 指引：重点盯这几个文件

完整分析见 [feature-report/v2.1.2.md](gpustack.custom/feature-report/v2.1.2.md)。rebase 到新官方版本时，**自动 merge 不可信**，重点人工核对：

**🔴 高风险（改了官方热点文件的控制流/算术）**
- `routes/openai.py` —— 冷启动 + 请求打点两簇，含整函数重写 `get_running_instance`
- `policies/candidate_selectors/gguf_resource_fit_selector.py` —— pre-check 循环重构 + `_should_skip` 改了既有 `if`（守卫易被自动 merge 静默丢弃）
- `policies/candidate_selectors/vllm_resource_fit_selector.py` —— 5 处显存算术替换散落 3 方法
- `server/controllers.py` —— `sync_replicas` 缩容分支改为标记 draining
- 前端 `hooks/use-models-columns.tsx` / `components/table-list.tsx`

**必做项**
1. **迁移链**：`migrations/_2026_04_14_0001_add_custom_v212_fields.py` 的 `down_revision`（当前 `8ad0f94c92e8`）重指向新官方 head，确认无同名列。
2. **三文件耦合修复**整体校验（手动跨节点 GPU）：`scheduler.py` 删除块没「复活」、`gguf_selector` 两个 `and distributed_inference_across_workers` 守卫还在、`models.py::validate_gpu_ids` 条件还在。
3. **前端默认值**：`forms/index.tsx` 的 `distributed_inference_across_workers: false` 易被官方默认 `true` 覆盖回去。
4. **`metrics_config.yaml`**：grep 官方是否新增自己的 `llama.cpp:` 映射块（撞 key）。
5. 升级后跑一遍 [feature-report/v2.1.2.md](gpustack.custom/feature-report/v2.1.2.md) §2 的双后端 auto-scaling 闭环冒烟测试。

> 降低未来 rebase 成本的重构建议（挪中间件、合并冷启动逻辑、抽前端生命周期列等）见报告 §5；可上游 PR 的通用 bug 修复见内存 `project_upstream_pr_backlog`。
