---
title: Agent SDK 供应商接入 — 剩下的边界工作还值得做吗？
status: draft
revision: v1
author: zejiangg, with Kiro
created: 2026-09-08
last-audited: 2026-09-08
audited-at: 575a8390e
doc-pr:
implementation-prs: []
tracking-issues: []
supersedes: []
superseded-by: []
translation-of: rfc-agent-sdk-provider-onboarding.md
translates-revision: v1
---
# RFC：Agent SDK 供应商接入 — 剩下的边界工作还值得做吗？

- 状态：草稿。这是一份**决策文档**，不是设计文档。它回答一个问题：
  [`rfc-crew-agent-sdk-boundary.md`](rfc-crew-agent-sdk-boundary.md)
  剩下的 PR 该不该做；并解答那份 RFC 留下的三个未决问题。
- 本文是 [`rfc-crew-agent-sdk-boundary.md`](rfc-crew-agent-sdk-boundary.md)
  的配套文档。文中写作 §N 的小节引用均指那份 RFC，除本文另有说明。
- 本文每个数字都是实测的，并且**每个数字的出处都是一张标注了测量提交的表格**。
  正文确实会重复那几个关键数字（见 §2、§3.4、§7）。那些是**引用**，不是独立的测量：
  §3.1、§3.3、§3.4 的表格才是权威；改了表格，就必须在同一个 commit 里
  更新引用它的正文。
- 这是英文原文 [`rfc-agent-sdk-provider-onboarding.md`](rfc-agent-sdk-provider-onboarding.md)
  的中文版，翻译的是它的 `revision: v1`（见本文 front matter 的 `translates-revision`）。
- **维护规则**：英文版每次改动，必须在**同一个 commit** 里更新本文并同步
  `translates-revision`。做不到就删掉本文，不要留一份会烂掉的翻译。
  两者的 `translates-revision` 与英文 `revision` 不一致时，本文即视为过期：
  以英文版为准，并且这个不一致是**可检测的**，不是靠一句"以英文为准"糊过去。
- 维护人：本文档的作者（见 front matter `author`）。

## 1. 问题，以及判断它的规则

边界 RFC 的既定目的是让新增一个 agent 供应商变便宜。本文用来判断它的规则很直白：

> 如果重构之后接入一个供应商的成本和重构之前一样，那就不要重构。把原因记下来，
> 直接开始加供应商。

所以要量的不是"去掉了多少耦合"，而是**加第五个供应商的人要打开多少个文件**——
在每个剩余 PR 之前和之后各是多少。耦合下降但这个数字不变，那是有价值的工作，
只是理由换了一个；换了理由就必须按那个新理由重新论证。

## 2. 答案

**按接入成本这个理由：不做。** 剩下的六个 PR 把"可选且已接入权限路由"的接入成本
从 38 个文件变成 37 个。就一个文件，而且它是搬家，不是消失。

原因是 RFC 没有写出来的一个事实：**认证是接入成本的大头，而这一摞 PR 里没有一个
去掉它。** 其中有两个只是把其中一部分搬了家，那不是同一件事，对供应商没有任何好处
（见 §3.3、§3.4）。§4 的 non-goal 2 已经明说了——host contract 的 seam 不在范围内——而
bucket 3《Identity and auth》并不是被提前塞进 PR 3 的那两个 contract 之一。§10
把每一处认证面都当成要**保住的不变量**，不是要建的 seam。

真正能动这个数字的改动根本不在这份 RFC 里。一个认证 seam——driver 上一份声明，
用 §5.3 的"靠存在性检测"的风格——一次性花大约 20 个文件，就把新供应商的认证成本
从 24 个文件降到 2 个。它不依赖 PR 2 到 PR 6 中的任何一个，今天就能落在 `main` 上。

结论，论证见 §7：**按接入成本这个理由停掉边界这一摞，先做认证 seam，然后开始加
下一个供应商。**

## 3. 测量

### 3.1 今天加一个供应商要花多少

测于 `575a8390e`，2026-09-08。

| 落地状态 | 文件数 | 含义 |
|---|---|---|
| 休眠：已知但不可选 | 20 | 地板。词汇表、spawn 路径、帧语料、host contract 列、安装探测、parity 测试 |
| 可选且已接入权限路由 | 38 | 再加工具权限路由、凭据地板、沙箱掩码、面板 caveat 和 13 个语言文件 |
| 真正接上每一个宿主面 | 49 | 再加 dashboard、MCP gateway、readiness 和 doctor 的外溢，即 §7 那份接入文档所说的第 7 阶段 |

