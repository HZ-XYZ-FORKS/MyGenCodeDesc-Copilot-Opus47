# MyGenCodeDescBase

- genCodeDesc 的 BASE（基座），用来和各种 CodeAgent 和 LLM 组合做 PlayKata，比如 Copilot+[GPT, Opus, Sonnet]。
  - 意思就是：这个 BASE 里面只放 genCodeDesc 的 WHAT（是什么）和 WHY（为什么），然后针对不同的 CodeAgent 和 LLM 去 fork 出来做 WHEN、WHERE、HOW 的具体实现。
  - 用的方法是 CaTDD（注释驱动的测试先行开发）：
    - UserStory+UserGuide -> AcceptanceCriteria -> TestCase。
    - ArchDesign -> DetailDesign -> Implementation。

- 举个例子：
  - `fork` MyGenCodeDescBase -> MyGenCodeDesc_Copilot_GPT-5.4-Xhigh_Python

---

## ======>>>我们有什么<<<======

- 我们把代码提交到一个已有的 **Git 或 SVN 仓库**——线上的或本地的都行。
  - 每次提交一个新版本之后，一个独立的流程会为这个版本生成一条 `genCodeDesc` 记录。
- `genCodeDesc` 是一种**外挂的、版本级别的元数据**，用来描述一次提交里哪些行是 AI 生成的。
  - 它不是仓库内容——它是 `codeAgent` 在每次提交之后生产出来的。
  - 一个版本一条记录，用 `repoURL + repoBranch + revisionId` 来定位。
  - 每条记录里带着逐行的 `genRatio`（0–100）和 `genMethod`（比如 `codeCompletion`、`vibeCoding`）。
- 两个协议版本：
  - **v26.03** —— 只记 AI 相关的行；blame 信息在分析时从活的 VCS 里现查。
  - **v26.04** —— 增量式 add/delete，内嵌 blame 信息；不用访问 VCS 就能自给自足。
- 三种算法（A、B、C），回答同一个度量问题，但用不同的方法来发现行的来源。
- 细节在这里：[README_Protocol_ZH.md](README_Protocol_ZH.md) | [README_AlgABC_ZH.md](README_AlgABC_ZH.md) | [Protocols/](Protocols/) | [README_UserStories.md](README_UserStories.md) | [README_UserGuide_ZH.md](README_UserGuide_ZH.md)

## ======>>>我们想要什么<<<======

- 我们想精确回答一个问题：

  > **在 `endTime` 这个时间点，活着的代码行里，凡是在 `[startTime, endTime]` 期间被新增或修改过的那些行，有多大比例归功于 AI 生成？**

- 这个度量是基于 `endTime` 时的**活快照**来算的——已删除的行不算，旧版本不算。
- 度量支持**三种模式**，通过阈值参数控制：

  | 模式 | 阈值 | 回答的问题 | 公式（基于窗口内活行） |
  |---|---|---|---|
  | **加权** | 无 | "AI 总共贡献了多少？" | `Sum(genRatio/100) / totalLines` |
  | **纯 AI** | `genRatio == 100` | "有多少行是完全 AI 生成的？" | `Count(genRatio == 100) / totalLines` |
  | **主要 AI** | `genRatio >= T`（比如 60） | "有多少行主要是 AI 生成的？" | `Count(genRatio >= T) / totalLines` |

  举个例子——10 行窗口内活行：5 行 genRatio=100，3 行 80，1 行 30，1 行 0：

  | 模式 | 结果 |
  |---|---|
  | 加权 | (5×1.0 + 3×0.8 + 1×0.3 + 1×0.0) / 10 = **77%** |
  | 纯 AI (==100) | 5 / 10 = **50%** |
  | 主要 AI (>=60) | 8 / 10 = **80%** |

