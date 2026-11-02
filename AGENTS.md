# Memory MCP

## 项目概述
个人记忆服务，基于语义向量检索与知识图谱，通过 MCP Streamable HTTP 对外提供能力。

## 技术栈
- Python 3.11+
- MCP SDK
- LanceDB
- NetworkX
- Starlette / Uvicorn
- 管理面板：React + TypeScript + Vite，TanStack Router / Query / Form，shadcn/ui + Tailwind，lucide（docs/adr/0003）

## 目录索引
- `src/` - 服务端源代码
- `tests/` - 服务端测试
- `cli/` - CLI 客户端（独立包 memory-mcp-cli）
- `docs/` - 项目文档
- `web/` - 管理面板源码（React 单页应用，pnpm，锁文件入库）；`pnpm build` 输出到 `src/memory_mcp/ui/`
- `src/memory_mcp/ui/` - 面板构建产物（不入库，由 Dockerfile 的 Node 阶段生成，随包发布，挂在 `/ui/`）
- `src/memory_mcp/settings_registry.py` - 设置注册表：可在面板修改的设置、元数据与生效值
- `src/memory_mcp/access_tokens.py` - 具名访问令牌：鉴权、创建、吊销；初始令牌的哈希写入与重置
- `src/memory_mcp/providers.py` - Provider 记录、API key 的 AES-GCM 加密与生效值解析（配置文件 Provider 的覆盖与恢复）
- `src/memory_mcp/engine/model_client.py` - 三种协议的 chat / embedding / 模型列表，调用结果写回 Provider 的最近调用状态
- `src/memory_mcp/model_roles.py` - 模型用途：写入与维护各自的 Provider、模型与超时；向量用途只读
- `src/memory_mcp/recall_log.py` - 检索记录（30 天、可关闭、可清空）与日统计（90 天，写入 / 召回数、召回耗时中位数）
- `src/memory_mcp/startup.py` - 启动设置：草稿、校验、应用与回退记录
- `src/memory_mcp/lifecycle.py` - 应用启动设置后的优雅退出：停止接受请求、等一轮维护、排出退出码
- `src/memory_mcp/overview.py` - 概览快照与维护轮次历史
- `PRODUCT.md` / `DESIGN.md` / `.impeccable/` - 面板的产品与视觉记录（视觉为 shadcn/ui 默认外观；`.impeccable/review/` 等工作文件不入库）
- `ops/` - 部署主机上运行的运维脚本（`backup-db.sh`：SQLite + 向量库每日备份，保留 7 份；`run-maintenance.sh`：触发一轮后台维护）
- `data/` - 运行时数据

## 常用命令
- 安装依赖：`pip install .`
- 开发服务：`python -m memory_mcp`
- 运行测试：`pytest`
- 代码检查：`ruff check .`
- 面板：`cd web && pnpm install`；`pnpm dev`（代理 `/api` 到 `127.0.0.1:8765`）；`pnpm typecheck` / `pnpm lint` / `pnpm test` / `pnpm build`

## 全局规范
- MCP Streamable HTTP 为主传输协议；REST API (`/api/v1/*`) 为 CLI 等非 MCP 客户端提供轻量接入，复用同一套 tool 函数
- MCP 只暴露 agent 主动存取所需的 4 个工具（`remember` / `recall` / `forget` / `trace`），不注册 resources；运维与图谱类能力只走 REST / CLI
- Tool 返回值统一为 JSON 字符串
- 运行时设置一律经 `settings_registry.get()` 在调用时读取，不在 import 时取值、不写模块常量；新增可调参数先在注册表声明（类型、默认、范围，高级参数带推荐值与评估依据）
- 面板中记忆文本只按文本渲染：ESLint 禁止 `dangerouslySetInnerHTML` 与 `innerHTML`
- 面板组件用 shadcn CLI 生成（`web/src/components/ui/`、`web/src/hooks/`），保持生成原样，不改类名；外观经 `web/src/index.css` 的主题变量与页面布局承担（瓷白 / 石墨 / 松烟，见 DESIGN.md）
- 记忆数据持久化：向量存储 + 图存储并行
- 变更必须更新本文件
- 涉及线上服务能力的任务，只有更新到线上并完成线上验证后才算终结；仅完成本地代码、测试或文档不算完成

## Agent skills

### Issue tracker

Issue 与 spec 放在 GitHub Issues（kassol/memory-mcp），用 `gh` CLI 读写。See `docs/agents/issue-tracker.md`.

### Triage labels

五个标准分诊角色沿用默认标签名（needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix）。See `docs/agents/triage-labels.md`.

### Domain docs

单上下文：根目录 `GLOSSARY.md` + `docs/adr/`，按需创建。See `docs/agents/domain.md`.

## 变更日志
### 2026-11-02 面板第七轮：可到达与可读
- 设置：tab 可深链（`?tab=parameters|providers|roles|tokens|startup|security`），切换 tab 同步更新 URL；概览的 Provider 与访问令牌卡可直接跳到对应 tab
- 手机 toast 改为顶部，避免遮住吸底裁定条
- 图表补屏幕阅读器摘要（30 天写入 / 召回与最近一次召回耗时），读屏能听到数据
- 验证：前端 61 个测试（新增设置深链）、`typecheck` / `lint` / `build` 通过；后端 283 个测试与 `ruff` 通过；线上复核深链、tab URL 同步与图表摘要

### 2026-11-02 面板第六轮：审阅与设置回路
- 待审：J / K 切换时队列自动滚到选中项，长队列不会把当前卷宗留在视野外
- 档案：分页补首页 / 末页图标按钮，长列表不用逐页翻
- 设置：Provider「测试连接」与模型用途「测试调用」显示测试中并防止重复点击
- 维护：有轮次运行时显示「已运行 n 分 n 秒」，每秒更新
- 可访问性：链接与 summary 补键盘焦点环
- 验证：前端 60 个测试、`typecheck` / `lint` / `build` 通过；线上复核队列滚动、分页按钮、维护运行时长与焦点样式

### 2026-11-02 面板第五轮：产品级收口
- 导航：侧栏分为「审阅 / 系统」两组；手机按钮统一 40px 高、图标按钮补 40px 宽；设置目录在手机改为 3×2 网格，两行对齐
- 韧性：路由增加错误边界与 404 页（带页标题与回待审），`defaultPreload: "intent"` 在悬停/聚焦时预取页面 chunk
- 动效：路由内容 180ms 淡入上移，`prefers-reduced-motion` 时关闭
- 图表：写入与召回图加图例；Provider、访问令牌与维护历史在手机改为卡片，去掉横向滚动
- 细节：维护错误带折叠箭头；设置布尔项「恢复为默认值」不再拉满；跳到主要内容链接补键盘入口
- 验证：前端 60 个测试、`typecheck` / `lint` / `build` 通过；线上复核 404、预取、手机 40px 目标、三页手机卡片与导航分组，最终 ship

### 2026-11-02 面板第四轮：减少文字与主次层级
- 全站：删除页头与卡片上复述标题的说明；侧栏页脚去掉装饰文字；空状态只留结论与出口
- 概览：待审横带只留计数、类型与入口；图表合并为「写入与召回」和「召回耗时中位数」两栏；维护卡只留计划时间与最近一轮
- 待审：检查意见默认两行、按需展开；卷宗头压缩为标题、类型、队列位置与 key；队列条目压缩为一行身份信息加两行摘要；筛选 chip 带选中态，空筛选保留该类型 chip 并给「查看全部」；裁定条去掉说明句
- 档案：去掉类型列（key 前缀已带类型），时间改为「月-日 时:分」，跨年补两位年份；检索与 key 过滤的占位文案缩短
- 设置：每行只留标签、非默认来源、控件与范围；说明、推荐值、key 收进「说明」；高级参数保留一行摘要；保存按钮只在改动后出现
- 维护：错误摘要改为「本轮有 N 项判定失败」或首行截断，原文放「详情」；去掉 409 这类开发者提示
- 验证：前端 60 个测试（新增空筛选选中态与保存按钮出现时机）、`typecheck` / `lint` / `build` 通过；线上按产品经理视角复核文字量与层级，确认主次成立后 ship

### 2026-11-02 面板第三轮：阅读与导航细节
- 待审：按句对比摘要移到两张记录卡上方，先看差异再读全文；裁定条继续吸底
- 档案：桌面表格头吸顶（lg 起取消生成的表格横向裁切），滚动 50 行仍保留列名；记录卡 key 旁增加复制按钮
- 主题：`web/index.html` 在 React 启动前按 `localStorage` / 系统偏好预置 `.dark`，深色用户首屏不再闪白
- 可访问性：路由切换后把焦点落到页标题 `h1`，屏幕阅读器能读出新页面
- 验证：前端 59 个测试、`typecheck` / `lint` / `build` 通过；后端 283 个测试；线上真实数据复核对比摘要位置、吸底裁定条、手机排序与吸顶表头，OCR 确认表头与正文没有串行

