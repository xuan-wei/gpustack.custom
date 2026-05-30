# GPUStack 自定义部署仓库

本项目是在官方 [GPUStack](https://github.com/gpustack/gpustack)（v2.1.2）基础上的二次开发。新增模型生命周期自动管理和请求级可观测性，保持可平滑同步到后续官方版本。

> 功能清单、rebase 风险、实测结果等完整文档见 **[fork-notes/v2.1.2.md](gpustack.custom/fork-notes/v2.1.2.md)**。

## 项目结构

```
gpustack-dev/                     # 本仓库（部署编排）
├── gpustack/                     # 子模块：后端（xuan-wei/gpustack, 分支: custom/v2.1.2）
├── gpustack-ui/                  # 子模块：前端（xuan-wei/gpustack-ui, 分支: custom/v2.1.2）
├── gpustack.custom/              # 部署配置（Dockerfile、compose、env、grafana、prometheus）
│   └── fork-notes/               # 各版本自定义功能报告
├── gpustack-data/                # 运行时数据（.gitignore）
└── gpustack-cache/               # 运行时缓存（.gitignore）
```

## 环境

- **Python**：conda 环境 `gpustack`（`conda activate gpustack`）
- **Node**：本地 node 及 pnpm 构建前端
- **pnpm**：必须使用 **8.x**（如 8.15.9）。官方 lock 文件是 lockfileVersion 6.0，pnpm 9+ 会重写整个 lock 文件导致 28000 行无意义 diff，rebase 时必冲突。

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

## 修改原则：让 rebase 到官方变简单

**所有改动应该以"未来 rebase 成本最低"为首要原则**：

1. **优先新增文件**，而不是修改官方文件。新增文件零冲突；修改官方文件每次 rebase 都可能冲突。
2. **必须修改官方文件时，改动越小越好**。不顺手重构、不顺手 cleanup、不调整无关代码风格。
3. **碰到官方的 bug / 不一致时，原则上忍一忍不上游 PR**。除非高频影响我们。
4. **想清楚是不是必须改后端**。能在 `gpustack.custom/`（prometheus/grafana/compose/env）里解决的，绝不动 `gpustack/` 子模块。

> Rebase 高风险文件、必做清单、跨文件耦合等详见 [fork-notes/v2.1.2.md](gpustack.custom/fork-notes/v2.1.2.md) §5–§6。

## 分支与版本管理

子模块（`gpustack`、`gpustack-ui`）统一使用以下规则：

- **活跃开发分支**：`custom/v{版本号}`（如 `custom/v2.1.2`），每个官方版本只保留一个。
- **版本快照 tag**：`custom-v{版本号}`（如 `custom-v2.1.2`），用于对比 `git diff v2.1.2 custom-v2.1.2` 查看该版本的全部自定义改动。
- **squash 前备份 tag**：`backup/pre-squash-v{版本号}-{日期}`，保留逐 commit 开发历史。
- **`main`**：跟踪 upstream，不做自定义开发。

**Rebase 到新版本时**：
1. 在当前 HEAD 打 tag `custom-v{旧版本}`（如已打则跳过）
2. 新建分支 `custom/v{新版本}`，rebase + 开发 + squash
3. 完成后打 tag `custom-v{新版本}`
4. 旧版本分支删掉，只留 tag
