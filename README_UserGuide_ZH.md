# 使用手册 —— `aggregateGenCodeDesc`（Python，Copilot+Opus4.7 fork）

这是 Python 版 `aggregateGenCodeDesc` 的面向最终用户的手册。
讲清楚：**什么时候**跑、输入输出**放哪**、12 个（VCS × 访问方式 × 算法）组合**怎么**跑。

- 相关文档：[README_ZH.md](README_ZH.md) · [README_UserStories.md](README_UserStories.md) · [README_AlgABC_ZH.md](README_AlgABC_ZH.md) · [README_Protocol_ZH.md](README_Protocol_ZH.md)

---

## 1. 安装

```bash
# 从本 fork 安装
pip install -e .
# 或者直接跑
python -m aggregateGenCodeDesc --help
```

需要 Python 3.11+。Alg A/B 跑 Git 要 `git` 在 PATH 里；跑 SVN 要 `svn` 在 PATH 里。Alg C 两个都不需要。

---

## 2. 输入

### 2.1 必填参数

| 参数 | 含义 |
|---|---|
| `--repo-url URL` | Git 或 SVN 仓库 URL。**本地**模式下传本地路径或 `file://` URL。 |
| `--repo-branch NAME` | Git 分支名，或 SVN 路径（比如 `trunk`、`branches/rel-1.0`）。 |
| `--start-time ISO8601` | 窗口开始时间，包含（`2026-01-01T00:00:00Z`）。 |
| `--end-time ISO8601` | 窗口结束时间，包含。 |
| `--threshold N` | 0..100 的整数，*Mostly AI* 模式用。 |
| `--algorithm {A,B,C}` | 行来源发现策略（见 [README_AlgABC_ZH.md](README_AlgABC_ZH.md)）。 |
| `--scope {A,B,C,D}` | 文件/路径过滤（见 [README_AlgABC_ZH.md](README_AlgABC_ZH.md)）。 |
| `--gen-code-desc-dir PATH` | 本次窗口对应的 genCodeDesc JSON 文件序列所在目录。看 §2.2。 |
| `--output-dir PATH` | 两个输出产物写到的目录（不存在就新建）。看 §3。 |

### 2.2 `--gen-code-desc-dir` 约定

这个目录里放的是**一个 genCodeDesc JSON 文件序列**，每次版本一个文件，覆盖 `repoBranch` 上 `[startTime, endTime]` 这段窗口。

- **一个目录只允许一种协议版本。** 要么全是 **v26.03**，要么全是 **v26.04**。混着放的话直接退出码 `2`。
- **发现方式**：目录里所有 `*.json` 文件全加载、解析、校验。
- **排序**：按 `revisionTimestamp` 升序（Alg C 用）。Alg A/B 用仓库自己的拓扑序；目录只用来查 `genRatio`。
- **身份校验**：每个文件的 `REPOSITORY.repoURL` + `repoBranch` + `revisionId` 必须和窗口对得上。对不上报错，对应 AC-006-2。
- **算法兼容性**：

  | 算法 | v26.03 | v26.04 |
  |---|---|---|
  | A（实时 blame） | ✅ | ✅ |
  | B（diff 重放） | ✅ | ✅ |
  | C（内嵌 blame） | ❌ 拒绝 | ✅ 必须 |

- **版本缺失策略**：`--on-missing {error,zero}`（Alg C 默认 `error`，A/B 默认 `zero`）。见 AC-006-1。
- **重复 revisionId 策略**：`--on-duplicate {error,last-wins}`（默认 `error`）。见 AC-006-3。
- **时钟漂移策略**（仅 Alg C）：`--on-clock-skew {error,warn}`（默认 `error`）。见 AC-006-4。

