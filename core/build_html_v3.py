"""
build_html_v3.py
程式碼控制排版版本（訪寫黃金標準 becker.pdf）
- 無需 Pass 2 AI 排版
- Python if/else 動態適應內容數量
- 使用精緻 CSS，對齊黃金標準視覺品質
"""

import re
import sys
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def esc(text):
    """HTML 跳脫"""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')


def _badges_html(badges):
    return ''.join(f'<span class="badge badge-green">{esc(b)}</span>' for b in badges)


def _problems_html(problems):
    return ''.join(f'<li>{esc(p)}</li>' for p in problems)


def _num_rows_html(key_numbers):
    html = ''
    for n in key_numbers:
        is_red = n.get('red', False)
        red_cls = ' red' if is_red else ''
        row_cls = ' red-row' if is_red else ''
        html += f'''
        <div class="num-row{row_cls}">
          <div class="num-value{red_cls}">{esc(n.get("value",""))}</div>
          <div class="num-label">{esc(n.get("label",""))}</div>
          <div class="num-unit">{esc(n.get("unit",""))}</div>
        </div>'''
    return html


def _solution_html(s):
    quote = s.get('solution_quote', '')
    subs = s.get('solution_subs', [])
    quote_html = f'<div class="solution-quote">{esc(quote)}</div>' if quote else ''
    subs_html = ''.join(f'<li>{esc(sub)}</li>' for sub in subs)
    return quote_html, f'<ul class="solution-sub">{subs_html}</ul>' if subs_html else ''


def _themes_html(themes):
    """瀑布流分欄：依主題數決定欄數
    支援 sub_heading（子標題）和 numbered_points（編號步驟）
    """
    n = len(themes)
    if n == 0:
        return '', 0
    if n == 1:
        cols = 1
    elif n <= 4:
        cols = 2
    else:
        cols = 3

    columns = [{'html': '', 'weight': 0} for _ in range(cols)]
    for th in themes:
        sub_h = th.get('sub_heading', '') or ''
        points = th.get('points', [])
        numbered = [p for p in (th.get('numbered_points', []) or []) if p]

        sub_html = f'<div class="theme-sub-heading">{esc(sub_h)}</div>' if sub_h else ''

        pts_html = ''.join(f'<li>{esc(p)}</li>' for p in points)
        body_html = f'<ul class="card-body">{pts_html}</ul>' if pts_html else ''

        num_items = ''.join(
            f'<div class="theme-num-item"><span class="theme-num">{i+1}</span>{esc(p)}</div>'
            for i, p in enumerate(numbered)
        )
        num_html = f'<div class="theme-num-list">{num_items}</div>' if num_items else ''

        card = f'''
        <div class="card card-soft">
          <div class="theme-title">{esc(th["title"])}</div>
          {sub_html}
          {body_html}
          {num_html}
        </div>'''
        weight = len(points) + len(numbered) * 1.2 + (1 if sub_h else 0)
        lightest = min(columns, key=lambda c: c['weight'])
        lightest['html'] += card
        lightest['weight'] += weight

    cols_html = ''.join(f'<div class="masonry-col">{c["html"]}</div>' for c in columns)
    return cols_html, cols


def _action_summary_html(action_groups):
    """Action Items 摘要三欄格（程式碼自動分欄）"""
    n = len(action_groups)
    if n == 0:
        return ''
    cols_per_row = 1 if n <= 1 else (2 if n <= 2 else 3)

    rows_html = ''
    for row_start in range(0, n, cols_per_row):
        row_groups = action_groups[row_start:row_start + cols_per_row]
        row_html = ''
        for ag in row_groups:
            items_html = ''
            for idx, it in enumerate(ag.get('items', []), 1):
                clean = re.sub(r'^\[.?\]\s*', '', it)
                items_html += f'<li><span class="ai-sum-num">{idx}</span>{esc(clean)}</li>'
            gname = ag.get('group', '')
            if not gname.startswith('@'):
                gname = '@' + gname
            row_html += f'''
            <div class="ai-group">
              <div class="ai-group-title">{esc(gname)}</div>
              <ul>{items_html}</ul>
            </div>'''
        rows_html += f'<div class="ai-row" style="display:grid;grid-template-columns:repeat({len(row_groups)},1fr);border-bottom:1px solid #E8F5E9;">{row_html}</div>'

    return f'''
    <div class="ai-section">
      <div class="ai-header">
        Action Items 執行清單
        <span class="ai-badge">待辦協議</span>
      </div>
      <div class="ai-body">{rows_html}</div>
    </div>'''