### 2026-11-02 面板第二轮：代码分割与审阅效率
- 代码分割：路由改用 `lazyRouteComponent`，五个页面各成异步 chunk；首屏主包从 1.14 MB 降到 400.87 kB（gzip 124.57 kB），概览的 recharts 单独懒加载 363.76 kB，档案的表格、设置的开关各自成块。路由挂 `defaultPendingComponent`，等待 chunk 时保留页头骨架
- 待审：概览的类型计数改成带 `?kind=` 的深链，点「重复 20」直接进筛选后的队列；新增「保留甲，归档乙 / 保留乙，归档甲」确认框（默认原因、可改），新增按句的「对比摘要」（共同 / 仅甲 / 仅乙）；新增上一件 / 下一件按钮与「队列 n / 总数」；裁定条改为吸底，长记录滚动时仍可操作；空筛选给「查看全部」出口
- 档案：手机端增加排序选择（最新 / 最早 / 最久未更新 / 最近更新 / Key A–Z），有筛选时显示「清除筛选」；详情 Sheet 标题吸顶
- 维护：有 running 轮次时每 3 秒自动刷新并禁用运行按钮；长错误首行常显，多行详情折叠
- 命令面板：底部补 ↑↓ / ↵ / esc 提示
- 静态缓存：`ConsoleStaticFiles` 给 `/ui/` 与 html 发 `Cache-Control: no-cache`，给 `assets/` 的哈希文件发一年 immutable；避免部署后浏览器继续用旧入口
- 测试：前端 59 个测试（新增深链筛选与保留甲/归档乙），`typecheck` / `lint` / `build` 通过；后端 283 个测试与 `ruff` 通过；线上用真实数据复核类型深链、上一件/下一件、保留确认框、手机排序与吸底裁定条

### 2026-11-02 面板视觉重做：瓷白与石墨
- 动机：shadcn 默认外观整体平庸。Sir 要求更现代、更精致，上一轮印刷校样 / 档案馆 / 调度台三案与暖色软调三案均被否，最终选定瓷白底、石墨字、单一松烟绿的方案
- 主题（`web/src/index.css`）：浅色地面 `#F6F6F3`、白面板、石墨 `#17181A`、发丝线 `#E9E8E3`、深松 `#245C4F`；深色地面 `#0B0C0B`、面板 `#171918`、瓷白字 `#EDEBE5`、提亮松 `#7AAD9D`。半径 0.5rem（面板 11.2px、控件 8px），边框与投影二选一。图表色改为松 / 琥珀 / 蓝灰 / 陶红 / 鼠尾草，关闭图表入场动画。新增 success / warning / info 语义色、选中文字与滚动条、焦点与 caret 的浏览器表面配色
- 外壳：侧栏改为浅色底、石墨方印「记」、工作台分组、白色抬起的当前项与松色图标；页头 64–71px，标题 22px、可选说明（手机隐藏）、右侧事实或操作，去掉竖分隔线；正文统一居中 `max-w-[1180px]` 与 16 / 32px 节奏
- 页面：概览改为全宽待审横带（大计数、类型分布、处理提示）+ 记忆 / 维护两卡 + 单张近 30 天图表面板 + Provider / 最久未更新 / 令牌；待审增加类型筛选与计数、全局卷宗编号、Shift 作用于甲/乙提示、选中卡抬起、记录卡等高且底栏对齐；档案加下划线视图切换、工具栏、手机卡片列表、类型小圆点、详情时间线；维护加最近一轮状态、错误两行截断、耗时右对齐；设置改左侧编号竖排目录（手机折成两排）、长 key 单独一行、保存按钮未改动时为描边；登录页改为墨色左栏 + 瓷白表单的分屏
- 状态语法统一：当前 / 完成 / 成功用松或绿点，等待用琥珀，失败用红，失效用淡灰点；胶囊只留给筛选与计数。主操作实心松绿，次要描边，危险用淡红
- 测试与验收：前端 57 个测试全部通过，`pnpm typecheck`、`pnpm lint`、`pnpm build` 通过；后端 283 个测试不受影响。用临时数据库与本地构建产物在 ego-browser 走桌面 1440、手机 390、浅色与深色，另由一次只读审图复核排版、等宽、对比与手机折行；`impeccable detect` 无机械问题
- 线上验收后修复：待审队列改用原生滚动并约束在 288px，长文本按两行截断；维护错误完整换行；布尔设置的默认值显示为开启 / 关闭；手机设置分区折行后留出 24px 间距
- 文档：重写 DESIGN.md（新主题、布局、组件与规则）；PRODUCT.md 品牌承诺与登录方式同步；surface brief 记录方向契约

### 2026-11-01 概览与维护页（#16）
- 动机：面板只有待审、档案与设置，服务整体状态（发现分布、记忆变化、Provider 健康、最近一轮维护、召回趋势）没有一处能看到（#7）
- 新增 `overview.py`：`snapshot()` 一次读出待审发现按类型计数、当前记忆总数与 7 / 30 天新增与演化数、最近一轮维护、Provider 最近调用、最久未更新的 5 条记忆、令牌最近使用、近 30 天日统计；`rounds(limit)` 读 `jobs` 里 `job_type = 'maintenance'` 的轮次并算出耗时
- 维护计划在宿主机 cron 上，服务不知道：接口返回固定说明文字，面板只展示
- REST（只接受面板会话，`_ADMIN` 增加 `/api/v1/overview`）：`GET /api/v1/overview`、`GET /api/v1/overview/rounds?limit=`。注意刻意不放在 `/api/v1/maintenance` 下：那个前缀下的 `POST /maintenance/run` 仍接受访问令牌（宿主机 cron 用它）
- 面板：概览页（三张卡：待审分布可跳转、记忆变化、维护状态；三张 30 天图：写入、召回、召回耗时中位数，新增 shadcn `chart` 与 recharts；再往下是 Provider 最近调用、最久未更新的记忆可打开详情、令牌最近使用）；维护页（立即运行一轮、刷新、最近 20 轮历史含耗时 / 调用次数 / 发现数 / 错误、计划显示）
- 删除 `pages/placeholder.tsx`：两个占位路由已换成真页面
- ESLint：生成组件的原始 HTML 禁令放行 `<style>` 上的 `dangerouslySetInnerHTML`（图表组件注入静态 CSS 变量），其他情况仍然报错
- 测试：`tests/test_overview.py`（快照各字段、轮次顺序与 limit 校验、只接受面板会话）；前端 `overview.test.tsx`（发现分布与跳转、记忆变化、图渲染数量、Provider / 最久未更新 / 令牌）、`maintenance.test.tsx`（计划文字、运行一轮后出现运行中、历史含耗时与错误）
- 文档：DESIGN.md 补概览与维护页、状态徽章、开关与图表的取色

### 2026-11-01 启动设置：校验、应用与回退（#14）
- 动机：端口、数据目录、向量后端这些只在启动时读取的设置只能改宿主机 `.env` 再重新部署；改错没有校验，服务起不来时也看不出原因（#7、docs/adr/0002）
- 启动设置在 settings 对象之前读取：`config.recover_startup` 在新的 `Settings` 之前读 `data/startup-settings.json` 并按需回退。可覆盖的键 `port`、`data_dir`、`vector_backend`、`embedding_model`、`embedding_dim`、`debug`
- 三个文件：`startup-settings.json`（生效）、`startup-settings.pending.json`（草稿）、`startup-apply.json`（应用标记与结果）。全部原子写入
- 流程：面板改草稿 → `check` 逐条给出原因 → `apply` 再校验同一份值、写标记与新文件、删草稿、请求重启。重启先等一轮维护（≤30 秒）再停止接受请求，最后由 uvicorn 排空并让进程以 `lifecycle.EXIT_CODE`（88）退出；`docker-compose.yml` 的 `restart: unless-stopped` 拉起它
- 回退：apply 写标记时 `attempts = 0`；下一次启动把它置为 1，走到 lifespan 结束即记「已生效」。若那一次启动没走到（端口占用、数据目录坏了等），再下一次启动把上一份 override 写回、把标记记为 failed 并写下原因，面板显示
- 校验项：取值范围、数据目录存在且可写、换目录时里面要有现成的 `memory.sqlite3`、向量后端能加载、已存向量维度与设置一致、容器外端口可绑定（当前端口跳过，它是本进程自己占的）
- 容器里 `port` 与 `data_dir` 只读并给出原因：由编排决定；`embedding_model` / `embedding_dim` 任何情况下都不在面板里改（存量向量依赖它们）
- `__main__.py` 改为自己创建 uvicorn `Server` 并 `lifecycle.bind`，退出码取自 lifecycle；不再用 `reload`（uvicorn 的 reload 会拉起监督进程，吞掉退出码），`debug` 只提高日志级别
- 修复：关闭时 `await get_store().close()`。aiosqlite 的工作线程不是守护线程，不关闭连接则进程无法退出，应用启动设置会挂在退出这一步（此前只在测试收尾时踩到）
- REST（只接受面板会话，`_ADMIN` 增加 `/api/v1/startup-settings`）：`GET /api/v1/startup-settings`（生效值、草稿、可编辑项、只读原因、上次应用）、`PUT`（保存草稿）、`DELETE`（丢弃草稿）、`POST /api/v1/startup-settings/check`、`POST /api/v1/startup-settings/apply`（202）
- 面板「设置 → 启动设置」：容器 / 手工运行的提示、端口与数据目录（容器内只读并给出原因）、向量后端、调试日志、待生效摘要、校验结果、应用并重启（应用后轮询 `/health` 直到服务回来）、上次应用结果
- 测试：`tests/test_startup_settings.py`（描述与草稿校验、容器内只读、坏草稿被 check 拦下且 apply 不写文件、apply 写文件与标记并记为已生效、丢弃草稿、只接受面板会话；两个子进程测试：apply 后进程以 88 退出、再次启动生效值来自文件且标记为已生效；起不来的应用会回退 override 并在面板显示原因）；前端 `startup.test.tsx`
- 未做：`data_dir` 换到别处时把数据库一起搬过去（当前要求先手工放好 `memory.sqlite3`）

