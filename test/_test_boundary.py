"""
邊界測試：直接用模擬資料測試 build_html_v3 渲染器
涵蓋：空列表、極端主題數量、超長文字、無財務數字等邊界情境
"""
import sys, os
sys.path.insert(0, r"D:\錄音檔\meeting-auto")
os.chdir(r"D:\錄音檔\meeting-auto")

from core.build_html_v3 import build_html_v3
from core.html_to_pdf import html_to_pdf
from pathlib import Path

out_dir = Path(r"D:\錄音檔\meeting-auto\test\boundary")
out_dir.mkdir(exist_ok=True)

# ── 基礎模板（action_groups.items 為字串，與 AI 實際輸出一致）──
def base_summary(**kwargs):
    d = {
        "big_title": "05-06 邊界測試會議",
        "sub_title": "邊界測試",
        "objective": "測試各種邊界情境下的排版穩定性",
        "key_numbers": [
            {"value": "6,000", "label": "每日業務報價", "unit": "元", "red": False},
            {"value": "-600",  "label": "每日虧損",     "unit": "元", "red": True},
        ],
        "themes": [
            {"title": "主題一：品質管理", "sub_heading": "核心問題",  "points": ["問題一", "問題二"], "numbered_points": []},
            {"title": "主題二：進度控制", "sub_heading": "",           "points": ["要點A", "要點B", "要點C"], "numbered_points": []},
        ],
        "solution_quote": "「品質是公司立足的根本。」",
        "solutions": ["落實品管制度", "強化跨部門協作", "導入科技工具"],
        "action_groups": [
            {
                "group": "製造部門",
                "role": "廠長",
                "summary": "負責品質管控",
                "items": [
                    "[ ] 廠長：每日審視生產品質，確保符合標準 - [TBD]",
                    "[ ] 勝哥：確認出貨流程與時程 - [TBD]",
                ],
            },
            {
                "group": "資訊部門",
                "role": "靖寰",
                "summary": "負責系統維護",
                "items": [
                    "[ ] 靖寰：優化日誌分析系統 - [TBD]",
                ],
            },
        ],
        "status": "待辦議",
        "badges": [],
    }
    d.update(kwargs)
    return d

def base_meeting(**kwargs):
    d = {
        "title": "邊界測試會議記錄",
        "date": "2026-05-06",
        "attendees": ["廠長", "勝哥", "靖寰"],
        "action_items": {
            "廠長": ["[ ] 任務一 - [TBD]"],
            "靖寰": ["[ ] 任務二 - [TBD]"],
        },
        "sections": [
            {
                "heading": "一、測試段落",
                "paras": ["這是一段測試內文，確認渲染正常。包含足夠的文字來驗證排版。"],
                "bullets": [(1, "重點一"), (2, "子項一"), (1, "重點二")],
                "closing": "結論：測試完成。",
            },
            {
                "heading": "二、第二段落",
                "paras": ["第二段內文，驗證多段落渲染。"],
                "bullets": [(1, "唯一重點")],
                "closing": "段落結論。",
            },
        ],
    }
    d.update(kwargs)
    return d

results = []

def run_case(name, summary, meeting):
    html = out_dir / f"{name}.html"
    pdf  = out_dir / f"{name}.pdf"
    try:
        build_html_v3(summary, meeting, str(html))
        html_to_pdf(str(html), str(pdf))
        size = pdf.stat().st_size // 1024 if pdf.exists() else 0
        results.append(f"  ✅ {name:45s} → {size} KB")
    except Exception as e:
        results.append(f"  ❌ {name:45s} → 錯誤: {e}")

print("=" * 65)
print("  邊界測試開始（14 個案例）")
print("=" * 65)

# 01: 正常基準
run_case("01_baseline", base_summary(), base_meeting())

# 02: 無財務數字
run_case("02_no_numbers", base_summary(key_numbers=[]), base_meeting())

