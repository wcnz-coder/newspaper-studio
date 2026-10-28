---
name: newspaper-studio
description: 把一份 spec.json（字体/纸张/页数/报头/每节标题+正文+图片）排版成仿新闻纸的报纸、特刊或课堂小报，输出 HTML + PDF + PNG。自动量测试排，保证每版正文不压页脚、图片只缩放不裁剪。用于「做一份报纸」「课堂小报」「特刊」「报纸风海报」「把文章排成报纸」这类任务。
---

# 报纸生产线

输入一份 **spec.json**（内容 + 版式愿望），输出 **HTML / PDF / 逐版 PNG / 跨页预览**。

核心判断：**内容先定，版式让它自己收敛。** 不要手工去试哪张图多宽、字号多大——写进 spec，让脚本反复打印 PDF、量测真实下沿、自动收放，直到每一版都不越界。

---

## 一、先看这张图

```
spec.json ──► render()  ──► HTML ──► Chrome 无头打印 ──► PDF
                  ▲                                      │
                  └──── 收图 / 调字号 ◄── measure() ◄─────┘
```

`measure()` 用 pymupdf 读出每页正文的真实下沿（mm），和 `limit` 比：

- **装不下** → 图片等比收小 5%（`fig_scale`），二分逼近；
- 收到 0.45 还装不下 → 正文字号降 0.3pt 重来（最低 8.4pt）；
- 装得下还有空 → 反向放大图（最多 ×1.35），把版面填满。

所以你只需给一个**大致合理**的图片宽度，剩下的它自己解决。

---

## 二、跑起来

```bash
# 依赖：Chrome 或 Edge、pymupdf、Pillow
python scripts/newspaper.py examples/crane/spec.json            # 出全套
python scripts/newspaper.py examples/crane/spec.json --dpi 300  # 高清位图
python scripts/newspaper.py examples/crane/spec.json --no-fit   # 只按 spec 排，不自动收放
```

输出（与 spec 同目录，可用 `-o` 改）：

```
<name>.html          屏幕版（多版并排、窄屏自动单栏）
<name>.pdf           印刷版，一版一页，可直接打印
<name>-p1.png …      逐版位图
<name>-spread.png    跨页预览（一次看全）
```

---

## 三、spec.json 怎么写

最小可用例子（一版、一节、一张图）：

```json
{
  "name": "my-paper",
  "paper": { "size": "A4" },
  "pages": 1,
  "masthead": { "title": "Daily Something", "subtitle": "A special edition" },
  "sections": [
    { "num": "01", "title": "The Lead", "byline": "By Someone",
      "lede": "一句话把谁、何时、何地、为什么讲清楚。",
      "body": ["第一段……", "第二段……"],
      "figure": { "src": "img/a.jpg", "width_mm": 58,
                  "caption": "<b>CAPTION.</b> 一句话说图里是谁、在哪、在干什么。" } }
  ]
}
```

### 顶层字段

| 字段 | 说明 |
|---|---|
| `name` | 输出文件名前缀 |
| `lang` | `html lang`，影响断词，默认 `en` |
| `paper` | `{"size":"A4"}`；可选 `A3 / A5 / Letter / Tabloid`，或 `{"size":"custom","custom_mm":[210,297]}`；加 `"orientation":"landscape"` 横版 |
| `pages` | 版数。每节写了 `page` 就按 `page` 分；否则按份数均分 |
| `style` | 见下表 |
| `masthead` | 报头：`mark`（是否画鹤）、`kicker{left,mid,right}`、`pre_title`（如 "The"）、`title`、`subtitle`、`thick_above` |
| `running_head` | 第二版起的转页眉 `{left,mid,right}` |
| `footer` | `{left, mid, page:"Page {n} of {total}", marks:2}`；`marks` 是页脚放几只鹤（0/1/2） |
| `fit` | `{limit_mm, min_body_pt, grow, max_iterations}`；`limit_mm` 默认 = 页高 − 下边距 − 12 |

### style

| 键 | 默认 | 说明 |
|---|---|---|
| `paper` `ink` `accent` | `#f6f1e7` `#1c1c1c` `#b3272d` | 纸色 / 墨色 / 点缀色（红只用于报头、小标题、细线、数据框） |
| `serif` | `Georgia, 'Times New Roman', 'Songti SC', serif` | 正文与英文标题字体栈 |
| `body_pt` `body_lh` | `9.2` `1.47` | 正文字号与行距（主要旋钮） |
| `lede_pt` `h2_pt` | `10` `13` | 导语与栏目名 |
| `title_mm` `mark_w_mm` | `9.9` `8.6` | 报名字号（mm）、鹤标宽度 |
| `columns` | `2` | 默认栏数；单节可覆盖 |
| `grain` | `true` | 纸张纤维纹理 |