### 2026-11-01 检索记录与日统计（#15）
- 动机：调优只能看现象，召回没有可对照的查询、令牌、耗时与结果；写入量也只有总量（#7）
- migration `0010_recall_log`：`recall_log`（时间、令牌、查询、耗时、结果数、前三条记忆 id）与 `daily_events`（日、令牌、kind = recall / write、耗时）。`daily_events` 每行一次事件，召回耗时中位数因此由真实值算出，不用近似
- 新增 `recall_log.py`：`record`（召回：总是写日事件，设置打开时再写日志）、`record_write`（remember 存下新版本时写日事件）、`recent` / `clear` / `daily` / `prune`。保留期 30 / 90 天，清理在记录时最多每小时执行一次，不需要额外 cron
- `recall_tool` 新增关键字参数 `origin_token`（与 `remember_tool` 同法，由传输层填入，客户端不能伪造），测量检索耗时并记录；`remember_tool` 在 created / evolved 两处记录写入数，no_change 不算
- 观测失败不影响主路径：日志写入异常只打 warning，召回与写入照常返回
- 设置注册表新增 `bool` 类型与 `recall_log_enabled`（默认开）；配置文件可用 `MEMORY_MCP_RECALL_LOG_ENABLED`
- REST（只接受面板会话，`_ADMIN` 增加 `/api/v1/recall-log`）：`GET /api/v1/recall-log?limit=&offset=`、`GET /api/v1/recall-log/daily?days=`（按日与令牌给出写入数、召回数与召回耗时中位数）、`DELETE /api/v1/recall-log`（清空日志，日统计保留）
- 面板：档案页顶部切换「档案 / 检索记录」；记录表显示时间、查询、令牌、耗时、结果，前三条结果可直接打开；顶部有记录开关（恢复默认可点）与清空；设置页的布尔项渲染成开关（新增 shadcn `switch`）
- 测试：`tests/test_recall_log.py`（召回写入日志与日事件、只留前三条 id、分页、关闭后只有日统计、清空保留统计、按日与令牌聚合与中位数、清理 30 / 90 天与每小时一次、只接受面板会话、参数校验）；`tests/test_migrations.py` 覆盖 0010 升降级；前端 `recall-log.test.tsx`（列表、打开结果、清空、开关）
- 未做：日统计的图表留给 #16

### 2026-11-01 模型用途：写入与维护（#13）
- 动机：所有模型调用共用一个 Provider 与模型，remember 需要的快路径与维护需要的强模型不能分开（#7）
- 新增 `model_roles.py` 与 migration `0009_model_roles`：`model_roles`（role 主键、provider_id 外键、model、timeout）。写入用途服务 key 分配、合并与冲突判定；维护用途服务后台检查的判定。没有行时用此前的行为：配置文件 Provider、`llm_model`、30 秒
- 调用点改经用途解析：`engine/llm.py` 的 `chat` 走写入用途、`maintenance_chat` 走维护用途；`conflict.py` 与 `key_assignment.py`、`merge.py` 用写入用途；`maintenance.py` 用维护用途。`engine/embedding.py` 走只读的向量用途（配置文件 Provider + `embedding_model`）
- 超时随用途走：冲突判定此前固定 10 秒，现在与写入用途的其他调用共用用途超时（默认 30 秒），用户可在面板调整
- 向量用途只读：`PUT` / `DELETE` 返回 400 并说明存量向量依赖它；面板只展示 Provider、模型与向量维度
- 删除 Provider 时若被某个用途引用，返回 409 并指出用途（`providers.delete_provider` 直接查 `model_roles`，避免与 `model_roles` 循环导入）
- REST（只接受面板会话，`_ADMIN` 增加 `/api/v1/model-roles`）：`GET /api/v1/model-roles`（含默认值与 `custom`）、`PUT /api/v1/model-roles/{role}`（`{provider_id, model, timeout}`）、`DELETE /api/v1/model-roles/{role}`（恢复默认）、`POST /api/v1/model-roles/{role}/test`（用该用途的 Provider 与模型发一句短请求，失败也返回 200 + `ok: false`）
- 面板「设置 → 模型用途」：写入与维护各一行 Provider 选择、模型输入（带该 Provider 的模型列表 datalist）、超时；保存、测试调用、恢复默认；向量一行只读
- 测试：`tests/test_model_roles.py` 覆盖默认值、写入与维护用途各自到达哪个 Provider 与模型（本地假 HTTP 服务上核对请求体里的模型名）、改用途后下一次调用生效、超时随用途、恢复默认、向量用途只读、校验（模型空 / 超时越界 / 未知 Provider / 未知用途）、被引用的 Provider 不能删除、测试调用成功与失败、管理接口只接受面板会话；`tests/test_migrations.py` 覆盖 0009 升降级与外键；`tests/fake_provider.py` 抽出假 Provider 供两个测试文件共用
- 前端：`roles.test.tsx` 覆盖默认展示、保存、测试调用、恢复默认、向量只读与失败原因

### 2026-11-01 Provider 记录与三种协议（#12）
- 动机：此前只有配置文件里的 OpenRouter 一个入口和一个模型，换 key 或加供应商要改宿主机 `.env` 再重新部署（#7）
- 新增 `providers.py` 与 migration `0008_providers`：`providers`（id、名称唯一、protocol、base_url、`api_key_cipher`、来源 file / console、创建与更新时间、最近调用时间与结果）。API key 用 AES-GCM 加密，数据密钥在 `data/provider-keys.key`（0600，首次启动或首次加密时创建，AAD 绑定 Provider id）；接口只返回末四位，key 不会回到浏览器
- 配置文件里的 OpenRouter 设置是 id 为 `file` 的 Provider：`base_url` 与 `api_key_cipher` 为 NULL 表示「用配置文件值」，面板改写这两列即覆盖，传 null 即恢复。该行不能删除，协议固定 OpenAI 兼容（向量用途依赖它）
- 新增 `engine/model_client.py`：OpenAI 兼容、Anthropic、Gemini 的 chat / embed / list_models。每次调用把结果写回 Provider 行（最近调用时间、成功与否、原因）；错误统一成可读消息（超时、连接失败、HTTP 状态加响应片段、响应缺少字段）。Anthropic 没有 embedding 接口，调用前就报错、不记录最近调用
- 推理按协议各自关闭：OpenAI 兼容 `reasoning.enabled=false`；Gemini 只在 2.5 / 3 系模型发 `thinkingConfig.thinkingBudget=0`（老模型拒绝该字段）。JSON 模式：OpenAI 兼容 `response_format`、Gemini `responseMimeType`、Anthropic 的 system 指令；`json_mode` 目前只有测试使用，写入路径行为不变
- `engine/llm.py`、`engine/conflict.py`、`engine/embedding.py` 改走 `model_client` 与 `file` Provider，配置在调用时读取；`conflict.py` 不再自己拼 HTTP 请求，`NO_REASONING` 常量删除
- REST（只接受面板会话，`_ADMIN` 增加 `/api/v1/providers`）：`GET /api/v1/providers`、`POST /api/v1/providers`、`PUT /api/v1/providers/{id}`、`DELETE /api/v1/providers/{id}`、`POST /api/v1/providers/test`（可以只给 id，用已存的 key，便于改地址后测试）、`GET /api/v1/providers/{id}/models`
- 面板「设置 → Provider」：列表显示来源、协议、key 末四位、最近调用与失败原因；添加、编辑（key 留空即保留原值）、测试连接（列出模型，不消耗 token）、删除、恢复地址或 key
- `ops/backup-db.sh` 一并复制 `provider-keys.key`；README 写明缺少数据密钥时库里的 key 无法解密
- 依赖：`cryptography` 显式声明（`requirements.lock` 里已有）
- 测试：`tests/test_providers.py` 用本地假 HTTP 服务覆盖三种协议的请求形状、推理关闭与 JSON 模式、embedding、模型列表、错误映射、最近调用状态、密文入库与末四位、REST 增删改与校验、配置文件 Provider 的覆盖与恢复、管理接口只接受面板会话、写入路径与 embedding 走 `file` Provider；`tests/test_migrations.py` 覆盖 0008 升降级；前端 `providers.test.tsx`
- 未做：删除 Provider 时「有模型用途引用则拒绝」要等 #13 引入模型用途；`json_mode` 也在 #13 接入