- 我们要一个叫 **`aggregateGenCodeDesc`** 的工具来算这个度量。
  - 语言：**Python**。
  - 输入：`repoURL + repoBranch + startTime + endTime + threshold` + genCodeDesc 元数据目录。
  - 输出：一个目录（`--output-dir`），里面放 **两个产物** —— `genCodeDescV26.03.json`（协议形状的聚合 JSON，包含三种模式的值）和 `commitStart2EndTime.patch`（覆盖窗口的单个累积 unified diff）。
  - 必须支持本 BASE 定义的 Algorithm A/B/C 和 Scope A/B/C/D。
  - **CLI 约定和 12 格场景矩阵（git/svn × local/remote × A/B/C）在 [README_UserGuide_ZH.md](README_UserGuide_ZH.md)里。**
- 这个 BASE 只定义 WHAT 和 WHY。每个 fork 来实现 WHEN、WHERE、HOW。

## ======>>>为什么要有协议 v26.03 和 v26.04<<<======

- **v26.03 存在是因为**：要度量 AI 比例，需要每个版本的元数据，但仓库本身提供不了这个——仓库知道哪些行活着、谁最后改了它们，但它**不知道**一行代码到底是不是 AI 写的。
- **v26.04 存在是因为**：v26.03 在分析时还得依赖活的 VCS blame。把真实的 blame 在写入时就嵌进协议里，v26.04 就让这套文件**自给自足了**——可以在断网、边缘设备、大规模批处理场景下跑，不需要回去访问仓库。
- v26.04 的代价：正确性完全托付给 codeAgent 写入时的 blame。分析时没法再用 VCS 独立验证了。

## ======>>>为什么要有算法 A、B、C<<<======

- **算法 A**（实时 blame）存在是因为 VCS blame 是**最权威的**行来源——正确性保证最强，实现路径最简单。
- **算法 B**（离线 diff 回放）存在是因为有些环境分析时根本没法访问活仓库，而且回放 diff 还能提供 blame 做不到的**历史过程度量**（比如代码翻动率、存活率、写了又删的统计）。
- **算法 C**（v26.04 内嵌 blame）存在是因为它做到了**运行时零仓库访问 + 零 diff 回放**——运行时依赖最轻，代价是正确性全靠 codeAgent 写入时负责。
- 三种算法各自在特定部署场景里不可替代；没有谁是全面碾压的。

## ======>>>我们会碰到什么<<<======

VCS 里会影响行归属的各种情况，每个 fork 都得正确处理。

### 文件级别的情况

| 情况 | 发生了什么 | 对归属的影响 |
|---|---|---|
| **纯改名** | 文件路径变了，内容没变 | blame 会穿透追踪——所有行保持原来的来源。v26.04 没有 DETAIL 条目。 |
| **改名 + 改内容** | 路径变了 + 部分行变了 | 没改的行通过 blame 保持来源。改了的行有新来源（v26.04 里是先 delete 旧的再 add 新的）。 |
| **文件删除** | 文件从仓库里移除了 | 所有行从活快照里消失了——**对度量贡献为零**。v26.04 需要为每一行写 delete 条目。 |
| **文件复制** | 文件被复制到新路径 | 保守做法：副本里所有行归属到复制那次提交。血统模式（可选）：保持原始来源。 |
| **跨目录移动** | 跟改名一样——路径变了 | 跟纯改名一样——blame 会跟着走。 |

### 提交级别的情况