# 03: 無 Action Items
run_case("03_no_actions",
         base_summary(action_groups=[]),
         base_meeting(action_items={}))

# 04: 無與會人員
run_case("04_no_attendees", base_summary(), base_meeting(attendees=[]))

# 05: 無詳細段落
run_case("05_no_sections", base_summary(), base_meeting(sections=[]))

# 06: 只有1個主題
run_case("06_single_theme",
         base_summary(themes=[{"title": "唯一主題", "sub_heading": "子標題",
                                "points": ["點一", "點二", "點三"], "numbered_points": []}]),
         base_meeting())

# 07: 5個主題（3欄）
themes5 = [
    {"title": f"主題{i+1}：{'測試'*(i%2+1)}標題", "sub_heading": f"子標題{i+1}",
     "points": [f"重點{j+1}" for j in range(i+2)], "numbered_points": []}
    for i in range(5)
]
run_case("07_five_themes", base_summary(themes=themes5), base_meeting())

# 08: 7個主題（3欄 + 溢出）
themes7 = [
    {"title": f"主題{i+1}", "sub_heading": "", "points": [f"重點{j+1}" for j in range(3)], "numbered_points": []}
    for i in range(7)
]
run_case("08_seven_themes", base_summary(themes=themes7), base_meeting())

# 09: numbered_points 渲染
themes_num = [
    {"title": "流程主題", "sub_heading": "標準作業流程", "points": [],
     "numbered_points": ["步驟一：確認規格", "步驟二：製作樣品", "步驟三：品質驗收", "步驟四：出貨確認"]},
    {"title": "一般主題", "sub_heading": "", "points": ["要點一", "要點二"], "numbered_points": []},
]
run_case("09_numbered_points", base_summary(themes=themes_num), base_meeting())

# 10: 超長文字
long_title = "這是非常非常長的標題測試用來驗證換行與截斷的排版穩定性是否正常運作"
long_item  = "[ ] 超長名稱負責人甲乙丙：這是超長的任務說明，包含所有細節與步驟，確認版面不崩潰 - [TBD]"
run_case("10_long_text",
         base_summary(
             big_title=long_title,
             action_groups=[{
                 "group": "超長名稱測試組", "role": "超長名稱負責人甲乙丙",
                 "summary": "負責所有測試項目",
                 "items": [long_item],
             }]
         ),
         base_meeting())

# 11: 1個 Action Group
run_case("11_single_action_group",
         base_summary(action_groups=[{
             "group": "唯一負責組", "role": "廠長", "summary": "全部負責",
             "items": [
                 "[ ] 廠長：任務一 - [TBD]",
                 "[ ] 廠長：任務二 - [TBD]",
                 "[ ] 廠長：任務三 - [TBD]",
             ],
         }]),
         base_meeting())

# 12: 5個 Action Groups
groups5 = [{
    "group": f"部門{i+1}", "role": f"主管{i+1}", "summary": f"負責領域{i+1}",
    "items": [f"[ ] 主管{i+1}：部門{i+1}任務{j+1} - [TBD]" for j in range(2)]
} for i in range(5)]
run_case("12_five_action_groups", base_summary(action_groups=groups5), base_meeting())

# 13: 無引言/解方
run_case("13_no_quote",
         base_summary(solution_quote="", solutions=[]),
         base_meeting())

# 14: 完全空內容（最極端邊界）
run_case("14_empty_all",
         base_summary(key_numbers=[], themes=[], action_groups=[],
                      solution_quote="", solutions=[], objective=""),
         base_meeting(attendees=[], sections=[], action_items={}))

# ── 統計 ──────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("  測試結果")
print("=" * 65)
for r in results:
    print(r)
total = len(results)
ok    = sum(1 for r in results if "✅" in r)
print(f"\n  通過 {ok}/{total}" + (" ✅ 全部通過！" if ok == total else " ❌ 有失敗案例"))
