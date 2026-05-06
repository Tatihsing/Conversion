"""強化 key_numbers 規則：損益結論句型優先"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

pipeline_path = r"D:\錄音檔\meeting-auto\core\pipeline.py"
with open(pipeline_path, 'r', encoding='utf-8') as f:
    content = f.read()

OLD = """- 數量控制：key_numbers 最多 4 個，優先選最具衝擊力的數字，不要把所有明細都列進來
- red: true 的使用場景（以下任一即可標記）：
  * 明確的虧損、赤字、負值（如每日虧損 -600 元）
  * 「現況偏低且需調整」的現行數字（如現行日支250，遠低於合理水準400，標記現況250為red）
  * 成本超支、超標、下降趨勢的數字
  * 講者用「不合理」「太低」「問題」等語氣描述的數字
- 若有現況 vs 建議的對比，建議值不標 red；現況若明顯不足則標 red
- 無財務數字時設為空列表 []"""

NEW = """- 數量控制：key_numbers 最多 4 個，優先選最具衝擊力的結論數字
- 【最高優先級】損益結論句型：若逐字稿中出現「收X付Y」「賠Z」「虧損Z」「成本X報價Y」等
  損益結論，這些是最重要的 key_numbers，必須優先提取：
  範例：「我們收6000，要付6600，每天每人賠600」→
    提取：{"value":"6,000","label":"每日業務報價","unit":"元"}
         {"value":"6,600","label":"每日實際成本","unit":"元"}
         {"value":"-600","label":"每人每日虧損","unit":"元","red":true}
  而不是去列個別費用明細（250日支、400補貼等）
- 【次要】若有全成本合計（如6,462）且明確說出，也應列入
- red: true 使用場景：
  * 虧損、赤字、負值（每日賠600 → -600，red:true）
  * 「現況偏低且需調整」的數字（現行250遠低於合理水準400，標現況250 red:true）
  * 講者用「賠」「虧」「不合理」「問題」語氣描述的數字
- 若有現況 vs 建議對比，建議值不標 red；現況明顯不足才標 red
- 無財務數字時設為空列表 []"""

if OLD in content:
    content = content.replace(OLD, NEW)
    with open(pipeline_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] key_numbers 損益結論優先規則已更新")
else:
    print("[ERR] 找不到目標文字")
    idx = content.find("數量控制")
    print(f"找到 '數量控制' 位置: {idx}")
    print(content[max(0,idx-50):idx+300])