def _role_cards_html(action_groups):
    """
    人員職責卡：從 action_groups 提取每位負責人
    最多顯示前 6 人（超過時分兩排）
    """
    individuals = []
    for ag in action_groups:
        gname = ag.get('group', '').lstrip('@')
        # 去除 [TBD] 並截取描述
        def clean_item_text(t):
            t = re.sub(r'^\[.?\]\s*', '', t)   # 去 [ ]
            t = re.sub(r'\s*-\s*\[TBD\]\s*$', '', t)  # 去 - [TBD]
            return t.strip()[:40]

        items = ag.get('items', [])
        desc = clean_item_text(items[0]) if items else ''

        if '&' in gname or '（共同）' in gname:
            clean = gname.replace('（共同）', '').strip()
            individuals.append({'name': clean, 'role': '協同負責', 'desc': desc})
        else:
            individuals.append({'name': gname, 'role': '', 'desc': desc})

    if not individuals:
        return ''

    # 每排 4 欄
    COLS = 4
    rows_html = ''
    for row_start in range(0, len(individuals), COLS):
        row = individuals[row_start:row_start + COLS]
        cards = ''
        for p in row:
            initial = p['name'][0] if p['name'] else '?'
            title_html = f'<div class="role-title">{esc(p["role"])}</div>' if p['role'] else ''
            cards += f'''
            <div class="role-card">
              <div class="role-avatar">{esc(initial)}</div>
              <div class="role-name">{esc(p["name"])}</div>
              {title_html}
              <div class="role-desc">{esc(p["desc"])}</div>
            </div>'''
        rows_html += f'<div class="role-row" style="grid-template-columns:repeat({len(row)},1fr);">{cards}</div>'

    return f'<div class="role-section">{rows_html}</div>'


def _sections_html(sections):
    html = ''
    for sec in sections:
        bullets_html = ''
        for level, text in sec.get('bullets', []):
            cls = f'lv{level}'
            bullets_html += f'<li class="{cls}">{esc(text)}</li>'
        paras_html = ''.join(f'<p class="detail-para">{esc(p)}</p>' for p in sec.get('paras', []))
        closing = sec.get('closing', '')
        closing_html = f'<div class="detail-closing">{esc(closing)}</div>' if closing else ''
        bullets_block = f'<ul class="detail-bullets">{bullets_html}</ul>' if bullets_html else ''
        html += f'''
        <div class="detail-heading">{esc(sec["heading"])}</div>
        {paras_html}
        {bullets_block}
        {closing_html}'''
    return html


