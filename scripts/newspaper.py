#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
newspaper.py —— 把一份 spec.json 变成一张（或几张）报纸。

    输入：spec.json（字体 / 纸张 / 页数 / 报头 / 每节标题+正文+图片）
    输出：<name>.html、<name>.pdf、<name>-p1.png…、<name>-spread.png

只依赖：Chrome/Edge（打印 PDF）、pymupdf、Pillow。
自动试排：反复量测 PDF 的真实下沿，等比收图、必要时微调字号，直到每一版都不越界。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(os.path.dirname(HERE), 'resources')

PAPERS = {          # 单位 mm（宽, 高）
    'A3':      (297.0, 420.0),
    'A4':      (210.0, 297.0),
    'A5':      (148.0, 210.0),
    'Letter':  (215.9, 279.4),
    'Tabloid': (279.4, 431.8),
}

DEFAULTS = {
    'paper': 'A4',
    'margins_mm': {'top': 12, 'right': 13, 'bottom': 13, 'left': 13},
    'style': {
        'paper': '#f6f1e7', 'ink': '#1c1c1c', 'accent': '#b3272d',
        'serif': "Georgia, 'Times New Roman', 'Songti SC', serif",
        'sans': "'Helvetica Neue', Arial, sans-serif",
        'body_pt': 9.2, 'body_lh': 1.47, 'lede_pt': 10.0, 'h2_pt': 13.0,
        'kick_pt': 6.4, 'subtitle_pt': 9.6, 'title_mm': 9.9, 'mark_w_mm': 8.6,
        'columns': 2, 'grain': True,
    },
    'fit': {'limit_mm': None, 'min_body_pt': 8.4, 'max_iterations': 24},
    'footer': {'page': 'Page {n} of {total}', 'marks': 2},
}


# ---------------------------------------------------------------- 小工具
def die(msg):
    print('× ' + msg, file=sys.stderr)
    raise SystemExit(1)


def deep_set(base, patch):
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_set(base[k], v)
        else:
            base[k] = v
    return base


def load_spec(path):
    spec = json.load(open(path, encoding='utf-8'))
    spec = deep_set(json.loads(json.dumps(DEFAULTS)), {k: v for k, v in spec.items()})
    size = spec['paper'].get('size', 'A4') if isinstance(spec['paper'], dict) else spec['paper']
    if isinstance(spec['paper'], str):
        size = spec['paper']
    custom = spec['paper'].get('custom_mm') if isinstance(spec['paper'], dict) else None
    if custom:
        pw, ph = float(custom[0]), float(custom[1])
    elif size in PAPERS:
        pw, ph = PAPERS[size]
    else:
        die('未知纸张 %r，可用：%s 或 {size:"custom", custom_mm:[宽,高]}' % (size, ', '.join(PAPERS)))
    if isinstance(spec['paper'], dict) and spec['paper'].get('orientation') == 'landscape':
        pw, ph = ph, pw
    spec['_w'], spec['_h'] = pw, ph
    spec['_dir'] = os.path.dirname(os.path.abspath(path))
    spec['name'] = spec.get('name') or 'newspaper'
    if spec['fit']['limit_mm'] is None:
        spec['fit']['limit_mm'] = round(ph - spec['margins_mm']['bottom'] - 12.0, 1)
    return spec


def find_chrome():
    cands = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    for c in ('chrome', 'google-chrome', 'chromium', 'msedge'):
        p = shutil.which(c)
        if p:
            return p
    die('找不到 Chrome / Edge。装了再跑，或用 --chrome 指定路径。')


# ---------------------------------------------------------------- 渲染
def esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def body_html(items, extra_cls='', cols=None):
    out = []
    for it in items or []:
        if isinstance(it, str):
            if it.startswith('## '):
                out.append('<h3>%s</h3>' % it[3:])
            else:
                out.append('<p>%s</p>' % it)
        elif 'subhead' in it:
            out.append('<h3>%s</h3>' % it['subhead'])
        elif 'pullquote' in it:
            out.append('<p class="pullquote">%s</p>' % it['pullquote'])
        elif 'statline' in it:
            s = it['statline']
            out.append('<div class="statline"><b>%s</b><span>%s</span></div>' % (s['big'], s['text']))
        elif 'keyfact' in it:
            k = it['keyfact']
            out.append('<div class="keyfact"><b>%s</b><p>%s</p></div>' % (k.get('title', 'Key fact'), k['text']))
        elif 'facts' in it:
            out.append(facts_html(it['facts']))
        elif 'close' in it:
            out.append('<p class="close">%s</p>' % it['close'])
        elif 'text' in it:
            out.append('<p>%s</p>' % it['text'])
    cls = ('body ' + extra_cls).strip()
    st = ' style="column-count:%d"' % cols if cols else ''
    return '<div class="%s"%s>%s</div>' % (cls, st, ''.join(out))