### 2026-11-01 初始令牌改为普通令牌（#11 后续）
- 动机：初始令牌原先是特例（不存哈希、与配置值比较、只能停用 / 启用），后端用 `id == initial`、前端用 `source === file` 各自判断。改为与其他令牌同一条路径
- 服务启动时（migration 之后）`store_initial_hash` 把 `MEMORY_MCP_AUTH_TOKEN` 的哈希写入 `initial` 行，只在它为空时写一次。配置值只在首次使用；之后改 `.env` 不生效。哈希不在 migration 里写：migration 按约定不读取 Settings（`migrations/env.py`），故无新 migration
- 鉴权只按哈希查表；初始令牌可由面板吊销，删除停用 / 启用与 REST `PUT /api/v1/tokens/initial`。面板 bootstrap 仍只接受未吊销的初始令牌（`opens_bootstrap`）
- 口令重置命令在同一事务里把初始令牌按 `.env` 当前值重新写入并恢复生效（对 agent 也生效），作为吊销后的找回路径；能执行该命令的人本就能读到 `.env`
- 面板：初始令牌与其他令牌一样显示「吊销」，确认框提示仍在用它的客户端与找回方式
- 测试：初始令牌可吊销、改配置值不生效、重置按新值恢复并可开 bootstrap、吊销后不能开 bootstrap、具名令牌不能开 bootstrap、启动时写入哈希

### 2026-11-01 具名访问令牌（#11）
- 新增 `access_tokens.py` 与 migration `0007_access_tokens`：`access_tokens`（id、名称唯一、SHA-256 哈希、来源 file / console、创建、最近使用、revoked_at）；`memories` 新增列 `origin_token`。配置文件令牌是 id 为 `initial` 的行，不存哈希，仍与配置值做常数时间比较；它的 `revoked_at` 表示停用，可以再启用；停用期间它也不能开面板 bootstrap 会话（重置口令后需先在库里启用，见 README），泄露后停用的令牌不能抢先设置口令。其他令牌只能吊销，名称在吊销后仍占用，保证记忆里的令牌名只指向一个令牌
- 最近使用时间在鉴权时写入，每个令牌每分钟最多一次
- `AuthMiddleware` 改为经 `access_tokens.authenticate` 鉴权，把令牌放在 `request.state.token`；REST `POST /api/v1/memories` 与 MCP `remember`（从 `ctx.request` 取）把令牌名写入 `origin_token`，客户端传入的同名字段被覆盖；面板会话写入时为空。人工改正保留原来的 `origin_token`。`GET /api/v1/memories/{id}` 返回项新增 `origin_token`
- REST（只接受面板会话，归入 `_ADMIN`）：`GET /api/v1/tokens`；`POST /api/v1/tokens`（`{name}`，201，响应含 `value`，空名 400，重名 409）；`DELETE /api/v1/tokens/{id}`（吊销，初始令牌 400，不存在 404）；`PUT /api/v1/tokens/initial`（`{enabled}`）。列表与响应都不含哈希
- 面板：「设置 → 访问令牌」列出名称、来源、创建、最近使用与状态；创建后在对话框里显示一次令牌值并可复制；吊销与停用前确认。状态显示在名称下方，手机隐藏来源与创建列，360 px 宽不横向滚动。新增 shadcn `alert-dialog`
- 线上验收：生产库副本演练 0007 升级、降级、再升级，记忆行数、rowid 与 id、全文检索命中、发现、外键与完整性不变；上线后在面板创建验收令牌，经 MCP 写入一条记录（`origin_token` 为该令牌名）、经 REST 检索到它、设置与令牌接口 403，归档该记录后在面板吊销，REST 与 MCP 均 403；初始令牌未停用，现有 agent 照常工作
- `remember_tool` 新增关键字参数 `origin_token`，不从 `arguments` 读，客户端无法伪造来源
- 测试：`tests/test_access_tokens.py`（REST 与 MCP 经新令牌读写、停用的初始令牌不能开 bootstrap 会话、重复停用保留首次时间、吊销与停用后被拒、初始令牌可再启用、令牌值只返回一次且只存哈希、名称唯一、最近使用每分钟一写、管理接口拒绝访问令牌、来源记录令牌名）；`tests/test_migrations.py` 覆盖 0007 升降级；前端 `tokens.test.tsx`

### 2026-10-31 管理口令与面板会话（#10）
- 面板改用管理口令登录（docs/adr/0001）。新增 `console_auth.py` 与 migration `0006_console_auth`（`console_admin` 存 scrypt 口令哈希；`console_sessions` 只存会话令牌的 SHA-256、7 天滑动过期、bootstrap 标记）
- 首次部署：没有口令时，配置文件里的访问令牌可开一个 bootstrap 会话，只能设置口令；设置后该令牌不能再登录面板。不做登录限流与锁定（ADR 0001）
- Cookie `mm_session`：HttpOnly、Secure、SameSite=Strict、Path=/、Max-Age 7 天。以 cookie 认证的写请求必须带与服务同源的 Origin（反代后按 `X-Forwarded-Proto` 与 Host 比对）
- 鉴权分层（`transport/auth.py`）：MCP 只接受访问令牌；设置类接口（`/api/v1/settings`，后续 Provider、令牌、重启同列）只接受完整面板会话，访问令牌 403；记忆与发现接口两者都接受；bootstrap 会话只能调用 `/api/v1/console/*`。#9 留下的「任一访问令牌可改设置」至此关闭
- REST：`GET /api/v1/console/session`、`POST /api/v1/console/login`（`{password}`，或无口令时 `{token}`）、`POST /api/v1/console/logout`、`PUT /api/v1/console/password`（`{current_password?, new_password}`）、`DELETE /api/v1/console/sessions`（退出所有设备）
- 重置命令：`python -m memory_mcp.reset_password`，删除口令与全部会话，不打印任何秘密
- 面板：登录 / 首次登录 / 设置口令三个视图；「设置 → 安全」改口令、退出所有设备；页面不再接触访问令牌
- 测试：`tests/test_console_auth.py`（bootstrap 限制、口令存在后令牌被拒、cookie 属性与只存哈希、缺失或不符 Origin 被拒、反代后的 Origin、设置接口拒绝 Bearer、数据接口两者皆可、MCP 拒绝 cookie、改口令、退出与退出所有设备、7 天滑动过期、重置命令）；`tests/test_settings.py` 改为面板会话；前端 `sign-in.test.tsx`

### 2026-10-31 面板改用 shadcn/ui 默认外观与 TanStack Table（#8 补齐）
- 动机：首版把 shadcn 组件改成自定义「登记簿」样式，且档案没有用 TanStack Table，不符合 #8 与 #7 的要求；改为采用 shadcn 原生外观，登记簿视觉作废
- `shadcn init`（radix-nova、neutral、Geist）后组件按生成原样使用：Sidebar（可折叠为图标，手机为抽屉）、Card、Badge、Table、Select、Sheet、Field、Alert、Empty、Kbd、Command、sonner；`next-themes` 管深浅色（默认跟随系统，侧栏底部可切换）。DESIGN.md 重写
- 档案改为 TanStack Table：按 key、类型、写入时间、生效时间服务端排序，按 key 子串与类型（带数量）过滤，分页显示第 n / m 页；详情在右侧 Sheet 中打开；手机隐藏两列时间
- REST：`GET /api/v1/memories` 新增 `sort`（`entity_key` / `entity_type` / `created_at` / `valid_from`）、`direction`（`asc` / `desc`）、`key`（不区分大小写的子串，LIKE 通配符按字面匹配），返回新增 `matched`（过滤后总数）；不带新参数时排序与 `total` 含义不变。新增 `GET /api/v1/memories/types`（当前记忆的类型与数量）
- ESLint：生成组件只检查「禁止原始 HTML」一条规则
- 测试：`tests/test_governance.py` 增排序、过滤、计数、类型列表；前端页面测试改为新界面（23 个）