### 2.3 可选参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `--protocol-version {auto,26.03,26.04}` | `auto` | 强制指定版本；`auto` 就用第一个文件的版本当基准，其他的必须一致。 |
| `--workdir PATH` | 临时目录 | Alg A/B 在这里克隆/签出远端仓库。Alg C 忽略。 |
| `--blame-whitespace {respect,ignore}` | `respect` | 只影响 Alg A。`ignore` 对应 `git blame -w`。见 AC-004-3。 |
| `--rename-detection {off,basic,aggressive}` | `basic` | 只 Git + Alg A/B。对应 `-M` / `-M -C -C`。 |
| `--commit-patch-dir PATH` | 无 | **只给 Alg B 用。** 事先算好的每个 revision 的 diff 文件放这里，给离线重放用。看 §2.4。 |
| `--log-level {Debug,Info,Warning}` | `Info` | stderr 日志详细程度。见 §2.5。 |
| `--report PATH` | 无 | 在 JSON 输出旁边额外写一份人读的摘要报告。 |

### 2.4 `--commit-patch-dir` 约定（Alg B）

- **只有 Alg B 会消费这个目录。** Alg A、Alg C 会直接忽略（带一条警告）。
- 窗口 `[startTime, endTime]` 内每个 revision 一个文件，命名为 `<revisionId>.patch`，覆盖该 revision 相对于它在 `repoBranch` 上的父提交的完整变更。
- 目录里扫 `*.patch` 文件。
- 顺序：Alg B 按仓库自己的拓扑/父子顺序重放；文件名只是 revision → diff 的映射，不是排序键。
- 缺 revision 走 `--on-missing`；重复走 `--on-duplicate`。
- 这个目录填好之后，Alg B 就可复现、不联网。

### 2.5 `--log-level` 语义

stderr 日志分档，上一档包含下一档的所有内容（档位越高越安静）。

| 档位 | 打什么 |
|---|---|
| `Debug` | 包含 `Info` 的所有内容，**再加内部调试细节**（解析器 token、原始 VCS 命令行、每文件耗时、哈希表统计、被拒绝的候选项）。给工具开发者排查问题用，非常啰嗦。 |
| `Info`（默认） | **文件加载**事件（每个 genCodeDesc / diff 文件的打开、解析、接受或拒绝）、**逐行状态流转**（每行来源查表、Alg C 的 add/delete 集合变化、Alg B 的 diff hunk 行号追踪）和**最终摘要**（分母、三个度量、诊断信息）。 |
| `Warning` | 只打 warning 和 error（缺 revision、revision 重复、时钟漂移、版本混用、降级结果）。不打任何按文件、按行的内容。 |

---

## 3. 输出

`--output-dir PATH` 里会放 **两个产物**：

| 文件（固定名称） | 是什么 |
|---|---|
| `genCodeDescV26.03.json` | 聚合结果，形状跑 genCodeDescProtoV26.03（§3.1）。 |
| `commitStart2EndTime.patch` | `repoBranch` 上 `[startTime, endTime]` 的单个累积 unified diff（§3.2）。 |

两个文件 **Alg A / B / C 都会生成**。即使是 Alg C（不碰 VCS）也会生成 patch——怎么生成的看 §3.2。

### 3.1 `genCodeDescV26.03.json`

形状跑 **[`Protocols/genCodeDescProtoV26.03.json`](Protocols/genCodeDescProtoV26.03.json)**（字段名同、SUMMARY / DETAIL / REPOSITORY 结构同）。聚合结果复用这个协议，这样已经能读版本级 genCodeDesc 的下游工具不用改就能读聚合结果。

度量 → 协议字段映射：

| 协议字段 | 聚合含义 |
|---|---|
| `protocolVersion` | `"26.03"`（**输出信封** 的版本，跟输入 `--gen-code-desc-dir` 的版本无关）。 |
| `codeAgent` | `"aggregateGenCodeDesc"`。 |
| `REPOSITORY.repoURL` / `repoBranch` | 原样抄自 `--repo-url` / `--repo-branch`。 |
| `REPOSITORY.revisionId` | `"aggregate:<startTime>..<endTime>"` —— 标识窗口的合成 id。 |
| `SUMMARY.totalCodeLines` | 分母——窗口内活代码行数。 |
| `SUMMARY.fullGeneratedCodeLines` | `genRatio == 100` 的行数（*Fully AI* 的分子）。 |
| `SUMMARY.partialGeneratedCodeLines` | `0 < genRatio < 100` 的行数。 |
| `SUMMARY.totalDocLines` / `fullGeneratedDocLines` / `partialGeneratedDocLines` | 同上，只统文档文件（markdown 等）。 |
| `DETAIL[].fileName` | 窗口内每个活文件。 |
| `DETAIL[].codeLines[]` / `docLines[]` | 逐行的 `{lineLocation, genRatio, genMethod}`（或者连续行用 `lineRange`），从来源 revision 的 genCodeDesc 拷过来。 |

