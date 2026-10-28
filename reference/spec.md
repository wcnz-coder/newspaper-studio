# spec.json 字段速查

> 一张纸上的所有开关。改版式去改 `resources/base.css`，改内容改这里。

## 顶层

```jsonc
{
  "name": "my-paper",          // 输出文件名前缀
  "lang": "en",                // html lang，影响断词
  "paper": {                   // 纸张
    "size": "A4",              // A3 A4 A5 Letter Tabloid custom
    "orientation": "portrait", // landscape 可横版
    "custom_mm": [210, 297]    // size:"custom" 时生效
  },
  "pages": 2,                  // 版数（每节写了 page 则以 page 为准）
  "style": { ... },            // 见下
  "masthead": { ... },         // 见下
  "running_head": { "left": "", "mid": "", "right": "" },
  "footer": { "left": "", "mid": "", "page": "Page {n} of {total}", "marks": 2 },
  "fit": {                     // 自动试排
    "limit_mm": 272,           // 正文下沿上限；默认 = 页高 − 下边距 − 12
    "min_body_pt": 8.4,        // 字号下限
    "grow": true,              // 有空就放大图
    "max_iterations": 24
  },
  "sections": [ ... ]
}
```

## style

| 键 | 默认 | 备注 |
|---|---|---|
| `paper` | `#f6f1e7` | 纸色（米） |
| `ink` | `#1c1c1c` | 墨色 |
| `accent` | `#b3272d` | 点缀（丹顶红） |
| `serif` | `Georgia, 'Times New Roman', 'Songti SC', serif` | 正文/英文标题 |
| `sans` | `'Helvetica Neue', Arial, sans-serif` | 备用 |
| `body_pt` | `9.2` | 正文字号 |
| `body_lh` | `1.47` | 正文行距 |
| `lede_pt` | `10` | 导语字号 |
| `h2_pt` | `13` | 栏目名字号 |
| `kick_pt` | `6.4` | 报眉字号 |
| `subtitle_pt` | `9.6` | 副标题字号 |
| `title_mm` | `9.9` | 报名字号（mm，报纸用 mm 才够大） |
| `mark_w_mm` | `8.6` | 鹤标宽度 |
| `columns` | `2` | 默认栏数 |
| `grain` | `true` | 纸张纤维 |

## masthead

```jsonc
"masthead": {
  "mark": true,                                  // 报头画鹤
  "thick_above": true,                           // 4px 粗线在报头上方
  "kicker": { "left": "...", "mid": "...", "right": "..." },
  "pre_title": "The",                            // 小字斜体前缀
  "title": "Crane Chronicle",
  "subtitle": "A Special Edition on ..."
}
```

线序固定为：报眉 → 鹤 → **粗线 + 细线** → 报名字 → 细线 → 副标题 → 细线（报纸惯例，上下双线）。

## section

| 键 | 类型 | 说明 |
|---|---|---|
| `page` | int | 排在第几版（全部写了才生效） |
| `num` | str | 栏目编号，如 `"01"` |
| `title` | str | 英文栏目名（全大写显示） |
| `byline` | str | 署名，靠右 |
| `lede` | str | 导语，斜体通栏 |
| `body` | array | 段落 / 小标题 / 拉引 / 关键事实（见下） |
| `columns` | int | 覆盖该节栏数 |
| `ragged` | bool | 强制左对齐（3 栏以上自动开） |
| `figure` | obj | `{src, width_mm, caption}` |
| `facts` | array | `[["字段","值"], …]` |
| `statline` | obj | `{big, text}`，通栏，排在整节后 |
| `close` | str | 收尾斜体句 |

### body 数组里能放什么

```jsonc
"body": [
  "普通一段。",
  "## Cross head",                                  // 小标题
  { "pullquote": "She was twenty-three." },         // 栏内拉引（红细线）
  { "keyfact": { "title": "Key fact", "text": "…" } },   // 浅红底关键事实
  { "facts": [["A","1"],["B","2"]] },               // 栏内资料框（较少用）
  { "close": "The work is slow, but so is a crane's dance." }
]
```

正文允许内联 HTML：`<i>`、`<b>`、`&rsquo;`、`&mdash;` 等不会被打码。

## 图片怎么给

- 放在 spec 同级的 `img/` 里，`src` 写相对路径；
- **保持原始比例**，脚本永远 `height:auto`，不会裁；
- `width_mm` 给个大概值即可：竖图（比例 0.5–0.8）建议 36–46mm，横图建议 56–80mm；
- 想让整页更饱满，把 `fit.grow` 留着（默认开），它会自动放大到刚好装满。

## 常见改写

**加一页** → `"pages": 3`，并给新页的节写 `"page": 3`。

**改成 A3 海报式特刊** → `"paper": {"size":"A3"}`，`title_mm` 提到 16，`body_pt` 提到 10.5。

**黑白老报纸** → `"style": {"paper":"#f3efe6","ink":"#141414","accent":"#8c1c1c"}`，图片事先自己转灰度。

**不要鹤** → `"masthead": {"mark": false}`，`"footer": {"marks": 0}`。
