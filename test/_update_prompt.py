"""
更新 pipeline.py 中 key_numbers 的規則說明（允許語境推導計算）
"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

pipeline_path = r"D:\錄音檔\meeting-auto\core\pipeline.py"
with open(pipeline_path, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = """■ 數據面板（key_numbers）— 提煉洞察結論，而非列舉明細：
- 選出 2~4 個「最能說明問題核心或決策依據」的關鍵數字
- 優先選擇：對比數字（成本 vs 收入）、結論性數字（虧損額、效益%）、決策依據數字
- 若有計算推導（A - B = C），直接呈現結論 C，label 說明其意義
- 舉例：與其列出各項費用明細（差旅費250、補貼400、油資540），
  不如列出【全成本6,462元（每人每日全成本）】和【-600元（每日出差虧損，red:true）】
- 用 red: true 標記虧損、超支、下降等負面指標
- 無財務數字時設為空列表 []"""

NEW = """■ 數據面板（key_numbers）— 依語境決定是否加總與如何呈現：
- 選出 2~4 個「最能說明問題核心或決策依據」的關鍵數字
- 優先選擇：對比數字（成本 vs 收入）、結論性數字（虧損額、效益%）、決策依據數字
- 【語境推導授權】：若講者在逐字稿中逐一列出費用明細，且討論語氣明顯在分析「總成本壓力」
  或「整體負擔」，你應主動將這些明細加總，計算出結論性數字呈現（這是分析師的職責）
  例如：講者列出薪資+勞健退+差旅+油資等明細並討論「一個人出去一天要多少錢」，
  你應計算合計並以「每人每日全成本 X 元」呈現，而不是把每個明細拆開列出
- 【保守原則】：若講者只是隨口提及某個數字，無明顯加總意圖，則直接用該數字，不要強行加總
- 若計算出推導數字，在 label 中說明（如「每人每日全成本（薪資+差旅+油資合計）」）
- 用 red: true 標記虧損、超支、下降等負面指標
- 無財務數字時設為空列表 []"""

if OLD in content:
    content = content.replace(OLD, NEW)
    with open(pipeline_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] key_numbers 規則已更新（語境推導版）")
else:
    print("[ERR] 找不到目標文字，請確認")
    # debug: 找最接近的位置
    idx = content.find("■ 數據面板")
    if idx >= 0:
        print("找到 '■ 數據面板' 位置，周圍內容：")
        print(content[idx:idx+300])
