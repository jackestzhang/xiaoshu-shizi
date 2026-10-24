# 小书 · 识字绘本 Demo

给 3–4 岁孩子的**离线**识字 App，加一条**受字表约束**的内容流水线。

- 儿童端：HTML + WebView 壳，双击 `app/index.html` 就能跑，无网络、无账号、无第三方 SDK。
- 内容端：Python 流水线，管字表、校验、配音、场景、打包；模型只负责写故事，流水线负责不让它超纲。
- 家长端：每个字的曝光/点读/跨天/测验，全部由**原始事件**现算；可标注，可导出。

当前 Demo：4 节课、119 个字、13 张 AI 插画。L03《守株待兔》7 页、L04《鲤鱼跃龙门》6 页，都是每页 17–22 字的长故事。

---

## 30 秒跑起来

```bash
# 1. 直接看 Demo（单文件，音频内联，预览器里也能出声）
open dist/shizi-demo.html    # macOS
# xdg-open dist/shizi-demo.html

# 开发时看多文件版（同样可双击）
open app/index.html

# 2. 改完内容后重新打包
python3 pipeline/build.py    # 语音 + data.js
python3 pipeline/bundle.py   # 单文件 Demo（内联全部音频）

# 3. 一口气检查：课程校验 + 前后端口径一致
python3 tests/run_checks.py

# 4. 真 DOM 回归 + 截图（需要 playwright + chromium）
python3 tests/ui_check.py
python3 tests/bundle_check.py   # 单文件在沙箱 srcdoc 里也能出声
```

导出给 Android：`python3 pipeline/pack.py` → `dist/shizi-web.zip`（266 KB）。

> **预览里点了没声音？** 用 `dist/shizi-demo.html`。它把 29 段音频转成 base64 内联，
> 运行时零外部请求，因此不受预览沙箱对相对路径的限制。
> 打开后点「家长 → 测试声音」，会直接告诉你这台设备有没有放出声音。

---

## 现在有什么

| 模块 | 内容 |
|---|---|
| 儿童端 | 整页插画（不可点）+ 文字点读、长按大字卡、翻页、整页朗读；卡片课；长句自动收字号 |
| 家长端 | 学习报告（119 字 × 8 列）、会/不会/? 标注、听音找字 5 题、导出 JSON、清空 |
| 流水线 | `prompt` → `lesson` → `review` → `art` → `build` → `pack`；`validate` 随时可跑 |
| 数据 | 追加式事件日志（localStorage），报表在 JS/Python 两侧各算一遍并逐字比对 |
| 素材 | 119 个字 + 119 个词 + 13 句整页 = 251 段语音，3.4 MB；13 张插画 2.1 MB |
| 画面 | 13 张整页 AI 插画（1280×768 WebP），L03 七页 + L04 六页 |
| 单文件 | `dist/shizi-demo.html` 6.9 MB，CSS/JS/插画/音频全部内联 |
| 测试 | 课程校验、约束拒绝路径、前后端口径一致、10 项 UI 回归 |

### 两本长故事

| 课 | 页数 | 字数 | 新字 | 预备课 | 插画 |
|---|---|---|---|---|---|
| L03 守株待兔 | 7 | 133（17–20/页） | 63 | 约 11 节 | 7 张 |
| L04 鲤鱼跃龙门 | 6 | 115（18–20/页） | 51 | 约 9 节 | 6 张 |

两本都是正式课程，页面和标签不做特殊标记。共同点：

- 课程 JSON 里 `page_limit: 20`，覆盖默认的 10/12 字上限；`validate` 会提示「高于 3–4 岁建议」，但不拦
- 第 1 页定妆，其余页**都以第 1 页为参考图**（不链式），参考强度按改动幅度从 0.8 降到 0.62
- 手机端 390px 下长句会自动收字号（41px → 33px），不会撑破卡片

> 页长上限是**课程级参数**，不是全局开关。以后做 5–6 岁长故事，改课程 JSON 即可，不用动代码。
> 两本书合计 6.9 MB（音频 3.4 MB + 插画 2.1 MB），单文件在手机上首次加载约 1–2 秒。

---

## 目录

