from pdf_utils import extract_text_annotations
from collections import Counter

here = 'here'
f2 = extract_text_annotations(f'{here}/ARK 03 Julkisivut_A_2609.pdf')
s2 = extract_text_annotations(f'{here}/ARK 04 Leikkaus_A_2609.pdf')

all_elevations = s2.get('elevations', []) + f2.get('elevations', [])
all_values = [float(e['value']) for e in all_elevations]

relative_values = [v for v in all_values if v <= 12.0]
freq = Counter([round(v, 2) for v in relative_values])
ridge_level = max(relative_values)
rounded_vals = [round(v, 3) for v in relative_values]
distinct_levels = sorted(list(set(rounded_vals)), reverse=True)

valid_levels = [level for level in distinct_levels if level < ridge_level - 0.3 and level > 0]
if valid_levels:
    valid_levels.sort(key=lambda lvl: (freq[round(lvl, 2)], lvl), reverse=True)
    eave_level = valid_levels[0]

print("All values:", sorted(all_values))
print("Relative values:", sorted(relative_values))
print("distinct_levels:", distinct_levels)
print("freq:", dict(freq))
print("valid_levels:", valid_levels)
print("eave_level:", eave_level)