38 这个数字才是诚实的对比点，因为这是供应商必须走到的、可用的状态。它由接入 Codex
的四个已合并 PR 推出——一个休眠 seam、一条强制的工具权限路由、一个探测 caveat、
一个 host contract 列——四者并集是 58 个不同文件，减去只用于搭建这些闸门本身的部分。

有两项义务是 Codex 落地**之后**才出现的，现在算在 20 个文件的地板里：
`test/fixtures/acp_frames/` 下的按后端分目录的帧重放语料，其闸门
`test_acp_frame_replay.py` 是**硬失败而不是跳过**；以及
`docs/system-specs/modules/agent-host-contract.md` 里按后端的那一列，由
`test_agent_host_contract_parity.py` 强制。也就是说，在边界工作进行期间，
接入成本是**变贵了**，不是变便宜。

### 3.2 PR2a 和 PR3a 并没有落地

本文的任务说明要求基线假设 PR2a（`EVENT_*` 常量搬到 `agent_sdk/events.py`）和
PR3a（`acp_backends`、`acp_tool_gate` 搬进 `agent_sdk/`，剩下的身份判断改成能力提问）
正在进行中并且会落地。

测于 `575a8390e`：两个都没有。不存在 `agent_sdk/events.py`；所有 `EVENT_*` 常量
仍在 `src/kiro_crew/acp/types.py`，而 `src/kiro_crew/providers/base.py` 仍在
连同 `LLMEvent = AcpEvent` 别名一起把它们重新导出。
`src/kiro_crew/acp_backends.py` 和 `src/kiro_crew/acp_tool_gate.py` 仍在包顶层。
§PR 3 列出的六处身份判断全都还活着，分别在 `src/kiro_crew/config/loader.py`、
`src/kiro_crew/dashboard/chat_handlers.py`、
`src/kiro_crew/dashboard/chat_runner.py` 和 `src/kiro_crew/knowledge/llm_pool.py`。
还有 RFC 没有列出的两处也活着，都在
`src/kiro_crew/dashboard/handlers/agents.py`——一处读 `provider.is_claude_backend`，
另一处在配置层与 `ACP_BACKEND_CLAUDE` 比较。所以活着的总数是八处，不是 §PR 3 说的六处。

**这个假设不花任何代价，而这本身就是结论。** 两者都不从接入清单里去掉任何一个文件。
PR2a 搬的是供应商从来不会去加的常量。PR3a 只是给供应商照样要改的两个文件换了路径。
无论怎么算，基线都是 20 / 38 / 49。

### 3.3 逐 PR 的增量

测于 `575a8390e`，2026-09-08。(a)、(b) 两列都是"可选且已接入权限路由"的计数，
除该行另有说明。(d) 列数的是这个 PR 自己要动的文件数；当该 PR 是迁移波次时，
取自边界闸门自己的基线。