```
shizi/
  app/                 儿童端（可直接打开）
    index.html
    app.js  scene.js  track.js  app.css
    sprites.js         由 pipeline/sprites.py 生成
    data.js            由 pipeline/build.py 生成
    assets/audio/      内容哈希命名的 MP3
    assets/art/        整页插画 WebP（审核通过才进来）
  pipeline/
    sprites.py         精灵图库 + 布局常量（无插画时的回退）
    scene.py           文案 → 回退场景布局
    art.py             整页插画：提示词 → 生成/导入 → WebP → 审核
    shotlist.py        分镜单：每页文案 + 画面 + 一键复制提示词
    prompt.py          生成受字表约束的写故事提示词
    lesson.py          新建/重生成课程草稿（不合规不写文件）
    validate.py        字表、页长、拼音、场景、音频校验 + 词汇预算
    review.py          文案审阅页；--ok 才解锁打包
    build.py           合成语音 → data.js + sprites.js
    bundle.py          把 app/ 打成一个自包含 HTML（音频 base64 内联）
    pack.py            打 zip + manifest（带每个文件的 sha1）
    report.py          读导出的 JSON，出和家长面板一致的报表
  art/
    L03/prompts.txt    三页提示词（可直接拿去即梦/豆包）
    L03/p*.png         生成源图（审核前）
  data/
    curriculum.csv     71 字示例字表（20 基础 + 51 长故事，拼音人工核过）
    lessons/*.json     课程
  tests/
    run_checks.py      一键检查
    ui_check.py        Playwright 回归
    bundle_check.py    单文件 + 沙箱 srcdoc 的出声回归
    parity.js          JS 侧算一遍，供 Python 比对
    make_events.py     可复现的示例数据（含 20ms 误触会话）
    shots/             回归截图
  review/              审阅页产物
  android/             WebView 壳代码与说明（未编译）
  dist/
    shizi-demo.html    单文件 Demo（6.9 MB，零外部请求）
    shizi-web.zip      Android assets 包
```

---

## 一课是怎么出来的

```bash
# 1. 先生成提示词（把已学字、目标新字、页长限制都写死进去）
python3 pipeline/prompt.py --order 4 --new "边 有 树" --pages 3 --idea "山边有树，树下有水"

# 2. 把提示词贴给任意 LLM，让它只返回 JSON，存成 draft.json

# 3. 导入并校验；超纲、缺拼音、页太长都会被拦住，不写文件
python3 pipeline/lesson.py --id L04 --order 4 --from-json draft.json

# 4. 看文案；确认后才允许出语音
python3 pipeline/review.py --id L04
python3 pipeline/review.py --id L04 --ok --build

# 5. 插画：出提示词 → 生成/导入 → 审核
python3 pipeline/art.py --id L04 --prompts
python3 pipeline/art.py --id L04 --import art/L04
python3 pipeline/art.py --id L04 --ok

# 6. 打包
python3 pipeline/pack.py
```

也可以完全跳过 LLM，手写文案：

```bash
python3 pipeline/lesson.py --id L04 --order 4 --pages "山边有树。|小兔跑来。|他等兔。"
```

**校验失败长这样**（真的会拒绝写文件）：

```
没有写文件。问题：
  ✗ 第1页超纲字：去 河 捉 鱼
  ✗ 第1页字表里没有：去 河 捉 鱼

先补字表：把 去 捉 河 鱼 加进 data/curriculum.csv（拼音要人工核过）
```

---

## 生成流程与输入参数

整体是 7 段。模型只负责第 2 段，其余都是约束、校验和审核。

```text
curriculum.csv + 已有课程 + 参数
        │
        ▼
① prompt.py      生成受字表约束的提示词（不调用模型）
        │
        ▼
② 任意 LLM       返回 draft.json（text + visual）
        │
        ▼
③ lesson.py      字表 / 页长 / 拼音校验；不合规不落盘，status=draft
        │
        ▼
④ review.py      人工看文案；--ok 才变 confirmed
        │
        ▼
⑤ art.py         提示词 → 出图 → 导入 → 审核 approved
        │
        ▼
⑥ build.py       配音 + data.js；任何 draft 一律拒绝
        │
        ▼
⑦ bundle.py / pack.py
```

