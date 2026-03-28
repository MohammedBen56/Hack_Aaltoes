from pdf_utils import extract_text_annotations, compute_building_dimensions
here = 'here'
fp1 = extract_text_annotations(f'{here}/ARK 02 Pohjakuva 1111 (2).pdf')
bd1 = compute_building_dimensions(fp1)

print("=== HOUSE 1 Building Dims ===")
import json
print(json.dumps(bd1, indent=2))