| 剩余 PR | (a) 之前 | (b) 之后 | (c) 掉了哪些文件，为什么 | (d) 这个 PR 自身的成本与风险 |
|---|---|---|---|---|
| **PR2b/2c** — 剩下的类型：`AgentEvent` 及其兼容层、`ApprovalToken`、错误分类 | 38 | 38 | **一个都没掉。无接入价值——纯基础设施。** 供应商从来不定义事件类型 | **33 个文件。** 19 个文件里 201 处事件字段读取，最重的是 `src/kiro_crew/dashboard/chat_runner.py`；再加 31 个文件里 145 处 approve/reject 调用点。RFC 当时测的是 17 个文件里的 131 处——这个面自那以后**长了约一半**。**风险：高。** §10.1 把 `ApprovalToken` 定为安全边界，§7 也警告过：丢掉 `raw_tool_params` 而不带上它的派生成员，会把每一次 shell 调用送进默认拒绝。它**是为了**：类型归属——让 SDK 而不是 `src/kiro_crew/providers/base.py` 来定义消费者读到的事件 |
| **PR3b** — 能力机制的剩余部分，加上两个被提前的 host contract | 38 | 38 | **一个都没掉。无接入价值——纯基础设施。** §PR 3 是把每个能力集合**翻译**成"`SessionCapabilities` 上的一个语义提问"。按供应商做成员判断这件事一字不改地活下来，只是换了拼法 | **6 个文件、7 处**，再加搬两个叶子模块、并把协议穿进每一条 session 构造路径。**风险：中高。** §10.7 会把登出回收集合的极性反过来；弄反了会让宿主登出去回收一个外部供应商的活子进程。它**是为了**：归属清晰——按 id 分派的表搬进边界内，policy 模块不再从边界外读叶子的表 |
| **PR4** — supervisor 接过生命周期 | 38 | 38 | **一个都没掉。无接入价值——纯基础设施** | **9 个在基线里的文件、24 条边**，以 `src/kiro_crew/session.py` 为首。**风险：中**——这次搬迁必须带上 kill-tree 辅助函数和受管 agent 标记，而工作类清扫是把它们当**安全**输入用的，不只是共享代码。它**是为了**：PID 归属和消环。它便宜的那一半已经落地了 |
| **PR5 第 1 波** — `dashboard/` | 38 | 38 | **一个都没掉。无接入价值——纯基础设施。** 在"真正接上"清单里的那几个 dashboard 文件，需要的是按供应商的**行为**，不是一个 ACP import；改导入路径，分支还留在那里 | **17 个文件、26 条边。风险：低到中。** 每一波还要删掉自己是最后读者的那些 PR 2 兼容层。它**是为了**：import 卫生 |
| **PR5 第 2 波** — `messaging/` 和各传输层 | 38 | 38 | **一个都没掉。无接入价值——纯基础设施。** 任何落地状态下都没有 channel 模块在接入清单上 | **8 个文件、12 条边。风险：低。** 它**是为了**：import 卫生 |
| **PR5 第 3 波** — `apps/`、`workflows/`、`knowledge/` | 38 | 38 | **一个都没掉。无接入价值——纯基础设施** | **8 个文件、10 条边。风险：低**，而且里面带了一处真实的安全清理：`src/kiro_crew/knowledge/llm_pool.py` 不再从包外读一个私有 ACP 属性。它**是为了**：import 卫生 |
| **PR5 第 4 波** — `cli_*`、`config/`、`platform/`、`eval/`、`connections/`、顶层 | 49（真正接上） | 47（真正接上） | **两个文件，而且是整摞里唯一真实的接入收益。** `src/kiro_crew/config/loader.py` 会掉，**前提是**它那处 Claude 比较变成供应商在声明自己的地方回答的一个能力。`src/kiro_crew/cli_doctor.py` 在同样前提下会掉。两者都取决于 PR3b 的翻译是否真的与供应商无关；如果那个能力在调用点仍然需要按供应商分支，这一行也是零 | **25 个文件、58 条边**——最大的一波，也是 RFC 自己说的兜底波。**风险：中高**——它管着 `src/kiro_crew/session.py` 以及从它拆出去的那些模块。它**是为了**：import 卫生，外加那两处分支删除 |
| **PR6** — 封上边界 | 38 | 37 | **一个文件。** `src/kiro_crew/providers/acp.py` 掉了，因为 PR 6 删掉它的兼容面，供应商标签分支搬进 `src/kiro_crew/agent_sdk/drivers/acp.py`，而后者已经在清单上。mirror 注册表**不会**掉——它只是换路径，照样要改 | 各波之后基线剩下的部分，加上删兼容模块、搬 mirror 树、更新被钉住的豁免集合测试。边界外仍有 28 个模块从 `kiro_crew.providers` 导入。**风险：高，而且这是唯一不可逆的一步。** 它还开不了工：§12.5 的 mirror 归属问题卡着它，而本文 §4 回答了那个问题。它**是为了**：import 卫生的收尾 |

**整摞合计：可选且已接入权限路由 38 → 37。真正接上 49 → 46，且这是最好情况，
其中一个还取决于 PR3b 尚未做出的决定。** 大约是接入成本的 6%，代价是六个 PR、
约 90 个文件、约 106 条 import 边。

### 3.4 成本到底在哪

把 38 个文件的"可选且已接入权限路由"清单按每个文件**关于什么**来分类。
测于 `575a8390e`，2026-09-08。

| 类别 | 文件数 | 占比 |
|---|---|---|
| **认证** — 凭据地板、沙箱掩码、权限路由、安装与 doctor 探测、面板的登录 caveat | **21** | 55% |
| 协议与类型 — id 词汇表、供应商标签、帧语料、mirror 注册表、能力集合成员判断 | 12 | 32% |
| 混合 — spawn 路径、contract 与 parity 文档 | 4 | 11% |
| 都不是 — 格式化 ratchet | 1 | 3% |

去掉"混合"和"都不是"两行，认证占可分类成本的 **21 / 33，即 64%**。
在"真正接上"的清单上是 **24 / 49**。这 21 个里有 13 个是语言文件，
承载的是同一句话：Codex 自己登录。