聚合专属扩展（做为同级顶层 key，只认 v26.03 的老消费者会忽略）：

| 字段 | 含义 |
|---|---|
| `AGGREGATE.window` | `{startTime, endTime}`。 |
| `AGGREGATE.parameters` | `{algorithm, scope, threshold, inputProtocolVersion}`。 |
| `AGGREGATE.metrics.weighted` | `{value, numerator}` — `Σ(genRatio/100) / totalCodeLines`。 |
| `AGGREGATE.metrics.fullyAI` | `{value, numerator}` — `fullGeneratedCodeLines / totalCodeLines`。 |
| `AGGREGATE.metrics.mostlyAI` | `{value, numerator, threshold}` — `count(genRatio >= T) / totalCodeLines`。 |
| `AGGREGATE.diagnostics` | `{missingRevisions[], duplicateRevisions[], clockSkewDetected, warnings[]}`。 |

例子（窗口内 10 行活代码，`genRatio = [100,100,100,100,100, 80,80,80, 30, 0]`，阈值 60）：

```json
{
  "protocolName": "generatedTextDesc",
  "protocolVersion": "26.03",
  "codeAgent": "aggregateGenCodeDesc",

  "SUMMARY": {
    "totalCodeLines": 10,
    "fullGeneratedCodeLines": 5,
    "partialGeneratedCodeLines": 4,
    "totalDocLines": 0,
    "fullGeneratedDocLines": 0,
    "partialGeneratedDocLines": 0
  },

  "DETAIL": [
    {
      "fileName": "src/auth.py",
      "codeLines": [
        {"lineRange": {"from": 1, "to": 5}, "genRatio": 100, "genMethod": "codeCompletion"},
        {"lineRange": {"from": 6, "to": 8}, "genRatio":  80, "genMethod": "vibeCoding"},
        {"lineLocation": 9,                    "genRatio":  30, "genMethod": "vibeCoding"},
        {"lineLocation": 10,                   "genRatio":   0, "genMethod": "human"}
      ]
    }
  ],

  "REPOSITORY": {
    "vcsType": "git",
    "repoURL": "https://github.com/acme/foo",
    "repoBranch": "main",
    "revisionId": "aggregate:2026-01-01T00:00:00Z..2026-04-01T00:00:00Z"
  },

  "AGGREGATE": {
    "window": {
      "startTime": "2026-01-01T00:00:00Z",
      "endTime":   "2026-04-01T00:00:00Z"
    },
    "parameters": {
      "algorithm": "C",
      "scope": "A",
      "threshold": 60,
      "inputProtocolVersion": "26.04"
    },
    "metrics": {
      "weighted":  {"value": 0.77, "numerator": 7.7},
      "fullyAI":   {"value": 0.50, "numerator": 5},
      "mostlyAI":  {"value": 0.80, "numerator": 8, "threshold": 60}
    },
    "diagnostics": {
      "missingRevisions": [],
      "duplicateRevisions": [],
      "clockSkewDetected": false,
      "warnings": []
    }
  }
}
```

### 3.2 `commitStart2EndTime.patch`

从窗口开始前的父提交到窗口末尾 revision 的 **单个累积 unified diff**，作用在 `repoBranch` 上。等价于：

```text
git diff <revJustBeforeStartTime>..<revAtEndTime> -- <scope 路径>
```