### 核心参数

| 参数 | 作用 | 常见错误 |
|---|---|---|
| `--order` | 决定「已学字」：所有 order 更小的课都算教过 | 当成文件名；填错会导致允许字集全错 |
| `--new` | 本课允许出现的新字，必须在 `curriculum.csv` 里 | 一次塞 15 个字 → 孩子读不动；建议 ≤6 |
| `--pages` / `--chars-per-page` | 页数 / 每页汉字数（标点不算） | 只加页数不减字数，词汇预算会爆 |
| `--idea` | 故事想法，只进提示词，不参与校验 | 把「必须出现某字」写在这里，模型仍可能超纲 |
| `--page-limit N` | 本课单页汉字上限（覆盖默认 10/12） | 设了就是软硬同值；长故事 20，普通课不要加 |

### 允许字集怎么算

```text
allowed = {curriculum.status = known}
        ∪ {所有 order < N 的课的字}
        ∪ --new
```

每页每个字都必须在 `allowed` 里；`--new` 里的字也必须在 `curriculum.csv` 里。
两种口径：

```bash
python pipeline/validate.py --gap L03 --baseline known    # 假设不补预备课
python pipeline/validate.py --gap L03 --baseline before   # 算上更早的课
```

### LLM 的返回契约

```json
{
  "title": "四个字以内",
  "world": "角色长相 + 场景构成，供插画复用",
  "new_chars": ["边", "有", "树"],
  "pages": [
    {"text": "第一页文案。", "visual": "这一页画什么：谁、在哪、做什么、镜头"}
  ]
}
```

`text` 是给孩子读的，`visual` 是给画图模型的；两者必须对得上。
`lesson.py --from-json` 会同时导入这两个字段。

### 插画参数

| 参数 | 作用 |
|---|---|
| `--prompts` | 生成 `art/<ID>/prompts.txt`，另附每页纯文本 `p1.txt…` |
| `--import DIR` | 批量导入 p1/p2/…，裁成 1280×768 WebP，status=draft |
| `--prompt N "..."` | 改第 N 页的**画面描述**，画风/设定仍自动拼接 |
| `--prompt N "..." --full` | 第 N 页使用**完整自定义提示词**（高级） |
| `--regen N` | 只重生成第 N 页（需要 `SHIZI_IMG_KEY`） |
| `--replace N FILE` | 用自己的图替换第 N 页 |
| `--ok N` | 只通过第 N 页；`--ok` 不带页码则全部通过 |
| `--versions N` | 列出第 N 页的历史版本 |
| `--provider openai` | 批量调用 OpenAI 兼容接口 |
| `--size` / `--quality` | 出图尺寸与质量，默认 `1536x1024 / high` |

每次 `--replace` / `--regen` / `--import` 都会先把旧图备份到 `art/<ID>/versions/`，
新图一律是 `draft`，必须 `--ok N` 才能进包。

改文案也会让该页插画自动变成 `draft/stale`（`review.py --text`），
`build.py` 会拒绝打包，直到你重新通过这一页。

## 五个设计决定

### 1. 字表是输入约束，不是事后审计

原方案是"先写故事，再统计缺多少字"。但 3 页 30 个字，搜索空间小到完全可以反过来做：把「已学字 + 本课新字」作为允许集，生成后校验，不通过就不落盘。

`validate.py --gap` 会同时给你两个视角：

```
只算已会字：全篇 21 字，需要 12 个新字 → 先上约 2 节预备课
算上更早的课：0 个新字 → 这本可以现在读
```

所以《守株待兔》不是"需要 17 个新字所以做不了"，而是"先上两节字卡课，然后它变成一本孩子能自己读的书"。

### 2. 整页插画，交互只在文字层

图和点读已经解耦：

- 一页一张 AI 插画，铺满画面，**不可点**；
- 只有下方文字是按钮：点字出声、长按出大字。

这样就不需要热点坐标，也不存在「图画对了但圈错位」。代价是画风一致性要靠提示词和参考图，而不是靠构造方式。

没有插画的页会自动回退到 SVG 精灵（`sprites.py` + `LAYOUT`），用来占位、试排、断网兜底；精灵不再承担点击。

