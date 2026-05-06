"""
build_html_v2.py
動態積木式渲染 — AI 擔任排版設計師，從預定義的 UI 組件庫中挑選並組裝 HTML
"""

import sys
import json
import textwrap
from datetime import datetime
from .shared import gemini_call_with_retry, MODEL_TEXT

# 強制 stdout 使用 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ── CSS 積木庫（所有樣式都已針對 Chrome PDF 優化過）─────────────────────────────
CSS_LIBRARY = r"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;background:#f0f0f0;display:flex;justify-content:center;padding:24px;}
.page{width:794px;background:#fff;padding:32px 36px 24px;box-shadow:0 4px 24px rgba(0,0,0,.12);}

/* ── 列印安全設定 ── */
@media print{
  body{background:#fff;padding:10mm 12mm;display:block;}
  .page{box-shadow:none;padding:0;width:100%;}
  -webkit-print-color-adjust:exact;
  print-color-adjust:exact;
  @page{size:A4 portrait;margin:0;}
}

/* ══ 組件 A：大標題區 (必用) ══ */
.main-title{font-size:26px;font-weight:700;color:#1B5E20;line-height:1.25;margin-bottom:5px;}
.sub-title{font-size:15px;font-weight:500;color:#333;margin-bottom:6px;}
.objective{font-size:12px;color:#555;border-left:3px solid #66BB6A;padding-left:8px;margin-bottom:16px;}
.badge-row{display:flex;gap:6px;margin-bottom:8px;}
.badge{font-size:10px;font-weight:600;padding:3px 10px;border-radius:20px;letter-spacing:.4px;background:#C8E6C9;color:#1B5E20;}

/* ══ 組件 B：卡片基礎 ══ */
.card{background:#fff;border:1px solid #E0E0E0;border-radius:8px;padding:13px 15px;border-top:3px solid #43A047;page-break-inside:avoid;break-inside:avoid;display:flex;flex-direction:column;}
.card-teal{border-top-color:#00897B;background:#FAFFFE;}
.card-num{border-top-color:#7CB342;background:#FAFFF5;}
.card-soft{border-top-color:#66BB6A;}
.card-accent{border-top-color:#FF8F00;background:#FFFBF0;}
.card-title{font-size:11.5px;font-weight:700;color:#2E7D32;margin-bottom:9px;display:flex;align-items:center;gap:5px;text-transform:uppercase;letter-spacing:.3px;}
.card-title::before{content:'';width:8px;height:8px;background:#43A047;border-radius:50%;flex-shrink:0;}
.card-title-teal{color:#00695C;}
.card-title-teal::before{background:#00897B;}
.card-body{list-style:none;flex-grow:1;}
.card-body li{font-size:12.5px;color:#333;padding:4px 0 4px 15px;position:relative;line-height:1.55;border-bottom:1px solid #F5F5F5;}
.card-body li:last-child{border-bottom:none;}
.card-body li::before{content:'\203A';position:absolute;left:1px;color:#66BB6A;font-size:16px;line-height:1.2;}

/* ══ 組件 C：Grid 排版容器 ══ */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;align-items:stretch;}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px;align-items:stretch;}
.grid-2-1{display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-bottom:10px;align-items:stretch;}
.grid-1-2{display:grid;grid-template-columns:1fr 2fr;gap:10px;margin-bottom:10px;align-items:stretch;}
.grid-row{display:grid;gap:10px;margin-bottom:10px;align-items:stretch;}

/* ══ 組件 D：數據面板 ══ */
.num-block{margin-top:2px;flex-grow:1;}
.num-row{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px dashed #C5E1A5;}
.num-row:last-child{border-bottom:none;}
.num-value{font-size:26px;font-weight:700;color:#2E7D32;line-height:1;min-width:70px;letter-spacing:-.5px;}
.num-value.red{color:#C62828;}
.num-label{font-size:12px;font-weight:600;color:#333;}
.num-unit{font-size:10px;color:#888;}

/* ══ 組件 E：金句/解方區塊 ══ */
.solution-quote{font-size:16px;font-weight:700;color:#1B5E20;margin:7px 0 10px;line-height:1.5;padding:8px 12px;background:#F1F8E9;border-radius:6px;border-left:4px solid #43A047;}
.solution-sub{list-style:none;flex-grow:1;}
.solution-sub li{font-size:12.5px;color:#00695C;font-weight:500;padding:4px 0 4px 17px;position:relative;}
.solution-sub li::before{content:'\2713';position:absolute;left:0;color:#43A047;font-size:12px;}

/* ══ 組件 F：主題卡片 (Masonry) ══ */
.masonry{display:grid;gap:10px;margin-bottom:10px;align-items:start;}
.masonry-col{display:flex;flex-direction:column;gap:10px;}
.theme-title{font-size:12px;font-weight:700;color:#2E7D32;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid #C8E6C9;}

/* ══ 組件 G：時間軸 ══ */
.timeline{margin:10px 0;padding-left:18px;border-left:3px solid #43A047;}
.timeline-item{padding:8px 0 8px 12px;position:relative;border-bottom:1px solid #F0F0F0;}
.timeline-item:last-child{border-bottom:none;}
.timeline-item::before{content:'';position:absolute;left:-24px;top:12px;width:12px;height:12px;background:#43A047;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 2px #43A047;}
.timeline-label{font-size:11px;font-weight:700;color:#2E7D32;margin-bottom:2px;}
.timeline-text{font-size:12px;color:#333;line-height:1.5;}

/* ══ 組件 H：人員職責卡 ══ */
.role-grid{display:grid;gap:10px;margin-bottom:10px;}
.role-card{background:#fff;border:1px solid #E0E0E0;border-radius:8px;padding:12px 14px;text-align:center;page-break-inside:avoid;break-inside:avoid;}
.role-icon{font-size:20px;margin-bottom:4px;}
.role-name{font-size:13px;font-weight:700;color:#1B5E20;margin-bottom:2px;}
.role-title{font-size:10.5px;color:#888;margin-bottom:6px;}
.role-desc{font-size:11.5px;color:#333;line-height:1.5;text-align:left;}

/* ══ 組件 I：Action Items 執行清單 ══ */
.ai-section{border-radius:8px;overflow:hidden;border:1px solid #C8E6C9;page-break-inside:avoid;break-inside:avoid;margin-bottom:10px;}
.ai-header{background:#1B5E20;color:#fff;font-size:12.5px;font-weight:600;padding:9px 16px;display:flex;align-items:center;gap:7px;}
.ai-header::before{content:'\\2756';font-size:10px;opacity:.7;}
.ai-body{display:block;}
.ai-group{padding:10px 14px;background:#fff;border-right:1px solid #E8F5E9;min-width:0;}
.ai-group:last-child{border-right:none;}
.ai-row{display:grid;border-bottom:1px solid #E8F5E9;}
.ai-row:last-child{border-bottom:none;}
.ai-group-title{font-size:11.5px;font-weight:700;color:#1B5E20;margin-bottom:7px;padding:2px 8px;background:#E8F5E9;border-radius:4px;display:inline-block;}
.ai-group ul{list-style:none;margin-top:4px;padding:0;}
.ai-group li{font-size:12px;color:#333;padding:4px 0 4px 22px;position:relative;border-bottom:1px dotted #EEE;line-height:1.5;}
.ai-group li:last-child{border-bottom:none;}
.ai-sum-num{position:absolute;left:0;color:#43A047;font-weight:700;font-size:12px;min-width:20px;}

/* ══ 組件 J：分隔線 ══ */
.section-divider{height:1px;background:linear-gradient(90deg,#A5D6A7,#E0E0E0);margin:18px 0 14px;}

/* ══ 組件 K：詳細段落 (Detail Section) ══ */
.detail-section{margin-top:4px;}
.detail-heading{font-size:15px;font-weight:700;color:#1B5E20;padding:7px 0 7px 14px;margin-bottom:8px;border-left:4px solid #43A047;border-bottom:1px solid #E8F5E9;}
.detail-para{font-size:13px;color:#333;line-height:1.85;margin-bottom:8px;text-align:justify;}
.detail-bullets{list-style:none;margin-bottom:10px;}
.detail-bullets li{font-size:13px;color:#333;line-height:1.75;padding:3px 0 3px 18px;position:relative;}
.detail-bullets li.lv1::before{content:'\2022';position:absolute;left:2px;color:#2E7D32;font-size:15px;line-height:1.3;}
.detail-bullets li.lv2{padding-left:34px;color:#444;}
.detail-bullets li.lv2::before{content:'\25E6';position:absolute;left:18px;color:#66BB6A;font-size:14px;}
.detail-closing{font-size:13px;color:#555;line-height:1.8;margin:6px 0 14px;padding:8px 12px;background:#F9FBE7;border-radius:4px;border-left:3px solid #AED581;}

/* ══ 組件 L：Action Items 詳細版 ══ */
.ai-detail{margin-top:4px;}
.ai-owner{font-size:13px;font-weight:600;color:#1B5E20;margin:10px 0 4px;}
.ai-owner-items{list-style:none;padding-left:0;}
.ai-owner-items li{font-size:12.5px;color:#333;padding:3px 0 3px 28px;position:relative;line-height:1.6;}
.ai-num{position:absolute;left:0;color:#43A047;font-weight:700;font-size:12.5px;min-width:24px;}

/* ══ 組件 M：比較表格 ══ */
.compare-table{width:100%;border-collapse:collapse;margin:10px 0;font-size:12px;}
.compare-table th{background:#E8F5E9;color:#1B5E20;font-weight:600;padding:8px 12px;text-align:left;border-bottom:2px solid #43A047;}
.compare-table td{padding:7px 12px;border-bottom:1px solid #F0F0F0;color:#333;line-height:1.5;}
.compare-table tr:nth-child(even){background:#FAFFF5;}

/* ══ 組件 N：重點提示框 ══ */
.callout{padding:10px 14px;border-radius:6px;margin:8px 0;font-size:12.5px;line-height:1.6;page-break-inside:avoid;break-inside:avoid;}
.callout-green{background:#E8F5E9;border-left:4px solid #43A047;color:#1B5E20;}
.callout-amber{background:#FFF8E1;border-left:4px solid #FF8F00;color:#E65100;}
.callout-blue{background:#E3F2FD;border-left:4px solid #1565C0;color:#0D47A1;}

/* ══ 頁尾 ══ */
.footer{margin-top:16px;text-align:center;font-size:10px;color:#aaa;padding-top:8px;border-top:1px solid #E0E0E0;}
"""


# ── AI 排版師 Prompt ──────────────────────────────────────────────────────────
LAYOUT_PROMPT = textwrap.dedent("""\
你是一位世界頂尖的會議記錄排版設計師。你的任務是：根據以下會議資料（JSON），
產出一份完整的 HTML `<body>` 內容（不含 <html>, <head>, <style> 標籤，只產出 <body> 裡面的內容）。

你手上有以下預定義的 CSS 組件可以使用，請直接使用這些 class name，不要自己發明新的 CSS：

══════════════════════════════════════
可用組件列表
══════════════════════════════════════

【A. 標題區（必用）】
- .main-title → 大標題（如 "04-21 製造部門內部檢討與轉型會議"）
- .sub-title → 副標題
- .objective → 目標描述（帶綠色左邊線）
- .badge-row + .badge → 標籤列

【B. 卡片】
- .card → 基本卡片（綠色頂線）
- .card-teal → 藍綠色調卡片（適合解方/結論）
- .card-num → 數據卡片（黃綠色調）
- .card-soft → 柔綠卡片（適合主題重點）
- .card-accent → 橘色卡片（適合警示/重點強調）
- .card-title → 卡片標題（帶圓點前綴）
- .card-title-teal → 藍綠色卡片標題
- .card-body → 卡片內容列表，li 自帶 › 符號

【C. Grid 排版】
- .grid-2 → 兩欄等寬
- .grid-3 → 三欄等寬
- .grid-2-1 → 左寬右窄（2:1）
- .grid-1-2 → 左窄右寬（1:2）
- .grid-row → 彈性 grid（需手動加 style="grid-template-columns:..."）

【D. 數據面板】
- .num-block → 數據區塊容器
- .num-row → 每一行數據
- .num-value → 大數字（.red 可標紅）
- .num-label → 數據說明
- .num-unit → 數據單位

【E. 金句/解方】
- .solution-quote → 大字金句框（綠底左線）
- .solution-sub → 支撐點列表，li 自帶 ✓ 符號

【F. 主題卡片瀑布流】
- .masonry → 容器（需手動設 grid-template-columns）
- .masonry-col → 每一欄
- .theme-title → 主題標題（帶綠底線）

【G. 時間軸（適合有時間節點/流程的會議）】
- .timeline → 容器（帶左側綠線）
- .timeline-item → 每一個節點
- .timeline-label → 節點標題
- .timeline-text → 節點說明

【H. 人員職責卡（適合有明確分工的會議）】
- .role-grid → 容器（需手動設 grid-template-columns）
- .role-card → 每人一張卡
- .role-icon → 表情符號圖示
- .role-name → 姓名
- .role-title → 職稱/代號
- .role-desc → 職責說明

【I. Action Items 執行清單（摘要版）】
- .ai-section → 整體容器（帶深綠標題列）
- .ai-header → 標題列
- .ai-body → 內容區
- .ai-row → 每一橫排（需手動設 grid-template-columns）
- .ai-group → 每人一組
- .ai-group-title → 負責人標籤
- .ai-sum-num → 編號（絕對定位）

【J. 分隔線】
- .section-divider → 漸變分隔線（用於摘要區與詳細區之間）

【K. 詳細段落】
- .detail-section → 詳細區容器
- .detail-heading → 段落標題（帶綠左線）
- .detail-para → 正文段落
- .detail-bullets → 條列清單
- li.lv1 → 主項（● 符號）
- li.lv2 → 子項（◦ 符號）
- .detail-closing → 段落結語（淡黃底色）

【L. Action Items 詳細清單】
- .ai-detail → 容器
- .ai-owner → 負責人標題
- .ai-owner-items → 項目列表
- .ai-num → 編號

【M. 比較表格（適合有對比數據的會議）】
- .compare-table → 表格
- th → 綠底表頭
- td → 資料格

【N. 重點提示框】
- .callout-green → 綠色提示（結論/共識）
- .callout-amber → 橘色提示（警示/風險）
- .callout-blue → 藍色提示（資訊/背景）

══════════════════════════════════════
排版規則（務必遵守）
══════════════════════════════════════

1. 整體結構必須包裝在 <div class="page"> 內
2. 文件分為上下兩大區塊：
   - 上半部：摘要儀表板（卡片化排版，像專業的報告首頁）
   - <div class="section-divider"></div> 分隔
   - 下半部：詳細會議紀要（使用 detail-heading / detail-para / detail-bullets）
3. 上半部「摘要儀表板」：
   - 必須以 .main-title、.sub-title、.objective 開場
   - 根據會議內容性質，選擇最適合的組件組合來呈現重點
   - 如果有財務數據 → 必須使用數據面板 (D)
   - 如果有明確結論/金句 → 必須使用金句區塊 (E)
   - 如果有明確分工 → 考慮使用人員職責卡 (H)
   - 如果有時間節點/里程碑 → 考慮使用時間軸 (G)
   - 主題重點 → 使用主題卡片瀑布流 (F)
   - Action Items 摘要 → 使用執行清單 (I)
4. 下半部「詳細會議紀要」：
   - 以 meeting.sections 為基礎，每段用 detail-heading + detail-para + detail-bullets
   - 最後一段放 Action Items 詳細清單 (L)
5. 最後加上 footer：<div class="footer">本文件由 AI 自動產生 · 生成時間：{gen_time} · 內容依逐字稿整理，如有出入以錄音為準</div>
6. 所有文字必須使用繁體中文
7. 所有特殊字元必須做 HTML 跳脫（& → &amp; 等）
8. 只輸出 HTML 標記，不要加說明文字、不要用 markdown code block
9. 確保 page-break-inside:avoid 的組件不會被拆開

═══════════════════════════════════════
會議資料 JSON
═══════════════════════════════════════
""")


def build_html_v2(summary, meeting, output_path, gen_time=None):
    """Pass 2：讓 AI 根據會議內容挑選組件，組裝最適合的 HTML"""
    if gen_time is None:
        gen_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 組合資料
    data_json = json.dumps(
        {"summary": summary, "meeting": meeting},
        ensure_ascii=False, indent=2
    )

    prompt = LAYOUT_PROMPT.replace("{gen_time}", gen_time) + data_json

    print("[AI] Pass 2：AI 排版設計師組裝中...")
    resp = gemini_call_with_retry(MODEL_TEXT, prompt)
    body_html = resp.text.strip()

    # 清理 AI 可能加的 markdown code block 標記
    if body_html.startswith("```"):
        # 移除開頭的 ```html 或 ```
        lines = body_html.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body_html = "\n".join(lines)

    # 組裝完整 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>{summary.get("big_title", "會議記錄")}</title>
<style>
{CSS_LIBRARY}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML v2 已產出：{output_path}")
    return output_path