- **格式**：标准 unified diff（`diff --git ...` / `---` / `+++` / `@@` hunks）。用 `git apply` 或 `patch -p1` 可应用。
- **范围**：按 `--scope` 过滤（和 JSON 分母的文件范围一致）。
- **重命名/二进制**：重命名检测跑 `--rename-detection`；二进制文件显示为 `Binary files differ`。
- **三个算法都生成**：

  | 算法 | patch 怎么得来 |
  |---|---|
  | A | 直接调 `git diff` / `svn diff`（在工作副本或远端上）。 |
  | B | 把 `--commit-patch-dir` 里的单次 revision diff 按拓扑顺序并聚为一个累积 diff。 |
  | C | 从 v26.04 的内嵌 add/delete 记录合成：把 `[startTime, endTime]` 上累积的 add/delete 状态序列化为 unified diff。不访问 VCS。 |

- **用途**：和 JSON 配对——JSON 回答*"比例多少"*，patch 回答*"到底改了啥"*；两者一起就能审计、复现，不需要再访问仓库。
- **文件头**：patch 首部是一段注释，记录 `repoURL`、`repoBranch`、`startTime`、`endTime`、`algorithm`、`scope`，以及合成 id `aggregate:<start>..<end>`。

退出码：`0` 成功 · `1` 运行时错误 · `2` 输入/校验错误 · `3` 有警告且带 `--fail-on-warn` 的降级结果。

---

## 4. 场景矩阵 —— 12 个组合

轴：**VCS** = `git` | `svn` · **访问** = `local` | `remote` · **算法** = `A` | `B` | `C`。

每个组合都消费同一个 §2.2 里说的 `--gen-code-desc-dir` 序列。

### 4.1 git × local

#### git · local · A（实时 blame）

- **前置**：本地有工作副本；`git` 在 PATH；genCodeDescDir 是 v26.03 或 v26.04。
- **例子**：
  ```bash
  python -m aggregateGenCodeDesc \
    --repo-url file:///srv/repos/foo.git \
    --repo-branch main \
    --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
    --threshold 60 \
    --algorithm A --scope A \
    --gen-code-desc-dir ./gcd/ \
    --output-dir ./out/
  ```
- **局限**：浅克隆会让 blame 失真（AC-005-4）。

#### git · local · B（离线 diff 重放）

- **前置**：工作副本带窗口内完整对象库。
- **局限**：重命名链深时状态会炸（见 README 规模表）。

#### git · local · C（内嵌 blame，仅 v26.04）

- **前置**：**完全不需要 VCS**——`--repo-url` / `--repo-branch` 只用来做校验。`--gen-code-desc-dir` 必须是 v26.04。
- **局限**：正确性完全依赖 codeAgent 写入时的 blame。

### 4.2 git × remote

#### git · remote · A

- **前置**：有网；工具克隆到 `--workdir`（或者配了 provider blame API 就走那个）。
- **例子**：
  ```bash
  python -m aggregateGenCodeDesc \
    --repo-url https://github.com/acme/foo.git \
    --repo-branch main --start-time ... --end-time ... --threshold 60 \
    --algorithm A --scope A \
    --gen-code-desc-dir ./gcd/ \
    --workdir /tmp/agcd \
    --output-dir ./out/
  ```
- **局限**：克隆时间占大头。别用 `--depth`（AC-005-4）。

#### git · remote · B

- **前置**：有网；按窗口内每个 revision 拉 diff。
- **局限**：规模大了受带宽限制（见 README 规模表）。

#### git · remote · C

- **前置**：**完全不访问远端仓库**。传 `--repo-url`/`--repo-branch` 只是为了让结果 JSON 自我标识；工具一次都不会连远端。
- **推荐**：内网隔离 / 批处理场景。

### 4.3 svn × local

#### svn · local · A

- **前置**：工作副本；`svn` 在 PATH。
- **局限**：`svn blame` 对 merge 过来的行会不精确（见 README 的 Git vs SVN 表）。

#### svn · local · B

- **前置**：工作副本；用 `svn diff -rN:M`。
- **局限**：不支持跨文件 move 检测。