| 情况 | 发生了什么 | 对归属的影响 |
|---|---|---|
| **普通提交** | 增/改/删行 | 直截了当：blame 指向这次提交的变更行。 |
| **合并提交** | 两个分支汇合 | blame 会穿透追到**原始写入那行的版本**，不管合并拓扑怎么绕。 |
| **Squash 合并** | 多个提交压成一个 | 所有行归属到**那个 squash 提交**——原来每个提交的细粒度丢了。genCodeDesc 描述的是 squash 后的整体。 |
| **Cherry-pick** | 把一个提交应用到另一个分支 | 产生一个**新提交**，有新 revisionId。blame 指向 cherry-pick 的提交。两边各自需要独立的 genCodeDesc。 |
| **Revert 提交** | 撤销前一个提交 | 被撤销的行有了**新来源**（revert 那次提交）。如果 AI 行被撤销了，它们就没了。 |
| **Amend / force-push** | 重写了已发布的历史 | 旧的 revisionId **消失了**。为旧版本写的 genCodeDesc 变成了**孤儿**。v26.04 里嵌的 blame 也过时了。 |
| **Rebase** | 在新基点上重放提交 | 每个重放的提交都有**新 revisionId**。所有 genCodeDesc 记录都得重新生成。 |

### 行级别的情况

| 情况 | 发生了什么 | 对归属的影响 |
|---|---|---|
| **行没变** | 跨多次提交文本一样 | blame 继续指向**最初的**来源版本。v26.04 不需要条目。 |
| **AI 行 → 人改了** | 人修改了 AI 生成的行 | **所有权转给人了。** 旧 genCodeDesc 里的 genRatio 不再适用。 |
| **人的行 → AI 重写** | AI 重写了人写的行 | **所有权转给 AI 了。** genRatio 来自新的 genCodeDesc。 |
| **只改了空白** | 缩进、尾部空格之类的 | blame **可能算也可能不算**新提交的，取决于 VCS 设置（`git blame -w`）。需要做策略决定。 |
| **行尾符变化** | CRLF↔LF 转换（比如 `.gitattributes` 改了） | diff 会觉得**每一行**都变了。所有行在一次提交里获得新 blame 来源——genCodeDesc 得描述整个文件。 |
| **相同内容重新添加** | 行在提交 X 里被删了，同样的文本在提交 Y 里又加回来了 | **新来源**（提交 Y）。文本相同不等于归属相同——blame 追踪的是版本，不是内容。 |
| **行在文件内移动** | 剪切粘贴到不同行号 | blame 归属到做移动的那次提交。v26.04 里：旧位置 delete + 新位置 add。 |

### 分支/历史级别的情况

| 情况 | 发生了什么 | 对归属的影响 |
|---|---|---|
| **长生命周期分支** | 分支跟 main 差得很远 | blame 正常工作——追踪每一行到它实际的来源提交，不管在哪个分支。 |
| **窗口内多次合并** | `[startTime, endTime]` 期间合并了好几个分支 | 每行还是只有一个 blame 来源。合并本身不改行内容。 |
| **窗口外的提交** | 一行的来源提交在 `startTime` 之前 | 这行**不算进度量**——它活着，但不是"在窗口内变过的"。 |
| **SVN path-copy** | SVN 的分支/标签机制 | blame 行为取决于 SVN 的 mergeinfo 处理——不如 Git 靠谱。有边界情况。 |
| **SVN mergeinfo** | SVN 追踪合并元数据的方式不同 | `svn blame` 对合并过来的行可能返回不精确的结果。已知限制。 |
| **浅克隆** | `git clone --depth N` 限制了历史深度 | 算法 A：`git blame` 到边界就断了——边界之外的行显示成从边界提交来的（来源错了）。算法 B：深度之外的 diff 拿不到。算法 C：不受影响（自给自足）。 |
| **子模块 / subtree** | 另一个仓库的代码嵌进来了 | 父仓库的 blame **追不进**子模块的历史。子模块有自己的 `repoURL`——需要自己的 genCodeDesc 链。策略决定：算还是不算。 |

### 破坏性 / 边界情况