### 2026-10-31 设置注册表与 React 面板（#9、#8）
- 动机：#7 把面板扩展为管理入口，表单规模超出手写 DOM 的承载能力（docs/adr/0003）；可调参数此前只能改宿主机 `.env` 并重新部署
- 设置注册表 `settings_registry.py`：每项声明 key、中文名、分组（行为 / 高级）、类型、默认值、范围；高级参数另有推荐值与评估依据。生效值 = 面板值（SQLite `console_settings`，migration `0005_console_settings`）> 配置文件或环境变量（`Settings` 同名字段，`None` 表示未设置）> 默认值，并报告来源。面板值在进程内缓存，本进程是唯一写入方
- 注册项：行为参数 `similarity_threshold`、`maintenance_max_llm_calls`；高级参数 `fts_weight`、`rrf_k`、`candidates_per_source`、`graph_seeds`、`decay_lambda`、`cross_key_min_cosine`、`cross_key_neighbours`。原 `hybrid_search` 与 `maintenance` 的模块常量删除，默认值与评估说明迁入注册表；混合检索每次 search 读取，维护每轮开始时读取一次
- 配置文件里超出范围的值在服务启动时报错并列出原因（`check_file_values`），不再静默生效
- REST：`GET /api/v1/settings`（值、来源、元数据）；`PUT /api/v1/settings/{key}`（`{value}`，类型或范围不符 400 并给原因，未知 key 404）；`DELETE /api/v1/settings/{key}`（删掉面板值，恢复为配置文件值或默认值）。在 #10 之前沿用访问令牌鉴权（#10 已改为只接受面板会话）
- 面板迁到 `web/`：侧栏导航（概览、待审、档案、维护、设置；概览与维护在 #16 之前显示简短空状态），命令面板（⌘K，跳页面或检索记忆并打开），hash 路由（`#/records?memory=<id>` 可直达），随系统深浅色，手机为顶栏加抽屉。待审、档案、详情与版本历史与旧版一一对应（登录、改正、归档需原因、判为误报、分页、类型过滤、最久未更新排序、检索）；待审新增快捷键 J / K 切换、C / A 改正或归档（Shift 作用于右侧）、D 判为误报，已失效记录上 C / A 不生效。设置页：分组、来源标签、恢复为配置文件值、推荐值与评估依据、范围校验、偏离推荐值的提示与「恢复推荐值」
- （当日由上方「面板改用 shadcn/ui 默认外观」一条取代：档案改为 TanStack Table，组件改为 shadcn 默认外观）
- 构建：Dockerfile 增加 `node:24-slim` 阶段（corepack pnpm，`--frozen-lockfile`），产物复制进包内 `ui/`，运行镜像无 Node；`pyproject.toml` 以 hatch `artifacts` 打包被忽略的产物；`StaticFiles(check_dir=False)`，没有构建产物时服务照常启动、`/ui/` 返回 404
- 测试：`tests/test_settings.py`（优先级、来源、恢复、非法值原因、保存后下一次 recall 生效、配置文件越界阻止启动）；`tests/test_migrations.py` 覆盖 0005 升降级；原有测试只把常量覆盖改为注册表覆盖，断言不变。`tests/test_governance.py` 的 UI 测试改用临时目录提供构建产物；「不含 `innerHTML`」由 ESLint 规则承担。前端 `web/src/pages/*.test.tsx`（Vitest + Testing Library + MSW）：登录、待审裁定与快捷键、档案分页 / 排序 / 过滤 / 检索 / 详情 / 改正 / 归档、设置校验 / 保存 / 恢复

### 2026-10-30 Web 治理台（#6）
- 动机：维护检查产生的发现需要人来裁定，记忆写错时需要直接改正或归档；此前只能在 CLI 里逐条查
- `/ui/` 静态页面（HTML + CSS + 原生 JS，无构建链），由 Starlette `StaticFiles` 从包内目录托管，非 editable 安装下同样可用。`AuthMiddleware` 只对 `/ui` 与 `/ui/` 前缀放行；页面不含数据，令牌存 `sessionStorage`，所有数据请求带 Bearer，无 cookie。记忆文本只经 `textContent` 渲染（令牌在页面里，HTML 注入会泄露它），当时由 `tests/test_governance.py` 断言 `app.js` 不含 `innerHTML`（2026-10-31 面板迁到 React 后改由 ESLint 规则承担）
- 功能：待审发现队列（并排展示两条记忆、改正 / 归档任一条、判为误报）；档案列表（翻页、按类型过滤、按 `valid_from` 升序找久未更新的记忆、检索）；记忆详情与版本历史（改动类型、时间、冲突合并标记、归档原因）。列表为 listbox，支持方向键与 Enter / Space；每次列表与详情加载带序号，过期响应直接丢弃
- REST 新增：`GET /api/v1/memories/{memory_id}`（含全部版本，新在前）；`POST /api/v1/memories/{memory_id}/correct`（`{content}`，人工内容原样替换，不经 LLM 合并，只重算 embedding，保留 title 与来源字段；内容未变不生成新版本；非 current 返回 409）；`POST /api/v1/memories/{memory_id}/archive`（`{reason}` 必填，经 `forget_tool`；不存在 404、非 current 409）；`POST /api/v1/findings/{id}/dismiss`（一条带 `status = 'open'` 条件的 UPDATE，不覆盖并发自动关闭的结果；非 open 409）。`GET /api/v1/memories` 新增 `offset`、`order`（`created_at` / `valid_from`），返回项补 `memory_id` 与 `valid_from`，不带新参数时行为不变
- 按 id 的路由与 `{entity_key:path}` 路由共存：前者的 `{memory_id}` 不匹配 `/`，且方法或后缀不同，测试覆盖了带 `/` 的 entity_key 仍能 trace / forget
- `forget_tool` 抛出 `MemoryNotFound` / `MemoryNotCurrent`（`ValueError` 子类，MCP 与既有 REST 行为不变）
- 视觉：「档案登记簿」方向，系统字体、等宽只用于标识与日期，随系统深浅色；产品与设计记录见 `PRODUCT.md`、`DESIGN.md`。本地浏览器验证覆盖桌面 1440 / 960、手机 390、深浅色、键盘操作与请求竞态

### 2026-10-30 后台维护（#5）
- 动机：`remember` 只保证同一 key 内一致。跨 key 重复、合并残留过时事实造成的内部矛盾、中断留下的同 key 多条 current，之前没有机制发现。原记忆系统因后台任务占满 CPU 被弃用，所以维护只在被调用时运行
- 术语见 `GLOSSARY.md`：发现（Finding，需要人处理）与检查记录（Check，已判定过，含相容，只用于去重）
- 新增 `engine/maintenance.py`：`POST /api/v1/maintenance/run` 在服务进程内后台跑一轮，返回 202 与 job id，已有一轮在跑时 409；没有进程内定时循环，由宿主机 cron 调 `ops/run-maintenance.sh`。每轮在 `jobs` 表写一行（`payload` 为各项统计，失败写 `error` 并打 warning 日志）。服务关闭时取消正在跑的一轮并记为 failed
- 每轮顺序：自动关闭涉及记忆已非 current 的 open 发现；同 key 多条当前版本（SQL，open 或 dismissed 的不再重报）；内部矛盾（LLM，只查 `conflict=1` 的 current，线上 314 / 3903）；跨 key 重复（LLM，每条记忆用已存向量取余弦最近 5 个、不同 key、余弦 ≥ `CROSS_KEY_MIN_COSINE=0.85`，每个无序对判一次）。旧规则 relevance ≥ 0.85 线上只匹配 6 对，余弦 0.85 约 121 对
- 预算：`MEMORY_MCP_MAINTENANCE_MAX_LLM_CALLS`（默认 100）。两类 LLM 检查各一半，一类用不完的给另一类；没判完的留到下一轮。不用游标，待办即「没有检查记录的」，记忆演化后新 id 自然重新检查。邻居扫描记录只在该记忆所有候选对都有检查记录后才写
- LLM 输出不合法、请求失败或问题判定缺少 `detail` 时，记入本轮错误、不写检查记录，本轮跳过该项、下一轮重试；一条判不出的记忆不会挡住后面的检查。不当作相容
- 新增 migration `0004_maintenance_findings`：`memory_findings`（open / resolved / dismissed）与 `memory_checks`（主键 `check_type + subject`，pair 的 subject 为排序后的两个 id）。不复用 `memories.conflict`（它表示「本版本由冲突合并产生」）
- `VectorStore.cosine_neighbours`：用已存向量查余弦近邻，LanceDB 调用放在 `asyncio.to_thread`，不重算 embedding
- REST：`GET /api/v1/findings?status=&kind=`（只含发现，不含检查记录）。标为误报的接口归 Web 治理台（#6）。MCP 不变
- 线上首轮（积压 314 条 conflict=1 与 3903 条邻居扫描）：5 轮共 436 次 LLM 调用。邻居扫描阶段容器 CPU 中位约 230%、持续约 6 分钟，前台 recall 中位数不变、p95 668→830 ms、最大 2.5 s；清完积压后的轮次 CPU 峰值约 13%。全文抽查：跨 key 重复精确率 93%（14/15）；内部矛盾首版提示词 20%，收紧（同一对象同一属性、逐字引两段原文、排除缺陷记录 / 不同范围 / 已标明取代的演化）后 80%（含需人判断的边界项）；跨 key 矛盾 0%（13 条全是周期任务不同次执行），按决定去掉，配对只判重复 / 相容
- 测试：`tests/test_maintenance.py`（含 REST 202/409、预算分配与续跑、判定失败不阻塞、自动关闭、recall 在维护运行中不被阻塞）、`tests/test_migrations.py`、`tests/test_vector_backend.py`