在 host contract 本身里，**九个 bucket 中有四个是认证**：3 Identity and auth、
4 Sandbox、7 Security and permission parity、8 Auxiliary runtimes。

**剩下的 PR 一个都不去掉这些，而且 RFC 自己说了。** 其中有两个确实**碰**到了：
§PR 3 把 `ACP_BACKENDS_KIRO_IDENTITY_STORE` 翻译成一个能力提问，并且必须给
`src/kiro_crew/acp_tool_gate.py` 一个明确的归属。但两者都只是把按供应商的那个条目搬家，
不是让它消失——这正是 §3.3 给它们记零的原因：供应商照样要声明登出回收的成员身份，
照样要加一行凭据掩码，只是换了路径。§4 的 non-goal 2 把 host contract
的 seam 工作（含沙箱委派）排除在外；被提前塞进 PR 3 的两个 contract 是按 session 的
MCP 注入和 transcript 归属，都不是认证；bucket 3 出现在 RFC 的 deferred 清单里。
§10.2 说拒绝规则的对等"属于 host contract，不属于 SDK"。§10.5 要求凭据擦除必须
跟着 spawn 代码走，而不是在边界之上重新推导。§10.8 让沙箱委派保持 fail-closed 原地不动。

所以这份 RFC 按写成的样子，达不到它自己声明的接入目标。这不是"差了一点"的问题——
成本的大头落在 RFC 明确宣布不在范围内的区域里。

## 4. PR 6 之后 `providers/mirrors/` 放在哪

### 4.1 结论

**`src/kiro_crew/agent_sdk/mirrors/`，在 PR 6 开工之前用单独一个 commit 搬过去**——
而且按 §7 的结论，这件事并不急，因为在真的动 PR 6 之前没有任何东西迫使它搬。
今天的 `src/kiro_crew/providers/mirrors/` 是一个能正常工作的状态，不是在滚利息的债。

一个 mirror 把一份 agent spec 投影到一个宿主的原生配置上。这是 driver 的活，
而这正是 §12.5 已经记下来支持这个选项的理由。§12.5 同时记下的反方理由——
这些裁决编码了按宿主的**决定**，不该让 driver 自由重述——的答案是：
把裁决词汇表和注册表继续共享在 `mirrors/` 内部，而不是按 driver 拆开。

第三个候选（每个 driver 一个 mirror 文件）没有指代对象。`drivers/` 是每个
harness **家族**一个模块，今天只有一个。Claude 不是一个 driver，它是 ACP driver
服务的一个后端。四个 mirror 条目都属于那一个 driver，所以"每 driver 一个文件"
就会是同一个文件装四个——那就是共享包换了个路径。

### 4.2 两个前置条件，都已验证

两个都不是可选的，而且正是 §12.5 警告"不要在 PR 6 里才发现"的那种活。

**mirror 的 ACP import 必须先改成函数内导入。**
`src/kiro_crew/providers/mirrors/claude_code.py` 在模块级从 `kiro_crew.acp` 导入
session-MCP 翻译器，而这个包自己的 `__init__` 通过注册表急切地把它拉进来。
把它搬到 `agent_sdk/` 之下，就会在 SDK 树里放一个模块级 ACP import，
而**目前没有任何东西能抓到这一点**。边界闸门抓不到，因为 `agent_sdk/` 是整树豁免的。
被钉住的测试 `test_agent_sdk_provider_identity.py` 也抓不到：它的子进程导入的是
`kiro_crew.agent_sdk.provider_identity` 这一个具体模块，所以一个没有对外导出的
`agent_sdk.mirrors` 子模块即使带着急切的 ACP import，也照样让它保持绿色，
而每一个真正导入 mirror 的消费者都会开始加载 ACP 包。这是一条**没有被覆盖**的不变量，
不是一条被守住的。所以 PR 6 要做的是两件事而不是一件：把 import 推迟到需要它的方法里，
和 `src/kiro_crew/agent_sdk/drivers/acp.py` 里其他每个函数一样；**并且**把那个探测
扩展到搬过去的 mirror 包，让这条不变量真正被强制。

**唯一的生产调用方也必须改成函数内导入。**
`src/kiro_crew/acp/client.py` 在模块级导入 mirror 查找函数。mirror 一旦搬到
`agent_sdk/` 之下，这就让地基急切地导入 SDK——正是 §5.1 的分层图禁止的反向。