| 情况 | 发生了什么 | 对归属的影响 |
|---|---|---|
| **丢了 genCodeDesc** | 某个版本的 genCodeDesc 没了 | 算法 A/B：那些行当作 `genRatio=0`（没有归属）。算法 C：**链断了**，结果损坏。 |
| **损坏的 genCodeDesc** | revisionId 或行映射是错的 | 校验规则应该能抓到 `REPOSITORY` 字段不匹配的。行级别的错误是**静默的**。 |
| **重复的 genCodeDesc** | 同一个 revisionId 出现了两条记录 | 行为未定义。聚合器必须检测并拒绝（或取最后一个）。算法 C 特别脆弱——重复的 add 会膨胀存活集。 |
| **时钟偏移** | 提交时间戳不是单调递增的 | 算法 C 按 `revisionTimestamp` 排序。时间戳不单调 → 累积顺序错了 → 存活集算错了。Git 允许任意作者日期。 |

### Git 与 SVN 的差异

上面大多数情况对 Git 和 SVN 都适用，但有些行为差别很大：

| 情况 | Git | SVN | 对 genCodeDesc 的影响 |
|---|---|---|---|
| **改名检测** | 启发式的——`git log -M`、`git blame -C`。如果内容改动太大可能漏掉改名。 | 显式的——`svn move` 是一等操作，一定能追踪到。 | Git：fork 可能需要调 `-M` 的阈值。SVN：改名检测可靠。 |
| **合并提交** | 真正的合并提交，有 2 个以上的父提交。`git blame` 能正确穿透合并拓扑。 | 没有合并提交——合并就是一个普通提交加上 `svn:mergeinfo` 属性。`svn blame` 可能不精确。 | Git：权威。SVN：合并来源的行要谨慎对待。 |
| **Cherry-pick** | `git cherry-pick` 创建新提交。blame 指向 cherry-pick 而不是原始提交。 | `svn merge -c`——行为类似但 mergeinfo 可能干扰 blame。 | 概念一样，但 SVN blame 可能归属到错误的版本。 |
| **Rebase** | `git rebase` 重放提交 → 新的 revisionId。所有 genCodeDesc 必须重新生成。 | **不存在。** SVN 历史不可变。 | Git 独有。SVN fork 可以忽略。 |
| **Amend / force-push** | `git commit --amend`、`git push --force` 重写历史。旧的 genCodeDesc 变成孤儿。 | **不可能。** SVN 版本一旦提交就不可变。 | Git 独有。SVN fork 可以忽略。 |
| **浅克隆** | `git clone --depth N` 限制历史深度。blame 到边界就断了 → 来源错误。 | **不适用。** SVN 检出始终可以通过服务器访问完整历史。 | Git 独有。SVN fork 可以忽略。 |
| **子模块 / subtree** | `git submodule` 或 `git subtree`。父仓库 blame 追不进子模块。 | `svn:externals`——概念类似，语义不同。blame 停留在各自仓库内。 | 都需要独立的 genCodeDesc 链。SVN externals 有额外的路径解析复杂度。 |
| **分支模型** | 分支是轻量引用。分支和合并便宜且频繁。 | 分支是路径拷贝（`/trunk`、`/branches/X`）。分支操作更重。 | SVN：`repoBranch` 映射到路径而不是引用名。fork 需要做规范化。 |
| **Blame 质量** | `git blame` 高度可靠。`-w` 忽略空白。`-C -C` 能检测跨文件移动。 | `svn blame` 基本情况够用。合并多的历史可能不精确。没有跨文件移动检测。 | SVN fork 应该把 blame 可靠性降低作为已知限制记录下来。 |
| **版本标识** | SHA-1/SHA-256 哈希（40/64 个十六进制字符）。全局唯一。 | 顺序整数（1, 2, 3...）。仅在单个仓库内唯一。 | `revisionId` 格式不同。校验规则必须两种都能处理。 |
| **时间戳** | 作者日期可以随意设置（`GIT_AUTHOR_DATE`）。时钟偏移是可能的。 | 服务器分配的时间戳。单调递增（同一服务器内）。 | Git：时钟偏移对算法 C 是真实风险。SVN：时间戳可靠。 |

### 规模 / 性能情况

参考规模：**1K 次提交 × 每次 100 个文件 × 每个文件 10K 行增删**，在 `[startTime, endTime]` 窗口内。