#### svn · local · C

- 和 `git · local · C` 一样——不访问 VCS。

### 4.4 svn × remote

#### svn · remote · A

- **前置**：有网；每文件一次 `svn blame URL@REV` 回合。
- **局限**：服务端延迟乘以文件数。`repoBranch` 要传 SVN 路径（比如 `trunk`）。

#### svn · remote · B

- **前置**：有网；`svn diff -rN:M URL`。
- **局限**：窗口大 → 回合多。

#### svn · remote · C

- 和 `git · remote · C` 一样——不访问 VCS。

### 4.5 组合汇总

| # | VCS | 访问 | 算法 | 跑的时候要访问仓库吗？ | 最适合 |
|---|---|---|---|---|---|
| 1 | git | local | A | 要 | 开发迭代 |
| 2 | git | local | B | 要 | 可复现的离线重放 |
| 3 | git | local | C | **不要** | 封闭式 CI |
| 4 | git | remote | A | 要（克隆） | 按需审计 |
| 5 | git | remote | B | 要（fetch） | 带宽 OK 的批处理 |
| 6 | git | remote | C | **不要** | 内网隔离 / 大规模 |
| 7 | svn | local | A | 要 | svn 开发迭代 |
| 8 | svn | local | B | 要 | svn 离线重放 |
| 9 | svn | local | C | **不要** | 封闭式 CI（svn） |
| 10 | svn | remote | A | 要 | svn 按需审计 |
| 11 | svn | remote | B | 要 | svn 带宽 OK 的批处理 |
| 12 | svn | remote | C | **不要** | 内网隔离（svn） |

---

## 5. 校验和错误分类

对应 [README_UserStories.md](README_UserStories.md) US-006：

| 情况 | 参数 | 默认 | 退出码 |
|---|---|---|---|
| 窗口内某 revision 的 genCodeDesc 缺失 | `--on-missing` | `error`（C）/ `zero`（A/B） | 2 / 0 |
| 文件里 `REPOSITORY` 对不上 | — | 一律拒绝 | 2 |
| `revisionId` 重复 | `--on-duplicate` | `error` | 2 / 0 |
| `revisionTimestamp` 非单调（Alg C） | `--on-clock-skew` | `error` | 2 / 0 |
| `genRatio` 超出 0..100 | — | 一律拒绝 | 2 |
| 目录里协议版本混用 | — | 一律拒绝 | 2 |
| Alg C 给了 v26.03 | — | 一律拒绝 | 2 |

---

## 6. 例子

最小封闭式（Alg C，不碰 VCS）：
```bash
python -m aggregateGenCodeDesc \
  --repo-url https://github.com/acme/foo.git --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
  --threshold 60 --algorithm C --scope A \
  --gen-code-desc-dir ./gcd-v26.04/ \
  --output-dir ./out/
```

Git 本地 + 实时 blame（Alg A）：
```bash
python -m aggregateGenCodeDesc \
  --repo-url file:///srv/repos/foo --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
  --threshold 60 --algorithm A --scope A \
  --gen-code-desc-dir ./gcd-v26.03/ \
  --blame-whitespace ignore \
  --rename-detection aggressive \
  --output-dir ./out/
```

Alg B + 预先算好的 diff（不连 VCS）：
```bash
python -m aggregateGenCodeDesc \
  --repo-url https://github.com/acme/foo.git --repo-branch main \
  --start-time 2026-01-01T00:00:00Z --end-time 2026-04-01T00:00:00Z \
  --threshold 60 --algorithm B --scope A \
  --gen-code-desc-dir ./gcd-v26.03/ \
  --commit-patch-dir ./diffs/ \
  --log-level Debug \
  --output-dir ./out/
```

---

## 7. 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 运行时/IO 错误（网络、磁盘、VCS CLI 失败） |
| 2 | 输入/校验错误（参数错、genCodeDesc 错、版本混用、算法与版本不匹配） |
| 3 | 降级结果（有警告且加了 `--fail-on-warn`） |
