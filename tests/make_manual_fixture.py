"""用Codex附带的Python运行，生成明确标记的两页模拟手册。"""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

folder=Path(__file__).parent/'fixtures';folder.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont('FixtureChinese','C:/Windows/Fonts/simhei.ttf'))
doc=canvas.Canvas(str(folder/'manual_demo.pdf'),pagesize=(595,842))
for lines in [
 ['模拟手册 DEMO-100','仅用于导入检索测试，不对应真实设备','E101 演示信号','E101 用于验证PDF导入和报警关键词检索。','实际原因未确认，未进行现场电气检查。','文本不得作为真实设备维修指导。'],
 ['模拟手册 DEMO-100 第二页','E202 温升示例','E202 与温升用于验证第二页原文检索。','温度尚未测量，不表示已经确认过热原因。','印刷页码 99  软件应标注PDF第2页']]:
    for i,line in enumerate(lines):
        doc.setFont('FixtureChinese',18 if i==0 else 13);doc.drawString(45,785-i*48,line)
    doc.showPage()
doc.save()
print(folder/'manual_demo.pdf')