### 画面：整页 AI 插画怎么生成

```bash
# 1. 生成提示词（画风 + 全书设定 + 每页画面 + 构图）
python3 pipeline/art.py --id L03 --prompts

# 2. 生成分镜单：每页可一键复制提示词（完整版 / 精简版）
python3 pipeline/shotlist.py --id L03
#    也可以直接看 art/L03/p1.txt … p3.txt

# 3. 出图：丢进 art/L03/，命名 p1.png…；不命名也行，按修改时间顺序对应页码
python3 pipeline/art.py --id L03 --import art/L03

# 4. 看图，确认后才允许打包
python3 pipeline/art.py --id L03 --ok
python3 pipeline/build.py
```

也可以走 OpenAI 兼容接口（需要自己的 key）：

```bash
SHIZI_IMG_BASE_URL=... SHIZI_IMG_KEY=... SHIZI_IMG_MODEL=... \
python3 pipeline/art.py --id L03 --provider openai
```

**出图通道排障**：如果内置图片工具报
`host "ai-corpus-backup-*.cos.ap-beijing.myqcloud.com" resolves to a private/internal address (169.254.x.x)`，
不是断网，也不是提示词问题：

- 沙箱内网 DNS 把 COS 域名解析到腾讯云内网网关（`169.254.0.49`），这是正常的内网加速；
- 但图片工具的 SSRF 防护把 `169.254.x.x` 判为“内部地址”，在发起请求前就拒绝；
- COS 本身是可达的（`curl` 能拿到 `Server: tencent-cos` 和正常的 `AccessDenied`）。

修法是把该域名指到 COS 的公网接入点，并同时写两处（`/etc/hosts` 会在工作区重启时还原）：

```bash
IP=82.156.94.17   # 任选，106.119.171.53 / 82.156.94.45 也可
echo "$IP ai-corpus-backup-1258344699.cos.ap-beijing.myqcloud.com" >> /etc/hosts
echo "$IP ai-corpus-backup-1258344699.cos.ap-beijing.myqcloud.com" >> ~/.user_hosts
```

请求的仍是同一个 COS 服务、同一张证书，不涉及绕过认证。

`shotlist.py` 仍保留：外部出图、或想逐页挑提示词时用它；
每页一张卡片，点按钮就能复制提示词；命名乱了也能按修改时间顺序导入。

提示词的关键不是形容词，而是**画面描述要可画**：
`visual` 字段是人工写的「这一页画什么」（树在左、兔子从左边跑来、农夫站在树桩旁），
不是给孩子看的文案（「山边有树」不等于「一棵树在画面左侧」）。

- 画风常量在 `pipeline/art.py` 顶部，改一处全书一起变；
- 三页共用同一段 `world`（角色长相、场景构成），第 2、3 页以第 1 页为参考图，避免画风漂移；
- 源图先落 `art/<ID>/p*.png`，转 WebP 后才进 `app/assets/art/`；
- `status=draft` 的插画，`build.py` 会拒绝打包。

> Demo 里的 3 张图就是用平台模型按这套提示词生成的：第 1 页作参考图，第 2、3 页只改动作和时间。
> 源图在 `art/L03/p1.png`…，提示词在 `art/L03/prompts.txt`，可复现或替换。

### 3. 只存事件，不存聚合

```
{kind:"exp",  ts, sid, day, lesson, page, ch}      # 翻到这一页
{kind:"tap",  ts, sid, day, lesson, page, ch, lat} # 点字，lat=出声延迟
{kind:"long", ...} {kind:"read", ...} {kind:"quiz", ok}
{kind:"start"|"end", sid, dur}
```

口径已经改过几次（整课曝光→按页、读一遍不计点击、面板只读、50ms 撤回）。如果落盘的是聚合值，旧数据就再也算不成新口径。现在报表全部现算，`track.js` 和 `report.py` 各一份镜像，`tests/parity.js` 会逐字比对——**两边算出来必须一样**。

### 4. 素材用内容哈希命名

`tts.py` 的键是 `sha1(text|voice|speed)[:12]`。文字一改，旧音频自然失效，不需要"清理缓存"，也不会出现"换了文案还读旧音"。