### 2026-10-30 recall 混合检索（#4）
- 动机：纯向量对型号、版本号、数字这类字面信息不敏感。线上只读模拟（3903 条 current）：30 条「中文问法 + 稀有型号 / 版本串」查询，纯向量前 3 命中 3 条
- 新增 `engine/hybrid_search.py` `search(query, limit, entity_type=None)`：向量、FTS5、图一跳三路各取前 50（`CANDIDATES_PER_SOURCE`），加权 RRF（`k=60`，FTS 权重 `FTS_WEIGHT=2`）融合。等权时上述查询前 3 命中 9 条，FTS ×2 时 14 条；7 条原本命中的查询不退化。参数为模块常量，不加环境变量
- FTS 查询：jieba 切词，每个词按 FTS5 字符串加引号（双引号转义），去掉不含字母数字的词，以 OR 连接；切词为空时跳过 FTS
- 图一跳：前两路融合后前 5 个 `entity_key` 作为种子，取一跳邻居的 current 记忆，排除种子本身，最多 50 条。线上 `relations` 为 0 行，这一路目前没有贡献
- 时间衰减 `DECAY_LAMBDA` 默认 0（关闭），只有评估集显示有收益时才打开
- `MemoryRepository.fts_search` 只返回 current（FTS 索引含全部历史版本），支持 `entity_type`；改为 `CROSS JOIN`，强制先走 FTS：普通 JOIN 下 planner 从 `idx_memories_current` 出发，对每条 current 执行一次 MATCH，3.9k 行时 1.7–7.6 秒，改后约 10 ms。新增 `get_current_by_entity_keys`
- `VectorStore.search` 新增 `overfetch`（默认 4，行为不变）；混合检索无类型过滤时用 1：向量索引只存 current，ANN 后不会再丢结果，取 200 条比 50 条多约 55 ms
- `recall` 改为调用混合检索，MCP 与 REST 同时生效。MCP 入参与返回字段不变；`relevance` 改为融合分数，只保证同一次结果内越大越相关，tool description 已写明。REST `GET /api/v1/memories/search?explain=1` 额外返回 `vector_rank` / `fts_rank` / `graph_rank` / `rrf_score`
- 本地耗时（不含 embedding 请求，3903 current + 5603 历史版本，LanceDB 1536 维）：纯向量中位数 34 ms，混合检索 52 ms，增量约 18 ms
- 测试：`tests/test_hybrid_search.py`、`tests/test_retrieval_quality.py`（固定语料，含纯向量对照）；`tests/test_transport.py` 断言 `recall` 返回字段集合不变且拒收 `explain`

### 2026-10-30 测试关闭 SQLite 连接（#3）
- 存储测试在 `anyio.run()` 返回后才关闭 aiosqlite 连接，worker 线程把结果投递到已关闭的事件循环，pytest 报 `Event loop is closed`。三个存储测试文件改为在同一事件循环内关闭各自打开的 store

### 2026-10-30 例行备份
- 新增 `ops/backup-db.sh`：在 compose 目录执行，经容器内 Python 用 SQLite backup API 拷出一致快照（服务运行中也可执行），`integrity_check` 通过后再复制向量库，写入 `data/backups/<UTC 时间戳>/`，只在本次备份校验通过后才删除最旧的，保留 7 份。由部署主机的 cron 每日执行；部署同步排除 `data/`，不会删掉备份
- 恢复：停服务，用某个备份目录里的 `memory.sqlite3` 和 `vectors/` 覆盖 `data/` 下同名文件，再启动

### 2026-10-30 删除 working_memory_cache 表
- 新增 migration `0002_drop_working_memory_cache`：Working Memory 简报已删除，该表没有任何读写方；`downgrade` 按 0001 的定义重建空表。`schema.sql` 与 `tests/test_migrations.py` 同步，`/health.schema_version` 变为 `0002_drop_working_memory_cache`

### 2026-10-30 清理失效功能
- 动机：服务只通过 MCP 的 4 个工具和用户级 AGENTS.md 引导使用，不再走 hook；v1 线上实例已退役、数据已迁完；Nowledge 已全量导入并停用。以下代码和文档已无使用方，留着只会误导读者
- 删除 `claude-code-plugin/`（session-start / stop hook、skills、commands）
- 删除 Working Memory 与对话提取：`engine/working_memory.py`、`engine/extraction.py`，REST `GET /api/v1/wm`、`POST /api/v1/memories/extract`，CLI `mem wm`、`mem extract` 及 client 对应方法，相关测试。`key_assignment` / `merge` / `llm` 仍被 `remember` 使用，保留。`working_memory_cache` 表保留在 schema 中（删表需要新 migration）
- 删除 v1 迁移：`scripts/migrate_v1_to_v2.py`、`tests/test_migrate_v1_to_v2.py`、`tests/fixtures/`，以及 `.gitignore`、ruff `extend-exclude` 里对 fixture 的例外；`storage/migrate.py` `run_migrations` / `_make_config` 的 `db_path` 参数随之无调用方，一并删除
- 删除 Nowledge 导入：`scripts/import_nowledge.py`、`tests/test_import_nowledge.py`；`scripts/` 包已空，删除。`remember_tool` 的仅进程内参数 `embedding` / `created_at` 与 `evolve_memory` 的 `created_at` 只有导入脚本和 Extraction 在用，一并删除，新节点时间一律取当前时间
- 删除 `docs/prd.md`（2024 年初版 PRD，架构与工具清单已过时）、`docs/behavioral-guidance.md`（基于 `mem` CLI 与 `mem wm` 的提示词，已被用户级 AGENTS.md 引导取代）
- 文档与代码中的生产主机别名和面板名改为中性说法（仓库公开）
- 删除 `docs/superpowers/`（2026-03 extension 与 2026-05 Agent Kernel 的 spec 和 M1–M6 plan）：M1 已落地，M6 已用其他方式完成，M3 不做；M2 混合检索、M4 后台维护、M5 Web 治理台中仍成立的部分已转为 GitHub issue #4、#5、#6
### 2026-10-30 Agent skills 配置
- 新增 `docs/agents/`（issue-tracker / triage-labels / domain）与本文件 `## Agent skills` 一节：issue 走 GitHub Issues，分诊标签沿用默认五个（已在 GitHub 补建 needs-triage / needs-info / ready-for-agent / ready-for-human），领域文档为单上下文布局
- 项目 backlog（含 C 档积压）以 GitHub Issues 为准