def _action_detail_html(action_items):
    html = ''
    for person in action_items:
        items_html = ''
        for idx, it in enumerate(person.get('items', []), 1):
            clean = re.sub(r'^\[.?\]\s*', '', it)
            items_html += f'<li><span class="ai-num">{idx}</span>{esc(clean)}</li>'
        html += f'''
        <div class="ai-owner">{esc(person["owner"])}</div>
        <ol class="ai-owner-items">{items_html}</ol>'''
    return html


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;background:#f0f0f0;display:flex;justify-content:center;padding:24px;}
.page{width:794px;background:#fff;padding:32px 36px 24px;box-shadow:0 4px 24px rgba(0,0,0,.12);}
@media print{
  body{display:block;background:#fff;padding:0;}
  .page{width:100%;box-shadow:none;padding:0;}
  -webkit-print-color-adjust:exact;
  print-color-adjust:exact;
  @page{size:A4 portrait;margin:10mm 12mm;}
}

/* ── 標題區 ── */
.main-title{font-size:28px;font-weight:700;color:#1B5E20;line-height:1.25;margin-bottom:4px;}
.sub-title{font-size:15px;font-weight:500;color:#555;margin-bottom:6px;}
.objective{font-size:12px;color:#555;border-left:3px solid #66BB6A;padding-left:8px;margin-bottom:16px;line-height:1.7;}
.badge-row{display:flex;gap:6px;margin-bottom:8px;}
.badge{font-size:10px;font-weight:600;padding:3px 10px;border-radius:20px;letter-spacing:.4px;}
.badge-green{background:#C8E6C9;color:#1B5E20;}

/* ── Row 1：三欄儀表板 ── */
.row1{display:grid;gap:10px;margin-bottom:10px;align-items:stretch;}
.card{background:#fff;border:1px solid #E0E0E0;border-radius:8px;padding:13px 15px;border-top:3px solid #43A047;page-break-inside:avoid;break-inside:avoid;display:flex;flex-direction:column;}
.card-teal{border-top-color:#00897B;background:#FAFFFE;}
.card-num{border-top-color:#7CB342;background:#FAFFF5;}
.card-soft{border-top-color:#66BB6A;}
.card-title{font-size:11.5px;font-weight:700;color:#2E7D32;margin-bottom:9px;display:flex;align-items:center;gap:5px;text-transform:uppercase;letter-spacing:.3px;}
.card-title::before{content:'';width:8px;height:8px;background:#43A047;border-radius:50%;flex-shrink:0;}
.card-title-teal{color:#00695C;}
.card-title-teal::before{background:#00897B;}
.card-body{list-style:none;flex-grow:1;}
.card-body li{font-size:12.5px;color:#333;padding:4px 0 4px 15px;position:relative;line-height:1.55;border-bottom:1px solid #F5F5F5;}
.card-body li:last-child{border-bottom:none;}
.card-body li::before{content:'\203A';position:absolute;left:1px;color:#66BB6A;font-size:16px;line-height:1.2;}

/* ── 數字卡 ── */
.num-block{margin-top:2px;flex-grow:1;}
.num-row{display:flex;align-items:center;gap:10px;padding:5px 0;border-bottom:1px dashed #C5E1A5;}
.num-row:last-child{border-bottom:none;}
.num-value{font-size:26px;font-weight:700;color:#2E7D32;line-height:1;min-width:55px;letter-spacing:-.5px;}
.num-value.red{color:#B71C1C;}
.num-row.red-row{background:#FFF3F3;border-radius:5px;padding:5px 8px;margin:1px -8px;border-bottom:1px solid #FFCDD2;border-left:4px solid #B71C1C;}
.num-row.red-row .num-value{font-size:28px;}
.num-row.red-row .num-label{color:#B71C1C;font-weight:700;}
.num-label{font-size:11.5px;font-weight:600;color:#333;flex:1;line-height:1.4;}
.num-unit{font-size:10px;color:#888;white-space:nowrap;}

/* ── 解方卡 ── */
.solution-quote{font-size:15px;font-weight:700;color:#1B5E20;margin:7px 0 10px;line-height:1.5;padding:8px 12px;background:#F1F8E9;border-radius:6px;border-left:4px solid #43A047;}
.solution-sub{list-style:none;flex-grow:1;}
.solution-sub li{font-size:12.5px;color:#00695C;font-weight:500;padding:4px 0 4px 17px;position:relative;}
.solution-sub li::before{content:'\2713';position:absolute;left:0;color:#43A047;font-size:12px;}

/* ── Row 2：主題瀑布流 ── */
.row2{display:grid;gap:10px;margin-bottom:10px;align-items:start;}
.masonry-col{display:flex;flex-direction:column;gap:10px;}
.theme-title{font-size:12px;font-weight:700;color:#2E7D32;margin-bottom:6px;padding-bottom:5px;border-bottom:2px solid #C8E6C9;}
.theme-sub-heading{font-size:11.5px;font-weight:700;color:#1B5E20;margin:5px 0 6px;padding:3px 8px;background:#E8F5E9;border-radius:4px;}
.theme-num-list{margin-top:6px;}
.theme-num-item{display:flex;align-items:flex-start;gap:8px;font-size:12px;color:#333;padding:3px 0;border-bottom:1px dotted #E0E0E0;line-height:1.5;}
.theme-num-item:last-child{border-bottom:none;}
.theme-num{min-width:18px;height:18px;background:#43A047;color:#fff;border-radius:50%;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;}

/* ── 人員職責卡 ── */
.role-section{margin-bottom:10px;}
.role-row{display:grid;gap:10px;margin-bottom:8px;}
.role-card{border:1px solid #E8F5E9;border-radius:8px;padding:12px 10px;text-align:center;background:#FAFFFE;page-break-inside:avoid;break-inside:avoid;}
.role-avatar{width:36px;height:36px;border-radius:50%;background:#2E7D32;color:#fff;font-size:15px;font-weight:700;display:flex;align-items:center;justify-content:center;margin:0 auto 6px;flex-shrink:0;}
.role-name{font-size:11.5px;font-weight:700;color:#1B5E20;margin-bottom:2px;word-break:break-all;line-height:1.4;}
.role-title{font-size:10px;color:#888;margin-bottom:4px;}
.role-desc{font-size:11px;color:#444;line-height:1.5;text-align:left;word-break:break-all;}

/* ── Action Items 摘要 ── */
.ai-section{border-radius:8px;overflow:hidden;border:1px solid #C8E6C9;page-break-inside:avoid;break-inside:avoid;margin-bottom:10px;}
.ai-header{background:#1B5E20;color:#fff;font-size:12.5px;font-weight:600;padding:9px 16px;display:flex;align-items:center;gap:7px;}
.ai-badge{margin-left:auto;font-size:10px;background:rgba(255,255,255,.2);padding:2px 8px;border-radius:10px;}
.ai-body{display:block;}
.ai-group{padding:10px 14px;background:#fff;border-right:1px solid #E8F5E9;min-width:0;}
.ai-group:last-child{border-right:none;}
.ai-row:last-child .ai-group{border-bottom:none;}
.ai-group-title{font-size:11.5px;font-weight:700;color:#1B5E20;margin-bottom:7px;padding:2px 8px;background:#E8F5E9;border-radius:4px;display:inline-block;}
.ai-group ul{list-style:none;margin-top:4px;padding:0;}
.ai-group li{font-size:12px;color:#333;padding:4px 0 4px 22px;position:relative;border-bottom:1px dotted #EEE;line-height:1.5;}
.ai-group li:last-child{border-bottom:none;}
.ai-sum-num{position:absolute;left:0;color:#43A047;font-weight:700;font-size:12px;min-width:20px;}

/* ── 分隔線 ── */
.section-divider{height:1px;background:linear-gradient(90deg,#A5D6A7,#E0E0E0);margin:18px 0 14px;}

/* ── 詳細段落 ── */
.detail-heading{font-size:16px;font-weight:700;color:#1B5E20;padding:7px 0 7px 14px;margin:14px 0 8px;border-left:4px solid #43A047;border-bottom:1px solid #E8F5E9;}
.detail-para{font-size:13px;color:#333;line-height:1.85;margin-bottom:8px;text-align:justify;}
.detail-bullets{list-style:none;margin-bottom:10px;}
.detail-bullets li{font-size:13px;color:#333;line-height:1.75;padding:3px 0 3px 18px;position:relative;}
.detail-bullets li.lv1::before{content:'\2022';position:absolute;left:2px;color:#2E7D32;font-size:15px;line-height:1.3;}
.detail-bullets li.lv2{padding-left:34px;color:#444;}
.detail-bullets li.lv2::before{content:'\25E6';position:absolute;left:18px;color:#66BB6A;font-size:14px;}
.detail-closing{font-size:13px;color:#555;line-height:1.8;margin:6px 0 14px;padding:8px 12px;background:#F9FBE7;border-radius:4px;border-left:3px solid #AED581;}

/* ── Action Items 詳細 ── */
.ai-owner{font-size:13px;font-weight:700;color:#1B5E20;margin:14px 0 5px;padding:4px 0 4px 16px;border-left:3px solid #43A047;}
.ai-owner-items{list-style:none;padding-left:0;margin-bottom:4px;}
.ai-owner-items li{font-size:12.5px;color:#333;padding:4px 0 4px 28px;position:relative;line-height:1.6;border-bottom:1px dotted #EEE;}
.ai-owner-items li:last-child{border-bottom:none;}
.ai-num{position:absolute;left:6px;color:#43A047;font-weight:700;font-size:12.5px;min-width:18px;}

/* ── 頁尾 ── */
.footer{margin-top:16px;text-align:center;font-size:10px;color:#aaa;padding-top:8px;border-top:1px solid #E0E0E0;}
"""


def build_html_v3(summary, meeting, output_path, gen_time=None):
    """
    v3：程式碼控制排版，訪寫黃金標準 becker.pdf 版面
    """
    if gen_time is None:
        gen_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    s = summary
    m = meeting

    # ── 基本資料
    big_title = s.get('big_title', '會議記錄')
    sub_title = s.get('sub_title', '')
    objective = s.get('objective', '')
    badges = s.get('badges', [])
    problems = s.get('problems', [])
    problems_title = s.get('problems_title', '') or '本次會議重點議題'
    key_numbers = s.get('key_numbers', [])
    key_numbers_title = s.get('key_numbers_title', '') or '財務數字'
    solution_title = s.get('solution_title', '')
    themes = s.get('themes', [])
    action_groups = s.get('action_groups', [])
    sections = m.get('sections', [])
    action_items = m.get('action_items', [])

    has_nums = bool(key_numbers)
    has_solution = bool(solution_title or s.get('solution_quote') or s.get('solution_subs'))
    has_themes = bool(themes)
    has_roles = bool(action_groups)

    # ── Row 1：動態決定三欄或兩欄
    if has_nums and has_solution:
        row1_cols = 3
        row1_grid = '1fr 1fr 1.1fr'
    elif has_nums:
        row1_cols = 2
        row1_grid = '1fr 1fr'
    elif has_solution:
        row1_cols = 2
        row1_grid = '1fr 1.2fr'
    else:
        row1_cols = 1
        row1_grid = '1fr'

    # ── 組裝各區塊 HTML
    badges_h = _badges_html(badges)
    problems_h = _problems_html(problems)
    num_rows_h = _num_rows_html(key_numbers)
    quote_h, subs_h = _solution_html(s)

    num_card = f'''
    <div class="card card-num">
      <div class="card-title">{esc(key_numbers_title)}</div>
      <div class="num-block">{num_rows_h}</div>
    </div>''' if has_nums else ''

    sol_card = f'''
    <div class="card card-teal">
      <div class="card-title card-title-teal">{esc(solution_title)}</div>
      {quote_h}
      {subs_h}
    </div>''' if has_solution else ''

    themes_cols_h, theme_cols_n = _themes_html(themes)
    themes_section = f'<div class="row2" style="grid-template-columns:repeat({theme_cols_n},1fr);">{themes_cols_h}</div>' if has_themes else ''

    role_section = _role_cards_html(action_groups) if has_roles else ''
    action_summary = _action_summary_html(action_groups)
    sections_h = _sections_html(sections)
    action_detail = _action_detail_html(action_items)

    action_detail_section = f'''
    <div class="detail-heading">Action Items 詳細清單</div>
    <p class="detail-para" style="font-size:10.5px;color:#555;">
      以下行動項依責任人彙整，所有未具體載明期限者均以 [TBD] 標註。
    </p>
    {action_detail}''' if action_detail else ''

    # ── 組裝完整 HTML
    badge_row = f'<div class="badge-row">{badges_h}</div>' if badges else ''

    html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>{esc(big_title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">

  <div class="main-title">{esc(big_title)}</div>
  {f'<div class="sub-title">{esc(sub_title)}</div>' if sub_title and sub_title != big_title else ''}
  {badge_row}
  {f'<div class="objective">{esc(objective)}</div>' if objective else ''}

  <!-- Row 1：儀表板三欄 -->
  <div class="row1" style="grid-template-columns:{row1_grid};">
    <div class="card">
      <div class="card-title">{esc(problems_title)}</div>
      <ul class="card-body">{problems_h}</ul>
    </div>
    {num_card}
    {sol_card}
  </div>

  <!-- Row 2：主題瀑布流 -->
  {themes_section}

  <!-- Row 3：人員職責卡 -->
  {role_section}

  <!-- Action Items 摘要 -->
  {action_summary}

  <div class="section-divider"></div>

  <!-- 詳細段落 -->
  <div class="detail-section">
    {sections_h}
  </div>

  <div class="section-divider"></div>

  <!-- Action Items 詳細 -->
  {action_detail_section}

  <div class="footer">本文件由 AI 自動產生 &middot; 生成時間：{gen_time} &middot; 內容依逐字稿整理，如有出入以錄音為準</div>
</div>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'[OK] HTML v3 已產出：{output_path}')
    return output_path
