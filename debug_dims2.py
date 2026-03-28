from pdf_utils import extract_text_annotations, _maybe_reverse
import re

here = 'here'
fp2 = extract_text_annotations(f'{here}/ARK 02 Pohjakuva_A_1602.pdf')

dims = fp2['dimensions_mm']
page = fp2['page_size']

print("Page width:", page['width'])
print("Total dims found:", len(dims))

for d in dims:
    if d['value'] > 5000:
        print(f"Dim > 5000: {d['value']} at x={d['x']}, y={d['y']}")