### 2026-10-29 MCP 接口收敛为 4 个工具
- 动机：agent 只靠 MCP + 用户级 AGENTS.md 引导主动存取记忆。原 `remember` 要求调用方自起 `entity_key`，不同会话起的 key 会漂移，同一主题无法合并演化；8 个工具里多数与主动存取无关；`memory:///current`、`memory:///entities` 一次返回全部记忆，导入后 9000+ 条会撑爆客户端上下文。当时没有 MCP 客户端在用，不保留旧 MCP 契约
- MCP 只剩 `remember(content, title?, tags?)`、`recall(query, limit?)`、`forget(memory_id, reason?)`、`trace(entity_key, format?)`，schema 均 `additionalProperties: false`（多传参数返回 `Input validation error`）；description 写明各自使用时机
- 移除 MCP 的 `recall_all` / `relate` / `unrelate` / `graph_query` 工具与全部 resources / resource templates：`Server` 不再传 resources handler，initialize 不再声明 resources 能力，`resources/list` 返回 method not found。tool 函数、REST 路由、CLI 子命令保留
- `remember_tool`：`entity_key` / `entity_type` 改为可选（必须成对出现）；缺省时用同一份 embedding 调 `assign_entity_key` 分配，并跳过语义合并路径（key 分配已对照过最相似的 current 记忆，与 Extraction 一致）。显式传 key 的调用方（导入脚本、Extraction）行为不变；REST `POST /api/v1/memories` 同样可不传 key
- `forget_tool` 新增 `memory_id`：归档该条 current 记忆（写法与按 `entity_key` 归档相同）；id 不存在或不是 current 时抛错，MCP 返回 `{"error": ...}`；按 `entity_key` 的 REST / CLI 用法不变。未新增 REST 路由（`DELETE /api/v1/memories/{...}` 已被按 `entity_key` 归档占用）
- `recall` 返回项新增 `memory_id`，供 `forget` 使用
- `tests/test_transport.py` 契约测试改为 4 个工具 + 无 resources，并走通 remember（服务端分配 key）→ recall → forget → recall 流程

### 2026-10-29 部署改为宿主机反代，去掉 cloudflared
- 生产迁到新主机，由宿主机上的反向代理（host 网络）终结 HTTPS：`docker-compose.yml` 删除 cloudflared 服务，`memory-mcp` 只映射 `127.0.0.1:18765:8765`；`.env.example` / README 删除 `CLOUDFLARE_TUNNEL_TOKEN`
- `docs/testing.md` 手工集成步骤同步为 4 个 MCP 工具

### 2026-10-30 向量表跨进程可见
- `LanceVectorBackend` 以 `read_consistency_interval=0` 连接：服务进程每次读都检查新版本。原先服务一直使用启动时打开的快照，导入脚本等其他进程写入的向量要重启服务才能检索到（Nowledge 增量导入后实测）

### 2026-10-30 演化写入顺序
- `evolve_memory` 新增 `fields`，`remember` 把 origin_client / origin_session_id / source_thread_id / source_refs / title 随新节点一次 insert 写入，不再演化后补一次 update。原先两次写入之间中断会留下缺来源的 current 记忆，导入去重也认不出它（全量导入中实际出现 1 条）
- 先 insert 新版本、再把旧版本置为非 current：中断时最坏是同一主题有两条 current，而不是一条都没有

### 2026-10-30 key 规范化与合并输出容错
- `assign_entity_key` 新建 key 时不再因格式拒收：转小写，subject 中非 `[a-z0-9_]` 字符替换为 `_`，以 key 前缀作为 entity_type；规范化后命中邻居 key 则沿用。仍拒收没有 `type:` 前缀或 subject 为空的输出。全量导入中 4 条失败来自主机名、`qwen3.6` 这类 subject 与前缀/类型不一致
- `merge_memories` 以 `json.loads(strict=False)` 解析，接受 content 字符串里的字面换行；解析失败时报错带 JSON 错误位置与上下文。全量导入中 20 条合并失败为偶发输出不规范，原样重试即通过

### 2026-10-30 向量索引只存 current 并定期压实
- `VectorStore` 向量索引只保留 current 记忆：`insert` 只写 current 节点的向量，`update` 把节点置为非 current 时删除其向量，不再重写未变化的向量（内容变化一律是新节点）。所有检索都过滤 current，旧版本留在索引里会挤占 ANN 候选，长演化链上甚至会让 current 那条落到候选之外
- `LanceVectorBackend` 每 200 次写入执行一次 `optimize(cleanup_older_than=1h)`：原先每次写入新建一个 fragment 和 version，导入约 5.8k 条后积累 9479 个 fragment、18960 个 version、4.3GB，单条导入从约 5 秒退化到约 22 秒

### 2026-10-30 删除线程表与线程溯源字段
- 新增 migration `0003_drop_threads`：删除 `threads` / `thread_messages` / `thread_messages_fts` 及其索引与触发器，删除 `memories.source_thread_id` / `source_refs` 两列、`idx_memories_source_thread_id` 与指向 `threads` 的外键。线上这两张表与两列均无数据，代码也不再读写
- SQLite 无法删除带外键的列，`memories` 按官方 12 步流程重建：在 alembic `autocommit_block` 里先关外键再显式 `BEGIN`（PRAGMA 在事务内不生效），`INSERT ... SELECT rowid, ...` 保留 rowid（`memories_fts` 是按 rowid 对应的 external-content 索引），重建索引与 FTS 触发器后执行 FTS `rebuild`，`foreign_key_check` 非空即回滚并报错，提交后重新开外键。downgrade 用同一流程恢复线程表与两列（取 NULL）
- `MemoryNode` 删除 `source_thread_id` / `source_refs` 与 `SourceRef`；`remember` 不再读取这两个参数，REST 请求体带上时静默忽略；MCP schema 不变
- `schema.sql` 同步为 0003 之后的结构；`tests/test_migrations.py` 覆盖升级、降级前后的行数、rowid 与 id 对应、FTS 命中、外键与完整性检查

### 2026-10-29 LLM 调用关闭推理
- `engine/llm.py` `chat()` 与 `check_conflict` 的请求统一带 `reasoning: {enabled: false}`（`NO_REASONING`）：OpenRouter 对部分模型（如 deepseek-v4.1-flash）默认开启推理，实测单次合并 10–28 秒、推理 token 最多约 8000，且偶发 content 为空；关闭后 1.7–3.3 秒，输出长度相当

### 2026-10-28 MCP Python SDK 迁移到 2.x
- 依赖约束 `mcp>=2.0,<3`；`requirements.lock`（`pip freeze | LC_ALL=C sort`，以旧锁为约束重解）与 `uv.lock` 同步更新
- `server.py` 由 1.x 装饰器注册改为 2.x `Server(..., on_list_tools/on_call_tool/on_list_resources/on_list_resource_templates/on_read_resource)` 构造参数，handler 签名 `(ctx, params)`，返回完整 Result 类型
- 2.x lowlevel 不再做 tool 入参 jsonschema 校验，`call_tool` 自行校验并保持 1.x 报错形态（`is_error=True` + `Input validation error: ...`）
- 对外 MCP 契约不变：8 个 tool、参数 schema、JSON 字符串返回、resources、`/mcp` 端点与 Bearer 鉴权；`transport/` 无需改动（`StreamableHTTPSessionManager` 签名未变）
- `tests/test_transport.py` 改用 2.x 进程内 `mcp.Client` 走真实协议分发，新增契约测试（tool 列表、校验报错、resources）
- 修复非 editable 安装（Dockerfile `pip install --no-deps .`）启动即崩：`storage/migrate.py` 改为按包内路径定位 migrations，`alembic.ini` 仅承载日志配置、找不到时省略（原先向上找 pyproject.toml 失败抛 `RuntimeError`）

### 2026-10-28 Nowledge 导入：key 分配 / 合并演化 / 冲突检测显式失败
- 新增 `engine/llm.py` `chat()`（单轮 OpenRouter 调用，HTTP/传输错误直接抛出），供 key 分配、合并、提取复用
- 新增 `engine/key_assignment.py` `assign_entity_key`：取 5 条最相似的 current 记忆给 LLM，同主题复用其 entity_key（类型以库内为准），否则新建 `<entity_type>:<snake_case>` key；请求失败或输出不可用抛 `KeyAssignmentError`
- Extraction Engine 的提取 LLM 只输出 `[{"content": ...}]`，entity_key/entity_type 一律由 `assign_entity_key` 对照库内记忆分配
- `check_conflict` 在请求失败、非 200、响应畸形、答案非 YES/NO 时抛 `ConflictCheckError`，不再当作「无冲突」
- 复用 key 时合并演化（`engine/merge.py` `merge_memories`）：`remember` 的两条演化路径在演化前让 LLM 把旧 current 与新内容合并为一条（保留不冲突的事实、冲突处以新内容为准、去重、保留 `[YYYY-MM]` 日期标注），新版本存合并结果并按合并文本重算 embedding；同 key 路径由这次合并调用同时给出 conflict（替代 `check_conflict`），语义合并路径仍先由 `check_conflict` 决定是否演化；合并结果与旧 current 相同返回 `no_change`；tags 取旧版与新输入的并集；合并失败抛 `MergeError`，不写库、不回退为整体替换。MCP / REST `remember` 同样生效，对外参数与返回字段不变
- `remember_tool` / `evolve_memory` 新增仅进程内可用的 `created_at` 参数：新节点 `created_at`/`valid_from` 与被演化旧节点的 `valid_until` 用该时间，未传时为当前时间；不暴露给 MCP/REST
- 新增 `python -m memory_mcp.scripts.import_nowledge --input <nmem --json m list 输出> --state <state.json> [--limit N] [--dry-run]`：`m list` 列出的全部记忆按 `created_at`（必须带时区）升序逐条分配 key 后经 `remember_tool`（`skip_semantic_merge`）写入，透传原 `created_at`、`origin_client=nowledge`、`origin_session_id=<Nowledge id>`、labels 作 tags；state 文件记录已完成与失败 id，可断点续跑；每条处理前先查库（`origin_client=nowledge` 且 `origin_session_id` 命中即视为已导入），写库后、存 state 前中断也不会重复提交；`--dry-run` 只解析排序，不调 LLM、不写库、不建 state 文件
- 合并提示词改为「保留长期有效事实、丢弃被新版本淘汰的阶段性状态（如旧进度快照）、结果 ≤1500 字」：试跑中逐条合并进度日志会把单条记忆滚到 1.1 万字以上，单条导入耗时随之升到约 21 秒
- 导入脚本 `--input` 可重复，多个来源按 `created_at` 穿插导入；记录可自带 `origin_client`（v1 线上数据用 `memory-mcp-v1`），续跑去重按 `origin_client + origin_session_id`；跳过 `memory-mcp-full-archive-*`（旧库整包转储，每条混装约 20 条无关记忆），v1 数据改为逐条导入
- key 分配与合并失败的报错带上底层异常，便于区分网络错误与模型输出问题