def facts_html(pairs):
    cells = ''.join('<div><dt>%s</dt><dd>%s</dd></div>' % (a, b) for a, b in pairs)
    return '<dl class="facts">%s</dl>' % cells


def figure_html(fig, pw):
    src = fig['src']
    cap = fig.get('caption', '')
    return ('<figure style="width:%smm"><img src="%s" alt="">%s</figure>'
            % (round(pw, 2), src, '<figcaption>%s</figcaption>' % cap if cap else ''))


def render(spec, fig_scale=1.0, body_pt=None, page_of=None):
    st = spec['style']
    body_pt = body_pt or st['body_pt']
    css = open(os.path.join(RES, 'base.css'), encoding='utf-8').read()
    tokens = {
        'PAGE_W': spec['_w'], 'PAGE_H': spec['_h'],
        'M_TOP': spec['margins_mm']['top'], 'M_RIGHT': spec['margins_mm']['right'],
        'M_BOT': spec['margins_mm']['bottom'], 'M_LEFT': spec['margins_mm']['left'],
        'PAPER': st['paper'], 'INK': st['ink'], 'ACCENT': st['accent'],
        'SERIF': st['serif'], 'SANS': st['sans'],
        'BODY_PT': body_pt, 'BODY_LH': st['body_lh'], 'COLS': st['columns'],
        'H2_PT': st['h2_pt'], 'KICK_PT': st['kick_pt'], 'LEDE_PT': st['lede_pt'],
        'TITLE_MM': st['title_mm'], 'MARK_W': st['mark_w_mm'], 'SUB_PT': st['subtitle_pt'],
        'NARROW_PX': int(spec['_w'] * 3.7795),
    }
    for k, v in tokens.items():
        css = css.replace('{{%s}}' % k, str(v))

    secs = spec['sections']
    groups = page_of or assign_pages(secs, spec.get('pages', 1))
    total = len(groups)
    sheets = []

    mark = crane_svg(st, 'mark') if spec.get('masthead', {}).get('mark') else ''
    for pi, idxs in enumerate(groups):
        parts = []
        if pi == 0:
            m = spec.get('masthead', {})
            k = m.get('kicker', {})
            parts.append('<div class="kick"><span>%s</span><span class="mid">%s</span><span>%s</span></div>'
                         % (esc(k.get('left', '')), esc(k.get('mid', '')), esc(k.get('right', ''))))
            if mark:
                parts.append(mark)
            if m.get('thick_above', True):
                parts.append('<div class="rule-thick"></div>')
            if m.get('title'):
                t = esc(m['title'])
                if m.get('pre_title'):
                    t = '<em>%s</em>%s' % (esc(m['pre_title']), t)
                parts.append('<div class="title">%s</div>' % t)
            parts.append('<div class="rule-hair"></div>')
            if m.get('subtitle'):
                parts.append('<div class="subtitle">%s</div><div class="rule-hair"></div>' % esc(m['subtitle']))
        else:
            r = spec.get('running_head', {})
            parts.append('<div class="runhead"><span>%s</span><em>%s</em><span>%s</span></div>'
                         % (esc(r.get('left', '')), esc(r.get('mid', '')), esc(r.get('right', ''))))

        for si, idx in enumerate(idxs):
            parts.append(render_section(spec, secs[idx], si == 0, fig_scale))

        f = spec.get('footer', {})
        nmarks = int(f.get('marks', 2))
        crane = crane_svg(st, 'foot')
        pair = '<span class="pair">%s</span>' % ('%s%s' % (crane, crane.replace('class="crane"', 'class="crane b"'))) if nmarks else ''
        pg = f.get('page', 'Page {n} of {total}').replace('{n}', str(pi + 1)).replace('{total}', str(total))
        Z = '​'
        parts.append('<div class="foot"><span>%s%s</span>%s<span class="mid">%s%s</span><span>%s%s</span></div>'
                     % (Z, esc(f.get('left', '')), pair, Z, esc(f.get('mid', '')), Z, esc(pg)))

        grain = '<div class="grain"></div>' if st.get('grain') else ''
        sheets.append('<section class="sheet" id="p%d">%s\n%s\n</section>' % (pi + 1, grain, '\n'.join(parts)))

    js = """
<script>
(function(){
  var stage=document.getElementById('stage');
  function apply(){
    var vw=window.innerWidth, narrow=vw<%(narrow)d;
    if(narrow){ stage.style.display='block'; stage.style.padding='0'; stage.style.zoom='1';
                stage.style.width='100%%'; return; }
    var n=document.querySelectorAll('.sheet').length, wide=vw>=%(wide)d;
    stage.style.display='flex'; stage.style.flexWrap=wide?'nowrap':'wrap'; stage.style.padding='10mm';
    var w=wide?(n*%(pw)s+(n-1)*10):%(pw)s;
    var s=Math.min((vw-24)/(w*3.7795),1);
    stage.style.transform='none'; stage.style.zoom=s;
    stage.style.width=(w*3.7795)+'px'; stage.style.margin='0 auto';
  }
  apply(); window.addEventListener('resize',apply);
})();
</script>""" % {'narrow': int(spec['_w'] * 3.7795), 'wide': int(spec['_w'] * 3.7795 * 2.4),
                 'pw': spec['_w']}

    return """<!DOCTYPE html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<title>%(title)s</title>
<style>
%(css)s
</style>
</head>
<body>
<div class="stage" id="stage">
%(sheets)s
</div>
%(js)s
</body>
</html>
""" % {'lang': spec.get('lang', 'en'), 'title': esc(spec.get('masthead', {}).get('title', spec['name'])),
       'css': css, 'sheets': '\n'.join(sheets), 'js': js}


