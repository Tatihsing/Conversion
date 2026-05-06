"""
build_html.py
根據 SUMMARY dict 產出完整會議記錄 HTML（儀表板摘要 + 詳細內文）
由 Claude 填入 SUMMARY 和 MEETING 後執行，再用 html_to_pdf.py 轉 PDF
"""

import os
import sys
import re
import json
from datetime import datetime

# 強制 stdout 使用 UTF-8（避免 Windows cp950 編碼錯誤）
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── 載入詞彙對照表（與 build_pdf.py 共用同一份 glossary）────────────────────
def load_glossary(base_dir=None):
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    xlsx_path = os.path.join(base_dir, 'glossary.xlsx')
    json_path = os.path.join(base_dir, 'glossary.json')
    if os.path.exists(xlsx_path):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_path, data_only=True)
            ws = wb.active
            mapping = {}
            for row in ws.iter_rows(min_row=2, values_only=True):
                wrong   = str(row[1]).strip() if row[1] else ''
                correct = str(row[2]).strip() if row[2] else ''
                if (wrong and correct and wrong != 'None' and correct != 'None'
                        and wrong != '辨識錯誤詞（原始）' and wrong != '填入辨識到的錯誤詞'):
                    mapping[wrong] = correct
            return mapping
        except Exception:
            pass
    if os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
        mapping = {}
        for key, val in data.items():
            if key.startswith('_'):
                continue
            if isinstance(val, dict):
                mapping.update(val)
            elif isinstance(val, str):
                mapping[key] = val
        return mapping
    return {}

def apply_glossary(text, mapping):
    if not text or not mapping:
        return text
    for wrong, correct in mapping.items():
        text = text.replace(wrong, correct)
    return text

def fix(obj, mapping):
    if isinstance(obj, str):   return apply_glossary(obj, mapping)
    if isinstance(obj, list):  return [fix(i, mapping) for i in obj]
    if isinstance(obj, tuple): return tuple(fix(i, mapping) for i in obj)
    if isinstance(obj, dict):  return {k: fix(v, mapping) for k, v in obj.items()}
    return obj

def esc(text):
    """HTML 跳脫"""
    return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br>')

# ── 儀表板 + 詳細內文 SUMMARY / MEETING（由 Claude 填入）─────────────────────
#
# SUMMARY 欄位說明：
#   big_title    : 大標題，例如 "04-21 製造部門內部檢討與轉型會議"
#   sub_title    : 副標題（不含日期）
#   objective    : 目標一句話
#   badges       : 標籤列表，例如 ["內部轉型會議", "AI 驅動記錄"]
#   problems     : 問題摘要條列（list of str）
#   key_numbers  : 財務數字，[{"value":"6,462","label":"全成本","unit":"元/人/日","red":False}, ...]
#                  若本次會議無財務數字，設為空列表 []
#   solution_title : 核心解方標題
#   solution_quote : 核心金句（可用 \n 換行）
#   solution_subs  : 核心解方條列（list of str）
#   themes       : 三欄主題，[{"title":"...","points":["..."]}, ...]（建議 3 欄）
#   action_groups: Action Items 摘要，[{"group":"...","items":["..."]}, ...]（建議 3 群）
#
# MEETING 欄位說明（詳細內文，同 build_pdf.py）：
#   sections     : [{"heading":"...","paras":["..."],"bullets":[(1,"..."),(2,"...")],"closing":"..."}, ...]
#   action_items : [{"owner":"@...","items":["[ ] ... - [TBD]"]}, ...]

SUMMARY = {
    "big_title":  "",       # ← Claude 填入
    "sub_title":  "",
    "objective":  "",
    "badges":     [],       # 保持空列表，不填任何標籤

    "problems":       [],   # 問題摘要條列
    "problems_title": "",   # 問題卡片標題，留空則自動用「本次會議重點議題」

    "key_numbers":    [],   # 財務數字，無則留空列表 []
    "key_numbers_title": "", # 財務卡片標題，留空則自動用「財務數字」

    "solution_title": "",   # 核心解方標題，留空則整個解方卡片隱藏
    "solution_quote": "",
    "solution_subs":  [],

    "themes": [],           # 多欄主題（幾個 dict 就幾欄，不限 3 欄）

    "action_groups": [],    # Action Items 摘要（幾群就幾欄）
}

MEETING = {
    "sections":     [],     # ← Claude 填入詳細段落
    "action_items": [],
}

