from pdf_utils import extract_text_annotations, compute_wall_height, compute_building_dimensions
import json

here = 'here'

print('=== HOUSE 1 (original) ===')
f1 = extract_text_annotations(f'{here}/ARK 03 Julkisivut.pdf')
s1 = extract_text_annotations(f'{here}/ARK 04 Leikkaus.pdf')
wh1 = compute_wall_height(s1, f1)
print(f"eave={wh1['eave_level']}m, ridge={wh1['ridge_level']}m, wall_height={wh1['wall_height_mm']}mm, gable_h={wh1['gable_height_mm']}mm")
print(f'Expected: eave=4.015, wall_height=4015mm, gable_h=2885mm')

print()
print('=== HOUSE 2 (new) ===')
f2 = extract_text_annotations(f'{here}/ARK 03 Julkisivut_A_2609.pdf')
s2 = extract_text_annotations(f'{here}/ARK 04 Leikkaus_A_2609.pdf')
wh2 = compute_wall_height(s2, f2)
print(f"eave={wh2['eave_level']}m, ridge={wh2['ridge_level']}m, wall_height={wh2['wall_height_mm']}mm, gable_h={wh2['gable_height_mm']}mm")

print()
print('=== HOUSE 2 Building Dims ===')
fp2 = extract_text_annotations(f'{here}/ARK 02 Pohjakuva_A_1602.pdf')
bd2 = compute_building_dimensions(fp2)
print(json.dumps(bd2, indent=2))
