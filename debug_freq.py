from pdf_utils import extract_text_annotations
from collections import Counter
here = 'here'
f1 = extract_text_annotations(f'{here}/ARK 03 Julkisivut.pdf')
s1 = extract_text_annotations(f'{here}/ARK 04 Leikkaus.pdf')
all_elevations = s1.get('elevations', []) + f1.get('elevations', [])
all_values = [float(e['value']) for e in all_elevations]
relative_values = [v for v in all_values if v <= 12.0]
freq = Counter([round(v, 2) for v in relative_values])
print("House 1 Freqs:")
for k, v in sorted(freq.items(), reverse=True):
    print(k, ":", v)
