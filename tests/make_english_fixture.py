"""Create an owned English-code fixture with standard PDF Helvetica text."""
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
writer=PdfWriter()
for text in ['E202 Overtemperature. Simulated test, cause unconfirmed.','E2020 Different alarm.','E202_1 Subgroup alarm.','E202-1 Another subgroup alarm.','2310 Overcurrent. Simulated test, no actual device.','23100 Different numeric alarm.']:
    page=writer.add_blank_page(595,842)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 40 760 Td ('+text+') Tj ET').encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(stream)
writer.write(Path(__file__).parent/'fixtures/manual_english_demo.pdf')
