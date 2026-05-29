# GPUStack 自定义部署仓库

本项目是在官方 [GPUStack](https://github.com/gpustack/gpustack)（v2.1.2）基础上的二次开发。它新增了模型生命周期自动管理和请求级可观测性，同时保持可平滑同步到后续官方版本的能力。

## 自定义功能（基于官方 v2.1.2）

| 功能         | 关键文件                                          | 描述                                                                                         |
|--------------|-------------------------------------------------|----------------------------------------------------------------------------------------------|
| **自动指标** | `server/auto_metrics.py`, `server/metrics_manager.py`        | 定期收集每个模型的请求指标（延迟、吞吐量、错误率）并写入数据库                                  |
| **自动卸载** | `server/auto_unload.py`                          | 配置超时后自动卸载空闲模型，释放GPU内存                                                        |
| **自动伸缩** | `server/auto_scaling.py`                         | 根据实时请求负载自动扩缩模型副本数量                                                           |
| **请求指标** | `routes/openai.py`                               | 拦截 OpenAI 兼容代理请求，并记录每个请求的延迟和 token 计数                                    |
| **生命周期表字段** | `migrations/…_add_model_lifecycle_fields.py`, `schemas/models.py` | 增加`auto_metrics`、`auto_unload`、`auto_scaling`字段，以及空闲超时/自动伸缩阈值                |
| **ModelScope 缓存** | `config/config.py`, `cmd/start.py`                | 新增 `--modelscope-cache-dir` 标志，支持模型缓存单独挂载到专用磁盘卷                             |
| **部署分数器** | `policies/scorers/placement_scorer.py`                  | 部署时考虑当前模型负载，优化副本分配                                                           |

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
docker compose -f gpustack.custom/docker-compose.server-dev.yaml \
               --env-file gpustack.custom/.env build
```

Dockerfile.custom 会将自定义后端源码和前端打包 dist 叠加在官方 `gpustack/gpustack:v2.1.2` 镜像之上。

## 运行

```bash
docker compose -f gpustack.custom/docker-compose.server-dev.yaml \
               --env-file gpustack.custom/.env up -d
```

## 开发注意事项

- 后端自定义分支：`port/custom-features-v212` —— 基于官方 v2.1.2，16 个文件增加了 726 行
- 自定义 Docker 镜像仅覆盖改动的源码，无须完整重构镜像
- 如需适配新官方版本：修改 Dockerfile.custom 中的 `OFFICIAL_TAG`，rebase 分支，然后重新构建

## 修改原则：让 rebase 到官方变简单

本项目是基于官方 v2.1.2 的二次开发，未来需要 rebase 到更新的官方版本。**所有改动应该以"未来 rebase 成本最低"为首要原则**：

1. **优先新增文件**，而不是修改官方文件。新增文件（如 `server/auto_metrics.py`）零冲突；修改官方文件（如 `routes/openai.py`）每次 rebase 都可能冲突。
2. **必须修改官方文件时，改动越小越好**。不顺手重构、不顺手 cleanup、不调整无关代码风格。
3. **碰到官方的 bug / 不一致时，原则上忍一忍不上游 PR**。除非这个 bug 高频影响我们，否则在自己 fork 里打 patch 比维护 PR 流程划算。本项目不追求把改动推回上游。
4. **想清楚是不是必须改后端**。能在 `gpustack.custom/`（prometheus/grafana/compose/env）里解决的，绝不动 `gpustack/` 子模块。