| 维度 | 数值 | 推导 |
|---|---|---|
| 窗口内提交数 | 1,000 | — |
| 每次提交涉及的文件数 | 100 | 总共 100K 个文件-提交对 |
| 每个文件增删的行数 | 10,000 | 每次提交 1M 行条目；窗口内**共 1B 行条目** |
| endTime 时的不同文件数 | ~10,000（上限） | 取决于提交间的文件重叠 |
| endTime 时每个文件的行数 | ~10,000 | 存活集 ≈ **1 亿行**（上限） |
| genCodeDesc 文件大小（每次提交） | ~1M DETAIL 条目 × ~200 字节 ≈ **200 MB JSON** | 1,000 个文件 × 200 MB = 总共 **200 GB** genCodeDesc 存储 |

| 关注点 | 算法 A（实时 blame） | 算法 B（diff 回放） | 算法 C（内嵌 blame） |
|---|---|---|---|
| **VCS 调用** | ~10K 次 `git blame`（每个文件一次）。每次都要走完整历史——**瓶颈**。 | ~1K 次 `git diff`。每次返回 100 文件 × 10K 行 = **每次 diff 1M 行**。 | **零**——不访问 VCS。 |
| **CPU** | 解析 10K 个 blame 输出 × 每个 10K 行 = **1 亿行** blame 要解析。可以按文件并行。 | 1K 个顺序 diff × 每个 1M 行 = **10 亿行** diff 回放。跨提交链的行位置追踪——**没法跨提交并行**。 | 解析 1K 个 JSON × 每个 1M 条目 = **10 亿个 JSON 条目**。集合增删操作：**10 亿次 hash-map 操作**。按文件分片的话可以并行。 |
| **内存** | 一次只处理一个文件的 blame（10K 行）——**很低**（~1 MB）。并行乘上去：100 并发 ≈ ~100 MB。 | 得在 1K 个链式 diff 里追踪行身份。每个文件的状态：10K 行 × 提交链。峰值：大文件高翻动率时 **~10 GB**。 | 存活集：上限 **1 亿个 key** × ~64 字节/key = **~6 GB** 哈希表。加上在飞的一个 genCodeDesc（解析后 ~200 MB）。 |
| **I/O** | 网络：10K 次 blame 请求。本地盘：快。远程 VCS：**延迟受限**（10K 次往返或批量 API）。 | 网络：1K 次 diff 请求。负载：~1K × 1M 行 × ~50 字节 = 线上 **~50 GB** 原始 diff。 | 磁盘：读 1K 个 genCodeDesc 文件，总共 **~200 GB**。顺序扫描——**受磁盘吞吐限制**。SSD：~200 GB / 2 GB/s ≈ 光 I/O 就要 **100 秒**。 |
| **排序** | 不需要——blame 按文件来，跟顺序无关。 | 提交必须拓扑排序。1K 个提交——不费事。 | 1K 个 genCodeDesc 按 `revisionTimestamp` 排序。O(N log N)，N=1K——**轻松**。 |
| **最坏情况** | 10K 个文件 × 深层改名链——blame 得追着 1K 次提交的改名跑。`git blame -C -C` **慢 10 倍**。 | 每次提交改名 100 个文件 → 行位置追踪器得跟 1K 个 diff 里 100K 次改名。状态爆炸。 | 10 亿次集合操作 + 6 GB 哈希表。如果 genCodeDesc 文件有错（重复 key），存活集**静默损坏**。 |
| **缓解措施** | 并行跑 blame（100 并发）。用 `git blame --incremental` 流式处理。缓存结果。跳过上次以来没变的文件。 | 限制窗口大小。流式处理 diff。按文件路径分片回放。预计算文件改名图。 | 按时间顺序流式读 genCodeDesc——别一次加载 200 GB。按文件路径分片存活集。大 JSON 用 mmap。用 SUMMARY 校验条目数。 |
