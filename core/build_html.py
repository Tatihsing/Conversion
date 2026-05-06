"""
build_html.py
根據 SUMMARY + MEETING dict 產出完整會議記錄 HTML（儀表板摘要 + 詳細內文）
"""

import os
import sys
import re
import json
from datetime import datetime
from .shared import load_glossary, apply_glossary, fix_deep

# 強制 stdout 使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def esc(text):
    """HTML 跳脫"""
    return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br>')


def build_html(summary, meeting, output_path, gen_time=None):
    if gen_time is None:
        gen_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    s = summary
    m = meeting

    # ── 標題區
    badges_html = ''.join(
        f'<span class="badge badge-green">{esc(b)}</span>' for b in s.get("badges", [])
    )

    # ── 問題摘要
    problems_html = ''.join(f'<li>{esc(p)}</li>' for p in s.get("problems", []))
    problems_title = s.get("problems_title", "") or "本次會議重點議題"

    # ── 智慧型版面配置：根據實際內容動態計算 ──
    
    # 財務數字卡
    nums = s.get("key_numbers", [])
    key_numbers_title = s.get("key_numbers_title", "") or "財務數字"
    has_nums = bool(nums)
    if has_nums:
        num_rows_html = ''
        for n in nums:
            red_cls = ' red' if n.get("red") else ''
            num_rows_html += f'''
            <div class="num-row">
              <div class="num-value{red_cls}">{esc(n["value"])}</div>
              <div><div class="num-label">{esc(n["label"])}</div>
                   <div class="num-unit">{esc(n["unit"])}</div></div>
            </div>'''
        num_card_html = f'''
        <div class="card card-num">
          <div class="card-title">{esc(key_numbers_title)}</div>
          <div class="num-block">{num_rows_html}</div>
        </div>'''
    else:
        num_card_html = ''

    # 核心解方卡
    sol_subs_html = ''.join(f'<li>{esc(s2)}</li>' for s2 in s.get("solution_subs", []))
    sol_quote_html = esc(s.get("solution_quote", "")).replace('&lt;br&gt;', '<br>').replace('\\n', '<br>')
    has_solution = bool(s.get("solution_title", ""))

    # 動態計算第一行有幾張卡：問題卡永遠存在 + 數字卡(可選) + 解方卡(可選)
    row1_cols = 1 + (1 if has_nums else 0) + (1 if has_solution else 0)
    
    # 根據卡片數量智慧分配欄寬
    if row1_cols == 3:
        row1_grid = "2.1fr 1.4fr 1.7fr"
    elif row1_cols == 2:
        if has_nums:
            row1_grid = "1.5fr 1fr"  # 問題卡 + 數字卡
        else:
            row1_grid = "1.2fr 1fr"  # 問題卡 + 解方卡
    else:
        row1_grid = "1fr"

    # ── 智慧主題卡片排版 (自適應 Masonry Layout)
    themes_data = s.get("themes", [])
    n_themes = len(themes_data)
    if n_themes > 0:
        # 智慧決定欄數：1~2個主題用2欄，3+用3欄
        if n_themes <= 2:
            num_cols = 2
        elif n_themes <= 6:
            num_cols = 3
        else:
            num_cols = 3  # 超過6個仍用3欄 masonry 堆疊
        
        columns = [{"weight": 0, "html": ""} for _ in range(num_cols)]
        
        def get_weight(th):
            w = len(th.get("title", "")) * 2
            w += sum(len(p) for p in th.get("points", []))
            return w
            
        themes_sorted = sorted(themes_data, key=get_weight, reverse=True)
        
        for th in themes_sorted:
            pts = ''.join(f'<li>{esc(p)}</li>' for p in th.get("points", []))
            card_html = f'''
            <div class="card card-soft">
              <div class="theme-title">{esc(th["title"])}</div>
              <ul class="card-body">{pts}</ul>
            </div>'''
            lightest_col = min(columns, key=lambda c: c["weight"])
            lightest_col["html"] += card_html
            lightest_col["weight"] += get_weight(th)
            
        themes_html = ''.join(f'<div class="masonry-col">{col["html"]}</div>' for col in columns)
    else:
        themes_html = ''
        num_cols = 3  # fallback

    # ── Action Items 摘要 (智慧網格)
    action_groups = s.get("action_groups", [])
    n_groups = len(action_groups)
    
    # 智慧決定每排幾欄：少量用少欄避免太擠，多量用3欄
    if n_groups <= 2:
        cols_per_row = max(1, n_groups)
    elif n_groups <= 6:
        cols_per_row = 3
    else:
        cols_per_row = 3  # 超過6組仍用3欄分批排列

    ai_groups_html = ''
    for row_start in range(0, n_groups, cols_per_row):
        row_groups = action_groups[row_start:row_start + cols_per_row]
        row_html = ''
        for ag in row_groups:
            items = ''
            for idx, it in enumerate(ag.get("items", []), 1):
                clean_it = re.sub(r'^\[.?\]\s*', '', it)
                items += f'<li><span class="ai-sum-num">{idx}.</span>{esc(clean_it)}</li>'
            row_html += f'''
            <div class="ai-group">
              <div class="ai-group-title">@{esc(ag["group"])}</div>
              <ul>{items}</ul>
            </div>'''
        ai_groups_html += f'<div class="ai-row" style="display:grid;grid-template-columns:repeat({len(row_groups)},1fr);border-bottom:1px solid #E8F5E9;">{row_html}</div>'

    # ── 詳細段落
    sections_html = ''
    for i, sec in enumerate(m.get("sections", []), 1):
        bullets_html = ''
        for level, text in sec.get("bullets", []):
            cls = f'lv{level}'
            bullets_html += f'<li class="{cls}">{esc(text)}</li>'
        paras_html = ''.join(f'<p class="detail-para">{esc(p)}</p>' for p in sec.get("paras", []))
        closing = sec.get("closing", "")
        closing_html = f'<div class="detail-closing">{esc(closing)}</div>' if closing else ''
        bullets_block = f'<ul class="detail-bullets">{bullets_html}</ul>' if bullets_html else ''
        sections_html += f'''
        <div class="detail-heading">{esc(sec["heading"])}</div>
        {paras_html}
        {bullets_block}
        {closing_html}'''

    # ── Action Items 詳細版
    ai_detail_html = ''
    for person in m.get("action_items", []):
        items_html = ''
        for idx, it in enumerate(person.get("items", []), 1):
            clean_it = re.sub(r'^\[.?\]\s*', '', it)
            items_html += f'<li><span class="ai-num">{idx}.</span> {esc(clean_it)}</li>'
        ai_detail_html += f'''
        <div class="ai-owner">• {esc(person["owner"])}</div>
        <ol class="ai-owner-items">{items_html}</ol>'''

    ai_detail_section = ''
    if ai_detail_html:
        ai_detail_section = f'''
        <div class="detail-heading">Action Items 詳細清單</div>
        <p class="detail-para" style="font-size:10.5px;color:#555;">
          以下行動項依責任人彙整，所有未具體載明期限者均以 [TBD] 標註。
        </p>
        <div class="ai-detail">{ai_detail_html}</div>'''

    detail_section = ''
    if sections_html or ai_detail_section:
        detail_section = f'''
        <div class="section-divider"></div>
        <div class="detail-section">
          {sections_html}
          {ai_detail_section}
        </div>'''

    # 用實際計算的 num_cols 來設定 CSS grid
    theme_grid_cols = num_cols

    html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>{esc(s.get("big_title","會議記錄"))}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap');
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;background:#f0f0f0;display:flex;justify-content:center;padding:24px;}}
  .page{{width:794px;background:#fff;padding:32px 36px 24px;box-shadow:0 4px 24px rgba(0,0,0,.12);}}
  @media print {{
    body {{ display: block; background: #fff; padding: 0; }}
    .page {{ width: 100%; box-shadow: none; padding: 0; }}
  }}
  .badge-row{{display:flex;gap:6px;margin-bottom:8px;}}
  .badge{{font-size:10px;font-weight:600;padding:3px 10px;border-radius:20px;letter-spacing:.4px;}}
  .badge-green{{background:#C8E6C9;color:#1B5E20;}}
  .badge-teal{{background:#B2EBF2;color:#006064;}}
  .main-title{{font-size:26px;font-weight:700;color:#1B5E20;line-height:1.25;margin-bottom:5px;}}
  .sub-title{{font-size:15px;font-weight:500;color:#333;margin-bottom:6px;}}
  .objective{{font-size:12px;color:#555;border-left:3px solid #66BB6A;padding-left:8px;margin-bottom:16px;}}
  .card{{background:#fff;border:1px solid #E0E0E0;border-radius:8px;padding:13px 15px;border-top:3px solid #43A047;page-break-inside:avoid;break-inside:avoid;display:flex;flex-direction:column;}}
  .card-teal{{border-top-color:#00897B;background:#FAFFFE;}}
  .card-num{{border-top-color:#7CB342;background:#FAFFF5;}}
  .card-soft{{border-top-color:#66BB6A;}}
  .card-title{{font-size:11.5px;font-weight:700;color:#2E7D32;margin-bottom:9px;display:flex;align-items:center;gap:5px;text-transform:uppercase;letter-spacing:.3px;}}
  .card-title::before{{content:'';width:8px;height:8px;background:#43A047;border-radius:50%;flex-shrink:0;}}
  .card-title-teal{{color:#00695C;}}
  .card-title-teal::before{{background:#00897B;}}
  .card-body{{list-style:none;flex-grow:1;}}
  .card-body li{{font-size:12.5px;color:#333;padding:4px 0 4px 15px;position:relative;line-height:1.55;border-bottom:1px solid #F5F5F5;}}
  .card-body li:last-child{{border-bottom:none;}}
  .card-body li::before{{content:'\u203A';position:absolute;left:1px;color:#66BB6A;font-size:16px;line-height:1.2;}}
  .row1{{display:grid;grid-template-columns:{row1_grid};gap:10px;margin-bottom:10px;align-items:stretch;}}
  .num-block{{margin-top:2px;flex-grow:1;}}
  .num-row{{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px dashed #C5E1A5;}}
  .num-row:last-child{{border-bottom:none;}}
  .num-value{{font-size:26px;font-weight:700;color:#2E7D32;line-height:1;min-width:70px;letter-spacing:-.5px;}}
  .num-value.red{{color:#C62828;}}
  .num-label{{font-size:12px;font-weight:600;color:#333;}}
  .num-unit{{font-size:10px;color:#888;}}
  .solution-quote{{font-size:16px;font-weight:700;color:#1B5E20;margin:7px 0 10px;line-height:1.5;padding:8px 12px;background:#F1F8E9;border-radius:6px;border-left:4px solid #43A047;}}
  .solution-sub{{list-style:none;flex-grow:1;}}
  .solution-sub li{{font-size:12.5px;color:#00695C;font-weight:500;padding:4px 0 4px 17px;position:relative;}}
  .solution-sub li::before{{content:'\u2713';position:absolute;left:0;color:#43A047;font-size:12px;}}
  .row2{{display:grid;grid-template-columns:repeat({theme_grid_cols},1fr);gap:10px;margin-bottom:10px;align-items:start;}}
  .masonry-col{{display:flex;flex-direction:column;gap:10px;}}
  .theme-title{{font-size:12px;font-weight:700;color:#2E7D32;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #C8E6C9;}}
  .ai-section{{border-radius:8px;overflow:hidden;border:1px solid #C8E6C9;page-break-inside:avoid;break-inside:avoid;}}
  .ai-header{{background:#1B5E20;color:#fff;font-size:12.5px;font-weight:600;padding:9px 16px;display:flex;align-items:center;gap:7px;}}
  .ai-header::before{{content:'\\2756';font-size:10px;opacity:.7;}}
  .ai-body{{display:block;}}
  .ai-group{{padding:10px 14px;background:#fff;border-right:1px solid #E8F5E9;min-width:0;}}
  .ai-group:last-child{{border-right:none;}}
  .ai-row:last-child .ai-group{{border-bottom:none;}}
  .ai-group-title{{font-size:11.5px;font-weight:700;color:#1B5E20;margin-bottom:7px;padding:2px 8px;background:#E8F5E9;border-radius:4px;display:inline-block;}}
  .ai-group ul{{list-style:none;margin-top:4px;padding:0;}}
  .ai-group li{{font-size:12px;color:#333;padding:4px 0 4px 22px;position:relative;border-bottom:1px dotted #EEE;line-height:1.5;}}
  .ai-group li:last-child{{border-bottom:none;}}
  .ai-sum-num{{position:absolute;left:0;color:#43A047;font-weight:700;font-size:12px;min-width:20px;}}
  .section-divider{{height:1px;background:linear-gradient(90deg,#A5D6A7,#E0E0E0);margin:18px 0 14px;}}
  .detail-section{{margin-top:4px;}}
  .detail-heading{{font-size:15px;font-weight:700;color:#1B5E20;padding:7px 0 7px 14px;margin-bottom:8px;border-left:4px solid #43A047;border-bottom:1px solid #E8F5E9;}}
  .detail-para{{font-size:13px;color:#333;line-height:1.85;margin-bottom:8px;text-align:justify;}}
  .detail-bullets{{list-style:none;margin-bottom:10px;}}
  .detail-bullets li{{font-size:13px;color:#333;line-height:1.75;padding:3px 0 3px 18px;position:relative;}}
  .detail-bullets li.lv1::before{{content:'\u2022';position:absolute;left:2px;color:#2E7D32;font-size:15px;line-height:1.3;}}
  .detail-bullets li.lv2{{padding-left:34px;color:#444;}}
  .detail-bullets li.lv2::before{{content:'\u25E6';position:absolute;left:18px;color:#66BB6A;font-size:14px;}}
  .detail-closing{{font-size:13px;color:#555;line-height:1.8;margin:6px 0 14px;padding:8px 12px;background:#F9FBE7;border-radius:4px;border-left:3px solid #AED581;}}
  .ai-detail{{margin-top:4px;}}
  .ai-owner{{font-size:13px;font-weight:600;color:#1B5E20;margin:10px 0 4px;}}
  .ai-owner-items{{list-style:none;padding-left:0;}}
  .ai-owner-items li{{font-size:12.5px;color:#333;padding:3px 0 3px 28px;position:relative;line-height:1.6;}}
  .ai-num{{position:absolute;left:0;color:#43A047;font-weight:700;font-size:12.5px;min-width:24px;}}
  .footer{{margin-top:16px;text-align:center;font-size:10px;color:#aaa;padding-top:8px;border-top:1px solid #E0E0E0;}}
  @media print{{
    body{{background:#fff;padding:10mm 12mm;}}
    .page{{box-shadow:none;padding:0;width:100%;}}
    -webkit-print-color-adjust:exact;
    print-color-adjust:exact;
    @page{{size:A4 portrait;margin:0;}}
  }}
</style>
</head>
<body>
<div class="page">
  <div class="main-title">{esc(s.get("big_title",""))}</div>
  <div class="sub-title">{esc(s.get("sub_title",""))}</div>
  <div class="objective">{esc(s.get("objective",""))}</div>

  <div class="row1">
    <div class="card">
      <div class="card-title">{esc(problems_title)}</div>
      <ul class="card-body">{problems_html}</ul>
    </div>
    {num_card_html}
    {'<div class="card card-teal"><div class="card-title card-title-teal">' + esc(s.get("solution_title","")) + '</div><div class="solution-quote">' + sol_quote_html + '</div><ul class="solution-sub">' + sol_subs_html + '</ul></div>' if has_solution else ''}
  </div>

  {'<div class="row2">' + themes_html + '</div>' if themes_html else ''}

  {'<div class="ai-section"><div class="ai-header">Action Items 執行清單</div><div class="ai-body">' + ai_groups_html + '</div></div>' if ai_groups_html else ''}

  {detail_section}

  <div class="footer">\u672c\u6587\u4ef6\u7531 AI \u81ea\u52d5\u7522\u751f &nbsp;\u00b7&nbsp; \u751f\u6210\u6642\u9593\uff1a{gen_time} &nbsp;\u00b7&nbsp; \u5167\u5bb9\u4f9d\u9010\u5b57\u7a3f\u6574\u7406\uff0c\u5982\u6709\u51fa\u5165\u4ee5\u9304\u97f3\u70ba\u6e96</div>
</div>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML 已產出：{output_path}")
    return output_path