### 一节（section）

| 键 | 说明 |
|---|---|
| `num` `title` `byline` | 栏目编号、英文栏目名、署名 |
| `page` | 指定排在第几版 |
| `lede` | 导语（斜体，通栏） |
| `body` | 段落数组。字符串＝一段；`"## 小标题"`＝小标题；对象形式见下 |
| `columns` `ragged` | 覆盖栏数；3 栏及以上自动左对齐（见坑 3） |
| `figure` | `{src, width_mm, caption}`，`caption` 可带 `<b>` |
| `facts` | `[["字段","值"], …]` 双列资料框（配图放在导语下最合适） |
| `statline` | `{big, text}` 通栏数据条，排在整节**之后** |
| `close` | 结尾斜体句（红细线上） |

`body` 里可以放的对象：

```json
{ "subhead": "Cross head" }
{ "pullquote": "She was twenty-three." }
{ "keyfact": { "title": "Key fact", "text": "……" } }
{ "facts": [["A","1"],["B","2"]] }
{ "close": "The work is slow, but so is a crane's dance." }
```

正文允许内联 HTML（`<i>`、`&rsquo;` 等），脚本不做转义——这是有意的。

---

## 四、几条必须遵守的版式规则

**1. 图片永远只缩放、不裁剪。**
模板里 `figure img{width:100%;height:auto}`。不要改成 `object-fit:cover` 或给 figure 写死 height——那会裁图，而用户要的是"内容不能少"。

**2. 图片栏宽是主旋钮，字号是副旋钮。**
竖图（比例 <0.8）在同样栏宽下比横图高一倍。想让某节更紧凑，先收那一节的 `width_mm`，别急着降字号。

**3. 三栏以上必须左对齐。**
Chrome 在 Windows 上没有断词词典，`hyphens:auto` 不生效，窄栏两端对齐会拉出"河流"。模板对 `columns>=3` 自动加 `.ragged`。

**4. 页脚是 `position:absolute`，量测时要排除。**
脚本给页脚文字塞了一个零宽字符 `\u200b` 当哨兵，`measure()` 跳过带它的 block。否则每页下沿永远等于页脚位置，永远"装不下"。

**5. `_print.html` 必须落在输出目录。**
打印副本放临时目录会让 `img/xxx.jpg` 相对路径全断，页面上只剩图注。脚本已固定写到输出目录，用完即删。

**6. 字体只用系统里确实有的。**
`Georgia / Times New Roman / Songti SC` 这套在 Windows + macOS 都稳。想用中文标题字体（方正舒体、华文行楷、楷体）先跑
`python -c "from PIL import ImageFont;print(ImageFont.truetype(r'C:/Windows/Fonts/STXINGKA.TTF',40).getname())"`
拿准 family 名，别凭感觉写。

**7. 照片用原色，除非用户明确要黑白。**
米色纸 + 红点缀的报纸，配原色照片是"有照片的报纸"；配黑白是"老报纸"。这是两种调性，别自作主张，问一句或按用户上次的选择延续。

---

## 五、验收

永远看 **PNG**，不要只看 PDF 页数：

1. 逐版 PNG 里每一节的图是否完整（红冠到脚爪那种细节）；
2. 正文下沿有没有压到页脚线；
3. 三栏的最后一栏是否明显短于前两栏（该节内容不够，考虑加句或减栏）；
4. 图注是否只有一行就够（多行会显得啰嗦）。

量数字（比肉眼准）：

```bash
python - <<'EOF'
import pymupdf
d = pymupdf.open('my-paper.pdf'); mm = lambda v: round(v/72*25.4, 1)
for i, p in enumerate(d):
    bots = [mm(b[3]) for b in p.get_text('blocks') if '\u200b' not in b[4]]
    print(i+1, '正文下沿', max(bots), 'mm')
EOF
```

---

## 六、参考

- `examples/crane/spec.json` —— 两版、六节、五图的完整例子（课堂特刊《The Crane Chronicle》）
- `resources/base.css` —— 全部版式规则，改这里而不是改输出 HTML
- `reference/spec.md` —— 字段速查（可打印）