OUTPUT = ""   # ← Claude 填入，例如 "/path/to/2026-04-21_會議標題.html"

# ── 產生 HTML ─────────────────────────────────────────────────────────────────
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

    # ── 財務數字
    nums = s.get("key_numbers", [])
    key_numbers_title = s.get("key_numbers_title", "") or "財務數字"
    if nums:
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
        row1_cols = 3
    else:
        num_card_html = ''
        row1_cols = 2

    # ── 核心解方（solution_title 留空則整個卡片隱藏）
    sol_subs_html = ''.join(f'<li>{esc(s2)}</li>' for s2 in s.get("solution_subs", []))
    sol_quote_html = esc(s.get("solution_quote", "")).replace('&lt;br&gt;', '<br>').replace('\n', '<br>')
    if not s.get("solution_title", ""):
        row1_cols = max(row1_cols - 1, 1)

    if row1_cols == 3:
        row1_grid = "2.1fr 1.4fr 1.7fr"
    elif row1_cols == 2:
        row1_grid = "1fr 1fr"
    else:
        row1_grid = "1fr"

    # ── 三欄主題
    themes_html = ''
    for th in s.get("themes", []):
        pts = ''.join(f'<li>{esc(p)}</li>' for p in th.get("points", []))
        themes_html += f'''
        <div class="card card-soft">
          <div class="theme-title">{esc(th["title"])}</div>
          <ul class="card-body">{pts}</ul>
        </div>'''

    # ── Action Items 摘要（編號取代核取方塊）
    # 超過 4 欄時自動分兩列，每列最多 4 欄
    action_groups = s.get("action_groups", [])
    n_groups = len(action_groups)
    cols_per_row = min(n_groups, 4) if n_groups <= 4 else (4 if n_groups <= 8 else 4)

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

    # ── Action Items 詳細版（移除 [ ] 核取方塊，改用編號）
    ai_detail_html = ''
    for person in m.get("action_items", []):
        items_html = ''
        for idx, it in enumerate(person.get("items", []), 1):
            # 移除開頭的 "[ ] " 或 "[x] " 格式
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
  .badge-row{{display:flex;gap:6px;margin-bottom:8px;}}
  .badge{{font-size:10px;font-weight:600;padding:3px 10px;border-radius:20px;letter-spacing:.4px;}}
  .badge-green{{background:#C8E6C9;color:#1B5E20;}}
  .badge-teal{{background:#B2EBF2;color:#006064;}}
  .main-title{{font-size:26px;font-weight:700;color:#1B5E20;line-height:1.25;margin-bottom:5px;}}
  .sub-title{{font-size:15px;font-weight:500;color:#333;margin-bottom:6px;}}
  .objective{{font-size:12px;color:#555;border-left:3px solid #66BB6A;padding-left:8px;margin-bottom:16px;}}
  .card{{background:#fff;border:1px solid #E0E0E0;border-radius:8px;padding:13px 15px;border-top:3px solid #43A047;}}
  .card-teal{{border-top-color:#00897B;background:#FAFFFE;}}
  .card-num{{border-top-color:#7CB342;background:#FAFFF5;}}
  .card-soft{{border-top-color:#66BB6A;}}
  .card-title{{font-size:11.5px;font-weight:700;color:#2E7D32;margin-bottom:9px;display:flex;align-items:center;gap:5px;text-transform:uppercase;letter-spacing:.3px;}}
  .card-title::before{{content:'';width:8px;height:8px;background:#43A047;border-radius:50%;flex-shrink:0;}}
  .card-title-teal{{color:#00695C;}}
  .card-title-teal::before{{background:#00897B;}}
  .card-body{{list-style:none;}}
  .card-body li{{font-size:12.5px;color:#333;padding:4px 0 4px 15px;position:relative;line-height:1.55;border-bottom:1px solid #F5F5F5;}}
  .card-body li:last-child{{border-bottom:none;}}
  .card-body li::before{{content:'›';position:absolute;left:1px;color:#66BB6A;font-size:16px;line-height:1.2;}}
  .row1{{display:grid;grid-template-columns:{row1_grid};gap:10px;margin-bottom:10px;align-items:start;}}
  .num-block{{margin-top:2px;}}
  .num-row{{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px dashed #C5E1A5;}}
  .num-row:last-child{{border-bottom:none;}}
  .num-value{{font-size:26px;font-weight:700;color:#2E7D32;line-height:1;min-width:70px;letter-spacing:-.5px;}}
  .num-value.red{{color:#C62828;}}
  .num-label{{font-size:12px;font-weight:600;color:#333;}}
  .num-unit{{font-size:10px;color:#888;}}
  .solution-quote{{font-size:16px;font-weight:700;color:#1B5E20;margin:7px 0 10px;line-height:1.5;padding:8px 12px;background:#F1F8E9;border-radius:6px;border-left:4px solid #43A047;}}
  .solution-sub{{list-style:none;}}
  .solution-sub li{{font-size:12.5px;color:#00695C;font-weight:500;padding:4px 0 4px 17px;position:relative;}}
  .solution-sub li::before{{content:'✓';position:absolute;left:0;color:#43A047;font-size:12px;}}
  .row2{{display:grid;grid-template-columns:repeat({min(len(s.get("themes",[1,2,3])),3)},1fr);gap:10px;margin-bottom:10px;align-items:start;}}
  .theme-title{{font-size:12px;font-weight:700;color:#2E7D32;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #C8E6C9;}}
  .ai-section{{border-radius:8px;overflow:hidden;border:1px solid #C8E6C9;}}
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
  .detail-bullets li.lv1::before{{content:'•';position:absolute;left:2px;color:#2E7D32;font-size:15px;line-height:1.3;}}
  .detail-bullets li.lv2{{padding-left:34px;color:#444;}}
  .detail-bullets li.lv2::before{{content:'◦';position:absolute;left:18px;color:#66BB6A;font-size:14px;}}
  .detail-closing{{font-size:13px;color:#555;line-height:1.8;margin:6px 0 14px;padding:8px 12px;background:#F9FBE7;border-radius:4px;border-left:3px solid #AED581;}}
  .ai-detail{{margin-top:4px;}}
  .ai-owner{{font-size:13px;font-weight:600;color:#1B5E20;margin:10px 0 4px;}}
  .ai-owner-items{{list-style:none;padding-left:0;}}
  .ai-owner-items li{{font-size:12.5px;color:#333;padding:3px 0 3px 28px;position:relative;line-height:1.6;}}
  .ai-num{{position:absolute;left:0;color:#43A047;font-weight:700;font-size:12.5px;min-width:24px;}}
  .footer{{margin-top:16px;text-align:center;font-size:10px;color:#aaa;padding-top:8px;border-top:1px solid #E0E0E0;}}
  @media print{{
    body{{background:#fff;padding:0;}}
    .page{{box-shadow:none;padding:18px 22px;width:100%;}}
    -webkit-print-color-adjust:exact;
    print-color-adjust:exact;
    @page{{size:A4 portrait;margin:8mm 10mm;}}
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
    {'<div class="card card-teal"><div class="card-title card-title-teal">' + esc(s.get("solution_title","")) + '</div><div class="solution-quote">' + sol_quote_html + '</div><ul class="solution-sub">' + sol_subs_html + '</ul></div>' if s.get("solution_title","") else ''}
  </div>

  <div class="row2">{themes_html}</div>

  <div class="ai-section">
    <div class="ai-header">Action Items 執行清單</div>
    <div class="ai-body">{ai_groups_html}</div>
  </div>

  {detail_section}

  <div class="footer">本文件由 AI 自動產生 &nbsp;·&nbsp; 生成時間：{gen_time} &nbsp;·&nbsp; 內容依逐字稿整理，如有出入以錄音為準</div>
</div>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML 已產出：{output_path}")
    return output_path


# ── 執行 ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # 套用對照表
    _glossary = load_glossary()
    if _glossary:
        SUMMARY = fix(SUMMARY, _glossary)
        MEETING = fix(MEETING, _glossary)
        print(f"[OK] 已套用對照表，共 {len(_glossary)} 條規則")

    if not OUTPUT:
        print("[ERR] 請設定 OUTPUT 路徑")
        exit(1)

    build_html(SUMMARY, MEETING, OUTPUT)

    # 自動呼叫 html_to_pdf.py 轉 PDF
    import subprocess, sys
    pdf_path = OUTPUT.replace('.html', '.pdf')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    converter = os.path.join(script_dir, 'html_to_pdf.py')
    print("[..] 轉換 PDF 中...")
    result = subprocess.run(
        [sys.executable, converter, OUTPUT, pdf_path],
        capture_output=False
    )
    if result.returncode == 0:
        print(f"[OK] 完成！PDF：{pdf_path}")
    else:
        print("[WARN] PDF 轉換失敗，請手動用 Chrome 開啟 HTML 列印")