### 5. 文案没确认，不出语音

`build.py` 只打包 `status=confirmed` 的课。改任何一页文案，`review.py --text` 会自动打回 `draft`。理由是成本：改一句话几秒钟，做错三页语音和插画要重来。

---

## 家长面板怎么读

| 判断 | 规则 | 含义 |
|---|---|---|
| 会（家长）/ 不会（家长）/ ?（家长） | 你手动标的 | **权重最高**，覆盖所有推断 |
| 测验未过 | 测过 ≥2 次，正确率 < 60% | 最硬的证据 |
| 反复点 | 跨天 ≥2 且 点击率 ≥ 0.6 | 可能是不会，也可能是喜欢 |
| 新鲜感 | 同一天连点 ≥3 且只出现在 1 天 | 先别当"不会" |
| 从不点 | 出现 ≥3 次，一次没点 | 可能已会，也可能没兴趣 |
| 待观察 | 其余 | 数据不够 |
| 没看到 | 曝光 0 | 不算会、也不算不会 |

两条防污染规则：

- **按页记曝光**：只翻到第 1 页，后两页的字不算"看过"。
- **50ms 撤回**：停留 <50ms 且一次没点的会话，曝光全部作废（`tests/make_events.py` 里有一个 20ms 的用例）。

---

## 测试

```bash
$ python3 tests/run_checks.py
1) 课程校验  ✓ 3 节
2) 示例数据  71 条事件
3) 前后端比对 ✓ 一致：14 行 × 11 列
4) 示例报表  看过 14/14 字 · 5 次会话 · 点读延迟中位数 36ms
```

```
树  shù   5  2  0.4  4  1  不会（家长）  0/1
兔  tù    3  8  2.7  3  5  测验未过      0/2
水  shuǐ  3  3  1.0  3  2  反复点        1/1
山  shān  3  3  1.0  3  2  会（家长）    1/1
```

`ui_check.py` 覆盖：首屏、轻点只出声、长按不出重复点击、翻页、字卡课、面板 14 行、标注覆盖推断、测验 5 题、导出文件、390px 无横向溢出。

---

## 这个 Demo 的边界

这些是**故意没做**或**只做了壳**的，别当成已完成：

1. **71 字只是示例字表，不是官方 280 字表。** 其中 51 个是为 L04 补的。所有 gap 数字只对这份表成立。换表只需替换 `data/curriculum.csv`（拼音必须人工过一遍，多音字工具单独查一定会错）。
2. **文案是手写的。** LLM 入口是 `prompt.py` + `--from-json`，模型无关，但没有内置 API key，也没有自动重试循环。
3. **语音走百度公开接口**，适合 demo，不适合量产。正式版建议自己录 300 个字：一个安静的晚上、一部手机，音质和情感都比 TTS 好，还没有接口风险。
4. **没有 APK。** `android/README.md` 里有完整的 WebView 壳代码（`WebViewAssetLoader` + 无 `INTERNET` 权限），但本机没有 Android SDK，未编译。
5. **没有云同步、没有多孩子、没有账号。** 数据只在这台设备的 localStorage 里，导出 JSON 就是全部。
6. **没有语音识别。** "孩子读得对不对"这件事，现在只能靠家长标注和听音找字间接判断。
7. **3 张插画是平台模型生成的**，单张约 5–10 credits。多本书建议先做一张角色定妆图，再用 image-to-image 保持角色一致；画风常量在 `pipeline/art.py` 顶部。

---

## 下一步建议

1. **换真字表**，把 `curriculum.csv` 变成唯一真相源，再跑一遍 `validate.py --gap`。
2. **把听音找字做成日常**：每天 5 题，比点击率可信得多；等积累了 2 周数据，再回头调判断阈值。
3. **录自己的声音**：先录基础 20 个字试试，孩子对熟悉声音的反应通常比 TTS 明显。
4. **再上 Android 壳**：把 `dist/shizi-web.zip` 解到 `assets/`，按 `android/README.md` 接 `WebViewAssetLoader`，删掉 `INTERNET` 权限。
5. **最后才扩内容**：一课一课加，每加一课跑一次 `validate + ui_check`，别让 40 节课一次性涌进来。