还有第三个事实，让"让 `providers/` 只作为 mirror 层活下来"这个选项比看上去更差。
mirror 包今天能被导入，靠的只是加载顺序：兼容层的 `__init__` 先把 ACP 包拉进来，
所以等 mirror 包自己的包体运行时，环已经解开了。删掉兼容层的重新导出——
而这正是 PR 6 要做的——顺序就反过来，此时单独执行
`import kiro_crew.providers.mirrors` 会抛出"部分初始化模块"的 `ImportError`。
这一点在一份树的副本上复现过。所以那个选项也不是纯删除：它需要同样的 import 推迟，
而且它额外保留了第三棵豁免树，这会让 PR 6 自己"缩到两棵树"的说法变成假的；
它还让 forbidden roots 列表自相矛盾——`kiro_crew.providers` 仍被禁，
而 `kiro_crew.providers.mirrors` 是一个活层的正规归属，配上只能缩小的基线和
没有单行豁免标记，于是未来任何一个非豁免的 mirror 查找消费者都完全无路可走。

### 4.3 PR 6 的删除退出条件变成什么

替换 §PR 6 里那两条以 mirror 为条件的退出条件：

- `src/kiro_crew/providers/` 整包删除，含 `mirrors/`，且后者已在**更早的**
  commit 里搬到 `src/kiro_crew/agent_sdk/mirrors/`。
- 闸门的豁免集合恰好是 `agent_sdk/` 和 `acp/`，被钉住的豁免集合测试在同一个
  commit 里更新。"缩到两棵树"这句话按字面变成真的。
- 搬过去的 mirror 的 ACP import 是函数内的，并且"不急切加载 ACP"的探测被
  **扩展到导入搬过去的 mirror 包**，让这条不变量真正被强制，而不只是恰好没被违反。
- `src/kiro_crew/acp/client.py` 的 mirror 查找是函数内的，地基不急切加载 SDK。
- forbidden roots 列表去掉 `kiro_crew.providers`，而目前断言该 root 存在的那个测试
  被重写，而不是删掉。

还有两项义务是现有退出条件在**任何一个**选项下都没覆盖的：

- `src/kiro_crew/acp/session_provider.py` 从 `src/kiro_crew/providers/base.py`
  导入 cancel-outcome 和 provider 类型。删那个模块之前，这些类型必须先有新家。
  它在豁免树里，所以闸门从来没报过它。
- `scripts/check_agent_sdk_boundary.py` 里有两条注释，就"`providers/` 是否计划删除"
  互相矛盾。不管选哪个方案，其中一条必须改。

## 5. 认证 seam

### 5.1 今天一个供应商为认证要动什么

测于 `575a8390e`，2026-09-08，针对自带登录、不需要产品内登录 UI 的供应商——
也就是 Codex 那个形状。

| 区域 | 文件 | 认证特有的改动 |
|---|---|---|
| 凭据地板 | `src/kiro_crew/security/paths.py` | 凭据叶子、它的 `$HOME` 覆盖锚点、以及一个已解析根字段 |
| 适配器自己的令牌 | `src/kiro_crew/acp_tool_gate.py` | 从 OS 掩码里排除的那一个叶子，否则子进程读不到自己的令牌 |
| 登出策略 | `src/kiro_crew/acp_backends.py` | 在不在登出回收集合里，在不在 pod home 重映射里 |
| 沙箱 | `src/kiro_crew/sandbox.py` | 凭据掩码是否适用；若它存在 crew home 下则还有隐藏叶子 |
| 安装探测 | `src/kiro_crew/agent_sdk/backend_install.py` | 一个探测条目，以及"不探测凭据"这一记录在案的决定 |
| driver 解析器 | `src/kiro_crew/agent_sdk/drivers/acp.py` | 探测调用的那个解析器 |
| 过期信号 | `src/kiro_crew/acp/client.py` | auth-required 抛出点和未登录判定 |
| 过期信号 | `src/kiro_crew/acp/session_provider.py` | 死掉的子进程翻译成 auth-required |
| doctor | `src/kiro_crew/cli_doctor.py` | 一行登录状态，或者"不要这一行"这个记录在案的决定 |
| host contract | `docs/system-specs/modules/agent-host-contract.md` | bucket 3 那一列。硬闸门 |
| 面板 | `website/src/pages/developer/AgentBackendTab.tsx` | caveat 链——用户唯一能知道这个供应商要单独登录的地方 |
| 面板文案 | `website/src/i18n/locales/` 下 13 个语言文件 | 那句 caveat |