def render_section(spec, sec, first, fig_scale):
    st = spec['style']
    out = ['<section class="sec%s">' % (' first' if first else '')]
    head = '<h2>'
    if sec.get('num'):
        head += '<span class="num">%s</span>' % esc(str(sec['num']))
    head += '<span>%s</span>' % esc(sec.get('title', ''))
    if sec.get('byline'):
        head += '<span class="by">%s</span>' % esc(sec['byline'])
    head += '</h2>'
    out.append(head)

    cols = sec.get('columns', st['columns'])
    ragged = ' ragged' if sec.get('ragged') or cols >= 3 else ''
    inner = ''
    if sec.get('headline'):
        inner += '<div class="headline">%s</div>' % sec['headline']
    if sec.get('lede'):
        inner += '<p class="lede">%s</p>' % sec['lede']
    if sec.get('body'):
        inner += body_html(sec['body'], ragged.strip(),
                           cols if cols != st['columns'] else None)
    for key in ('pullquote', 'keyfact'):
        if key in sec:
            v = sec[key]
            if key == 'pullquote':
                inner += '<p class="pullquote">%s</p>' % v
            else:
                inner += '<div class="keyfact"><b>%s</b><p>%s</p></div>' % (v.get('title', 'Key fact'), v['text'])
    if sec.get('facts'):
        inner += facts_html(sec['facts'])
    if sec.get('close'):
        inner += '<p class="close">%s</p>' % sec['close']

    after = ''
    if sec.get('statline'):
        v = sec['statline']
        after = '<div class="statline"><b>%s</b><span>%s</span></div>' % (v['big'], v['text'])

    if sec.get('figure'):
        pw = float(sec['figure'].get('width_mm', 50)) * fig_scale
        out.append('<div class="grid" style="grid-template-columns:1fr %smm"><div>%s</div>%s</div>'
                   % (round(pw, 2), inner, figure_html(sec['figure'], pw)))
    else:
        out.append(inner)
    if after:
        out.append(after)
    out.append('</section>')
    return ''.join(out)