### 2026-05-21 M1 存储底座（v2 schema）
- 引入 SQLite v2 主存储（aiosqlite + alembic 1.18 + WAL/FK/busy_timeout pragmas）
- 新建 `0001_initial_v2` migration：memories / memories_fts / entities / relations / threads / thread_messages / thread_messages_fts / jobs / working_memory_cache + 全部索引 + FTS5 触发器
- LanceDB 精简到 `(id, vector)`，元数据全部走 SQLite；`VectorStore.search` 改为「ANN 取候选 ID → SQLite WHERE id IN (...) 拼装 MemoryNode」
- `GraphStore` 改为运行时按需把 `entities`/`relations` 加载进 `nx.MultiDiGraph`，写时双写，废弃 `data/graph/*.json` 持久化与 `evolution_chains.json`
- `MemoryNode` 增加 v2 字段：title / title_tokens / content_tokens / review_status / origin_client / origin_session_id / source_thread_id / source_refs / access_count / last_accessed_at / reinforce_count
- 应用层 jieba 分词，写入 memories 时自动填充 `content_tokens` / `title_tokens`，支持 `MEMORY_MCP_JIEBA_USER_DICT` 自定义词典
- 新增 `python -m memory_mcp.scripts.migrate_v1_to_v2 --src ... --dst ... --backup ... --dry-run --verify` 一次性迁移脚本（review_status 全部标 `legacy`）
- FastAPI lifespan 启动时自动跑 `alembic upgrade head`（`MEMORY_MCP_AUTO_MIGRATE` 控制）；`/health` 新增 `schema_version` 字段，`status` 由 `healthy` 改为 `ok`
- CLI 新增 `mem db upgrade/downgrade/current/history` 子命令（M6 runbook 离线运维入口）
- 7 个原有 MCP tools 对外契约保持不变；新字段全部默认值；hybrid search / memory_crud / threads / worker 留给 M2-M4

### 2026-04-29 Relation 删除能力与交付规则
- 新增 `unrelate` MCP tool，用于按 `relation_id` 删除实体关系边
- 新增 REST API `DELETE /api/v1/relations/{relation_id}`，返回 `deleted/not_found`
- CLI 新增 `mem unrelate <relation_id>`
- 明确交付规则：线上服务更新并验证通过才视为任务完成

### 2025-12-20 Streamable HTTP 与 PRD 补齐
- 替换 SSE 集成为 Streamable HTTP，会话由 SDK 管理
- 补齐 recall_all、资源读取、演化规则、图深度查询与归档原因
- 修复配置/存储问题并补充测试与文档
- 修复 Dockerfile 构建顺序，避免缺少源码/README 导致安装失败
- 增加向量存储 InMemory 后备实现（`MEMORY_MCP_VECTOR_BACKEND=memory`），提升可测试性与环境兼容性
- 补齐各子包 `__init__.py` 并拆分认证中间件到 `src/memory_mcp/transport/auth.py`
- `remember` 在 entity_key 命中时也执行冲突判定，并输出 `labels`（`conflict/correction/reversal`）用于打标与追溯
- `docker-compose.yml` 移除 8765 端口暴露，cloudflared 仅通过环境变量注入 token

### 2025-12-21 修复 Streamable HTTP 启动崩溃
- 修复 `StreamableHttpApp.lifespan` 方法签名以兼容 Starlette `lifespan(app)` 调用，解决容器启动 `TypeError` 崩溃
- 增加回归测试 `tests/test_transport.py`，确保生命周期钩子可正常进入/退出

### 2025-12-21 文档与开源协议完善
- 扩充 `README.md`（中文）功能介绍与使用说明，并新增英文版 `README.en.md`
- 新增 `LICENSE`（MIT License），便于 GitHub 开源分发

### 2026-03-25 Extension: REST API + CLI + Working Memory + Extraction + Plugin
- 新增 REST API (`/api/v1/*`) 作为辅助传输协议，复用现有 tool 函数
- 新增 `mem` CLI 客户端（httpx + typer），位于 `cli/` 目录
- 新增 Working Memory 引擎 — 模板拼接 briefing，无需 LLM
- 新增 Extraction Engine — LLM 从对话记录中提取候选记忆
- `remember_tool` 新增 `skip_semantic_merge` 参数，防止自动提取时跨实体污染
- 新增 Claude Code 插件（hooks: session-start/stop, skills, commands）
- AuthMiddleware 错误格式统一为 `{"ok": false, "error": ...}`
- 协议约束更新：MCP 主 + REST 辅

### 2026-03-25 Review Fixes: CLI / Extraction / Test Runner
- 修复 CLI `relate` 请求字段名错误，避免向 REST API 发送 `from_key/to_key` 导致 400
- CLI `remember` 补充 `--tags` 支持，并透传到 REST API
- Extraction Engine 在 LLM 调用失败时显式抛错，不再伪装为 `200 + empty results`
- 移除 `cli/tests/__init__.py`，修复根目录 `pytest` 因双 `tests` 包冲突导致的收集失败

### 2026-04-28 Production Deploy Hardening
- Dockerfile 改为使用 `requirements.lock` 安装锁定依赖，再以 `--no-deps` 安装本地包，降低重建时依赖漂移风险
- `MEMORY_MCP_VECTOR_BACKEND=lancedb` 下 LanceDB 初始化失败会直接中止启动；`memory` 与 `auto` 保留测试/兼容场景
- `/health` 返回当前 `vector_backend`，便于部署后确认实际存储后端
- Extraction Engine 返回单条候选写入失败的 `errors/failed`，便于排查部分写入失败

### 2026-05-21 v2 Agent Kernel Phase 1 设计与实施计划
- 新增 spec `docs/superpowers/specs/2026-05-21-memory-mcp-agent-kernel-design.md`（13 个核心决策 D1-D13），覆盖 SQLite 主+Lance 副存储收敛、v2 schema 9 字段扩展（α/β/γ/δ/ε 五组）、Threads 完整归档、Hybrid Search、Web UI 治理台、Background Worker、生产破坏性迁移
- 新增 6 个 milestone plan（M1-M6，共 123 task / 579 step），每个 milestone 独立可 merge；待 M1 起实施
- 关键架构方向（实施中陆续生效）：存储收敛 SQLite 主+Lance 副、MemoryNode v2 字段扩展、Threads per-provider adapter、RRF hybrid search、cookie session Web UI、asyncio 同进程 worker、本地 CLI 推送式 sync
- 命名规范确立：分页响应字段 `items`（非 `results`）；REST by-id 路径 `/api/v1/memories/{id}`；CLI 引入 `mem db/memory/thread` 子命令簇；`/health` 字段固定 `{status, vector_backend, sqlite_path, schema_version}`
- 经 codex 交叉评审 + fix subagent 修复跨 plan 契约：7 项 Blocking（SQLite 抽象、MemoryNode v2 类型序列化、Thread FK 顺序、Worker DB 路径、REST/SPA DTO、M6 runbook 依赖、migration --dst）+ 6 项 Recommended + 4 项 Nice-to-have 全部清理
- Web UI 自动化 e2e 采用 agent-browser（不引入 Playwright 工具链）