**24 个文件。** 需要产品内交互式登录的供应商——KAS 那个形状——再加 17 个：
整个 `src/kiro_crew/auth/` 包、它的 dashboard handler 和路由、前端 API client，
以及一个登录门组件。**41 个文件**，而且此时那 13 个语言文件承载的是每个约 52 个 key
而不是一个。

这个数字背后有两个结构性事实。树里没有任何一个按供应商的认证对象：每一处改动
都是改一张共享表，或者改宿主模块里的一条 `if` 链。以及
`docs/system-specs/modules/harness-onboarding.md` 列了七个接入阶段，
**没有一个是认证**——它只作为某一阶段里的一句 caveat、以及另一阶段里没有命名的
"外溢"出现。

这不是空想的证据：把 Claude Code 变成可选的那个 PR 动了**零个**认证文件。
它的 OAuth 令牌是后来才被加到敏感路径地板上的，而且是由 **Codex** 那个 PR 加的；
那个 PR 自己的正文记着：在 Claude Code 已经作为可选后端发货的同时，
一个 agent 可读的活 OAuth 令牌一直没在地板上。

### 5.2 提案

一份声明加一个可选协议，用 §5.3 的风格——小的强制核心，加
`runtime_checkable` 的可选协议，用 `isinstance` 检测而不是读一个布尔标志。

新增 `src/kiro_crew/agent_sdk/host_auth.py`：

- **`AgentAuthDeclaration`**（driver 必需）：它存哪些凭据叶子、哪些 `$HOME`
  覆盖环境变量会挪动它们、它自己的子进程仍必须读的那一个叶子、登录补救字符串、
  宿主登出是否可以回收它的子进程、以及它的授权来自哪里。
- **`AgentInteractiveLogin`**（`runtime_checkable`，可选）：流程清单，以及
  begin / poll / logout。自带登录的供应商干脆不实现它，此时 §5.3 的规则生效——
  这种"没有"在类型系统里是看得见的，而不是变成一个静默的空实现。

其余都由此派生。凭据地板、沙箱掩码、以及适配器自有叶子的排除项都改成读这份声明
而不是读字面量，于是**宿主继续决定什么被围起来，供应商只声明自己存了什么**。
这个分工很重要：一个能改掩码的 driver 就能把自己解掩。

前端那半是同一个动作。`GET /api/acp-backends` 的返回体多一个 auth 对象，
面板的 caveat 渲染收到的东西。选项列表**已经**是数据了——候选项是服务端答案的并集，
显示名回落到线上 id——所以这是把一个已有模式收尾，不是开一个新模式。

### 5.3 成本，以及买到什么

**20 个文件：15 个源码与文档，5 个测试。** 之后，一个自带登录的新供应商的认证成本
是 **2 个文件**——driver 里的声明，以及 parity 测试要求的 bucket 3 那一列。
接下来的三个数字落在两个不同的基数上，所以分开陈述，不合成一个数。在 §5.1 那份
**24 个文件的认证清单**里，22 个不再承载认证改动；其中只为认证而改、别无他用的那 2 个
——`src/kiro_crew/security/paths.py` 和 `src/kiro_crew/acp/session_provider.py`——
彻底离开接入清单。在 §3.1 那份 **38 个文件的"可选且已接入权限路由"清单**里，按下面
"服务端渲染补救字符串"这个选择，**有 16 个文件彻底离开**：13 个语言文件、
`src/kiro_crew/security/paths.py`、`website/src/pages/developer/AgentBackendTab.tsx`
及其测试。那份清单上其余的认证文件会留下，因为每一个同时还承载着与认证无关的接入改动。

不要把一个基数减另一个基数。§3.1 的清单和 §5.1 的清单是两份不同的清单，
混着减就会得出错误的"seam 之后"数字。

有一个设计约束要在这个 PR 里定下来，而不是事后发现：
`src/kiro_crew/security/paths.py` 被很早导入，而它读身份存储表恰恰是因为那个模块
只依赖标准库。声明表必须放在同等条件的、只依赖标准库的叶子里，否则地板读它就会成环——
和后端词汇表模块自己 docstring 里记下的那个陷阱是同一个。

**13 个语言文件是诚实的例外，而它们的命运由这个 PR 决定。** 让服务端把声明里的
补救字符串原样渲染出来，就像面板今天已经回落到线上 id 那样，那 13 个文件就**永久**
离开接入清单——代价是每个供应商多一句不翻译的字符串。反过来保留一句可翻译的文案，
那 13 个文件就**永久**留在清单上，因为按供应商翻译的字符串在构造上就是按供应商的文件改动。
**建议选前者**：一句正确但没翻译的补救说明，胜过一句翻译好但没人去加的。