def assign_pages(secs, npages):
    """没写 page 就按份数均分；写了就用写的。"""
    if all('page' in s for s in secs):
        groups = [[] for _ in range(max(s['page'] for s in secs))]
        for i, s in enumerate(secs):
            groups[s['page'] - 1].append(i)
        return [g for g in groups if g]
    n = max(1, int(npages))
    groups = [[] for _ in range(n)]
    for i, s in enumerate(secs):
        groups[min(n - 1, i * n // len(secs))].append(i)
    return [g for g in groups if g]


def crane_svg(st, variant):
    ink, acc = st['ink'], st['accent']
    cls = 'crane' if variant == 'foot' else 'mark'
    return ('<svg class="%s" viewBox="0 0 200 340" aria-hidden="true">'
            '<path d="M55,58 C50,94 57,138 88,178" fill="none" stroke="%s" stroke-width="7" stroke-linecap="round"/>'
            '<circle cx="54" cy="52" r="6.6" fill="%s"/>'
            '<path d="M48,50 L12,45.5 L12,49 L48,55.5 Z" fill="%s"/>'
            '<ellipse cx="55.5" cy="45.5" rx="5.2" ry="3.6" fill="%s"/>'
            '<path d="M106,206 L102,264 L98,322" fill="none" stroke="%s" stroke-width="2.6" stroke-linecap="round"/>'
            '<path d="M120,208 L117,266 L113,324" fill="none" stroke="%s" stroke-width="2.6" stroke-linecap="round"/>'
            '<path d="M98,322 L85,328 M98,322 L97,331 M98,322 L110,328" stroke="%s" stroke-width="1.7" stroke-linecap="round"/>'
            '<path d="M113,324 L101,330 M113,324 L112,333 M113,324 L125,330" stroke="%s" stroke-width="1.7" stroke-linecap="round"/>'
            '<path d="M141,172 C165,172 184,182 192,198 L177,200 C182,206 179,212 172,215 C159,209 149,204 138,200 Z" fill="%s"/>'
            '<ellipse cx="118" cy="190" rx="40" ry="17.5" transform="rotate(-9 118 190)" fill="%s" stroke="%s" stroke-width="2.5"/>'
            '<path d="M148,180 C166,181 178,188 186,197 C174,199 164,197 154,193 Z" fill="%s"/>'
            '</svg>'
            % ((cls,) + (ink, ink, ink, acc) + (ink, ink, ink, ink, ink, st['paper'], ink, ink)))


# ---------------------------------------------------------------- 打印 / 量测
def build_pdf(html, pdf, chrome, workdir, outdir=None):
    """_print.html 必须落在输出目录里，否则 img/ 相对路径会断。"""
    stripped = re.sub(r'<script>.*?</script>', '', html, flags=re.S)
    stripped = stripped.replace('</style>', """
.stage{display:block!important;padding:0!important;gap:0!important;
       zoom:1!important;transform:none!important;width:auto!important}
.sheet{margin:0!important;box-shadow:none!important}
html,body{background:#fff!important;height:auto!important}
</style>""", 1)
    tmp = os.path.join(outdir or workdir, '_print.html')
    open(tmp, 'w', encoding='utf-8').write(stripped)
    if os.path.exists(pdf):
        os.remove(pdf)
    r = subprocess.run([chrome, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--no-pdf-header-footer', '--print-to-pdf=' + pdf,
                        'file:///' + tmp.replace('\\', '/').lstrip('/')],
                       capture_output=True, text=True, timeout=180)
    if not os.path.exists(pdf):
        die('打印失败：\n' + (r.stderr or '')[-800:])


def measure(pdf):
    import pymupdf
    d = pymupdf.open(pdf)
    res = []
    for p in d:
        mm = lambda v: v / 72.0 * 25.4
        bots = [mm(b[3]) for b in p.get_text('blocks') if '​' not in b[4]]
        for im in p.get_image_info():
            bots.append(mm(im['bbox'][3]))
        res.append(max(bots) if bots else 0.0)
    d.close()
    return res


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='spec.json → 报纸 PDF / PNG')
    ap.add_argument('spec')
    ap.add_argument('-o', '--out', default=None, help='输出目录（默认与 spec 同目录）')
    ap.add_argument('--chrome', default=None)
    ap.add_argument('--no-fit', action='store_true', help='不做自动试排')
    ap.add_argument('--dpi', type=int, default=150)
    ap.add_argument('--no-png', action='store_true')
    a = ap.parse_args()

    spec = load_spec(a.spec)
    outdir = os.path.abspath(a.out or spec['_dir'])
    os.makedirs(outdir, exist_ok=True)
    name = spec['name']
    chrome = a.chrome or find_chrome()
    limit = spec['fit']['limit_mm']

    if spec['style'].get('grain'):
        g = os.path.join(RES, 'grain.png')
        if os.path.exists(g) and not os.path.exists(os.path.join(outdir, 'grain.png')):
            shutil.copy(g, outdir)

    work = tempfile.mkdtemp(prefix='np-')
    groups = assign_pages(spec['sections'], spec.get('pages', 1))
    best = None            # (fig_scale, body_pt)

    def trial(fs, bp):
        html = render(spec, fs, bp, groups)
        build_pdf(html, os.path.join(work, 'x.pdf'), chrome, work, outdir)
        bots = measure(os.path.join(work, 'x.pdf'))
        worst = max(bots)
        ok = worst <= limit + 0.8
        print('  试排: 图×%.2f 字%.2fpt → %d 版，最高 %0.1fmm（限 %0.1f）%s'
              % (fs, bp, len(bots), worst, limit, '  ✓' if ok else ''))
        return ok

    body_pt = spec['style']['body_pt']
    for level in range(4):
        lo, hi = 0.45, 1.0
        if trial(1.0, body_pt):
            best = (1.0, body_pt)
            if spec['fit'].get('grow', True):          # 还有空白就继续放大图
                lo2, hi2 = 1.0, 1.35
                for _ in range(3):
                    mid = round((lo2 + hi2) / 2, 3)
                    if trial(mid, body_pt):
                        lo2 = mid
                        best = (mid, body_pt)
                    else:
                        hi2 = mid
            break
        for _ in range(6):
            mid = round((lo + hi) / 2, 3)
            if trial(mid, body_pt):
                lo = mid
                best = (mid, body_pt)
            else:
                hi = mid
        if best:
            break
        if body_pt <= spec['fit']['min_body_pt'] + 0.05:
            break
        body_pt = max(spec['fit']['min_body_pt'], body_pt - 0.3)
        print('  · 字号降到 %.2fpt 再试' % body_pt)

    if not best:
        print('  ! 已到最小字号和图宽仍装不下 —— 加一页，或删掉一张图')
        best = (0.45, spec['fit']['min_body_pt'])
    fig_scale, body_pt = best

    html = render(spec, fig_scale, body_pt, groups)
    html_path = os.path.join(outdir, name + '.html')
    open(html_path, 'w', encoding='utf-8').write(html)
    pdf = os.path.join(outdir, name + '.pdf')
    build_pdf(html, pdf, chrome, work, outdir)
    bots = measure(pdf)
    print('  最终：%d 版，正文下沿 %s mm（限 %.1f） 图×%.2f 字%.2fpt'
          % (len(bots), [round(b, 1) for b in bots], limit, fig_scale, body_pt))

    if not a.no_png:
        import pymupdf
        from PIL import Image
        d = pymupdf.open(pdf)
        pngs = []
        for i in range(d.page_count):
            f = os.path.join(outdir, '%s-p%d.png' % (name, i + 1))
            d[i].get_pixmap(dpi=a.dpi).save(f)
            pngs.append(f)
        d.close()
        if len(pngs) > 1:
            ims = [Image.open(p) for p in pngs]
            gap = 40
            W = sum(i.width for i in ims) + gap * (len(ims) - 1)
            H = max(i.height for i in ims)
            sheet = Image.new('RGB', (W, H), (232, 230, 222))
            x = 0
            for i in ims:
                sheet.paste(i, (x, 0))
                x += i.width + gap
            sheet.save(os.path.join(outdir, '%s-spread.png' % name))
        print('  PNG：%d 张（%ddpi）' % (len(pngs), a.dpi))

    for f in os.listdir(outdir):
        if f.startswith('_print'):
            os.remove(os.path.join(outdir, f))
    shutil.rmtree(work, ignore_errors=True)
    print('  ✓ ' + pdf)
    print('  ✓ ' + html_path)


if __name__ == '__main__':
    main()