### 5.4 它算哪个 PR

**一个新的、独立于这一摞的 PR。** 它不是 PR 3b 也不是 PR 4b，因为它不依赖
PR 2 到 PR 6 中的任何一个：`src/kiro_crew/agent_sdk/` 和它的 `drivers/` 模块已经存在，
声明在构造上只依赖标准库，而 API 返回体和面板是每一个 RFC PR 都不碰的。
它落在今天的 `main` 上。

退出条件：

- 每个现有供应商都有一份声明，且当一个已知供应商没有声明时 parity 测试失败。
- 凭据地板、沙箱掩码、适配器自有叶子排除项都从声明派生；三张手工维护的字面量表消失。
- doctor 里按供应商的认证块被一行由声明驱动的行取代。
- auth-required 的提示语来自声明，不再是 kiro-cli 的那句字面量。
- 面板里按供应商的比较消失；caveat 来自返回体。
- `docs/system-specs/modules/agent-host-contract.md` 的 bucket 3 从文本表变成
  已声明的 seam，seam 状态清单把它去掉。
- `docs/system-specs/modules/harness-onboarding.md` 增加一个认证阶段。它今天没有。

## 6. 按现状加一个供应商

如果 §7 被接受，这就是要发布并照着走的清单。它是**当下**的成本，不是未来的成本；
顺序安排成不会中途发出一个不可用的状态。

### 6.1 各 ratchet 要求的

1. **词汇表。** `src/kiro_crew/acp_backends.py`：id 常量、已知集合、可选基线、
   policy id、路由条目，以及对**每一个**能力集合的明确"在或不在"决定。
   缺条目会让 parity 和治理测试失败。
2. **供应商标签。** `src/kiro_crew/acp/types.py` 以及
   `src/kiro_crew/providers/acp.py` 里的标签分支。这是一个封闭映射，
   索引着恢复、session map 持久化和清理路由。
3. **spawn 路径与握手。** `src/kiro_crew/acp/client.py`：适配器与二进制常量、
   依赖标记、环境变量覆盖、解析阶梯，以及它自己的协议版本。§5.5 按设计把这些
   留在 driver 内部，而那份接入文档量到的规模是几百行。这一项无法压缩。
4. **帧重放语料。** `test/fixtures/acp_frames/<policy id>/`，至少两个文件。
   `test_acp_frame_replay.py` 是**硬失败**而不是跳过，并且要求七类帧：
   带 agent 版本的 initialize 响应、带 session id 的 session-new 响应、
   一条消息片段、一次工具调用、一次工具调用更新、一次权限请求、
   以及一个带 stop reason 的响应。自从那个可选的帧录制器落地之后，
   产出这份语料是机械的，不用手抄。注意
   `test/fixtures/acp_frames/README.md` 仍然写着"还没有录制器"——那是过期的。
5. **host contract。** 在 `docs/system-specs/modules/agent-host-contract.md`
   **全部九张** bucket 表里各加一列，再加列义表里的一行。
   `test_agent_host_contract_parity.py` 要求解析出的列集合与已知集合**完全相等**，
   会把每一列的常量名对着词汇表模块解析，并拒绝同一标题下出现第二张后端形状的表。
   写 `unknown` 的单元格是能过的：它断言的是"存在"，不是"正确"。
6. **安装探测。** 在 `src/kiro_crew/agent_sdk/backend_install.py` 加一个探测条目，
   以及它在 `src/kiro_crew/agent_sdk/drivers/acp.py` 里调用的解析器。
   缺探测会降级成 unknown 而不是抛错，但"作为可选发货却没有探测"正是其中一个
   Codex PR 存在的目的所要修的回归。
7. **可选性 ratchet。** `test/test_agent_backend_editable.py` 里有一个硬编码的
   基线字面量和一个"未作为可选发货"集合。一个新 id 会同时踩到两条断言。
8. **mirror 决定。** 注册表需要一个 mirror 类，或者一条带散文理由的"无 mirror"条目。
   两边都不在的 id 会在运行时抛错。
9. **能力选入。** 有若干测试按已知集合参数化，当成员判断与它们矛盾时失败。
   正是这些测试挡住了"供应商静默地跳过一个决定"。

### 6.2 认证要求的

§5.1 的十二行。在认证 seam 落地之前，每一行都是对一张共享表的手工改动。

### 6.3 前端

**没有任何闸门要求这里做什么**，而选项列表是接入里唯一已经正确的部分：面板从服务端
答案构造候选项，名字回落到线上 id。真正可选的是：显示名和图标。

认证 caveat 在实践上**不是**可选的，这也正是 §3.1 那份 38 个文件的账单把它和它的
13 个语言文件算进去的原因。没有测试会因为缺它而失败。但它仍然是用户唯一能知道这个供应商
要单独登录的地方，所以少了它，发出去的就是一个用户无法行动的选项。它算在 §5.1 的认证清单里
而不是这一节，就是这个原因。

### 6.4 账单

**休眠：20 个文件。可选且已接入权限路由：38。真正接上：49。**
走完整摞 RFC 之后：37 和 46。改为只做认证 seam 之后：取"服务端渲染补救字符串"
这个选择，**可选且已接入权限路由是 22**，因为有 16 个文件离开清单——逐个列在 §5.3。
真正该比的是"离开 16 个文件"对上整摞的"1 个"。

## 7. 结论

**采用第 3 个选项，并作修正：按接入成本这个理由停掉边界这一摞，把 §6 的清单按现状
发布出来，做认证 seam，然后开始加下一个供应商。**

论证的直白形式：

- 整摞的接入增量是 38 里的 1 个文件。实测，见 §3.3。
- 成本的大头是认证，而 RFC 用自己的 non-goal 把认证排除了。实测，见 §3.4。
- 这一摞之外的一个 PR 就把认证成本从 24 个文件降到 2 个，而且它不依赖这摞里的任何东西。见 §5。
- 因此 §1 的规则触发：重构之后接入成本和之前一样，所以**按这个理由**重构不成立。

为什么不选第 2 个选项"只做有接入增量的 PR"。因为没有值得点名的。PR 6 买一个文件，
而且在 §12.5 定下来之前开不了工；PR5 第 4 波买两个，都取决于 PR3b，
而它自己要花 25 个文件、是整摞里最大的一波。按数字算，第 2 个选项塌缩成第 3 个。

**这份结论没有说的话。** 它没有说边界这一摞没有价值。它说的是：边界这一摞的理由
不是接入成本，应该按它真正交付的东西来论证：

- **类型归属**（PR2b/2c）。今天 `src/kiro_crew/providers/base.py` 把 ACP 事件
  别名成"与供应商无关"的类型，而这正是闸门不得不监视两个 root 的那条通道。
  这是一个真实的设计缺陷。
- **PID 归属与消环**（PR4）。它便宜的那一半已经落地，也正是基线下降的原因。
- **一处安全清理**（PR5 第 3 波）。`src/kiro_crew/knowledge/llm_pool.py`
  从包外读一个私有 ACP 属性。这本身就值得修，而且不需要一整波。
- **import 卫生**（PR5、PR6）。是真的，值得在树上没别的事时做——
  而不是排在产品想要的那个供应商前面。

上面每一项都可以单独论证、单独估量、单独排期。它们唯一都不能用来论证的，
就是加第五个供应商的成本。

**如果本结论被接受，顺序是：**

1. 把 §6 作为接入清单发布，并修掉 §6.1 点出的两处文档漂移——过期的录制器说明，
   以及 `harness-onboarding.md` 报的能力集合数量比代码里实际的少一个。
2. 做认证 seam（§5），取"服务端渲染补救字符串"这个选择。
3. 照着 §6 的清单加下一个供应商，并记录它真实花了多少。
4. 只在边界这一摞自己的理由成立时才重开它，逐个 PR 来，用 §7 的清单当论证依据；
   mirror 的归属决定（§4）在真的动 PR 6 时再做，而不是提前做。

## 8. 什么会改变这个答案

- **第二个需要产品内交互式登录的供应商。** 那时认证 seam 的可选登录协议就变成
  真正承重的，而 §5.1 里那 17 个额外文件进入范围。这会让 seam 相对替代方案变得
  更便宜而不是更贵——所以这一条是加强 §7，不是削弱它。
- **实测出来的接入成本远高于 38 个文件。** 上面第 3 步就是为了查清这一点。
  如果真实成本由本文和那份 RFC 都没量过的东西主导，两份都要重读。
- **边界这一摞因为某个非接入理由并且带截止日期而必须做**——一个解不开的 import 环，
  或者一个卡住功能的类型缺陷。那就让相关的那个 PR 按那个理由发出去；
  本文的答案不受影响，因为它从来不是关于代码形状的论证。
