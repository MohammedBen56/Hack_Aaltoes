import pdfplumber
import fitz  # PyMuPDF
import re

FACADE_CROPS = {
    'west':  (0.00, 0.00, 0.42, 0.50),
    'north': (0.30, 0.00, 0.72, 0.50),
    'east':  (0.00, 0.45, 0.42, 1.00),
    'south': (0.30, 0.45, 0.72, 1.00),
}

ROOM_NAMES = {'KUISTI', 'OLESKELU', 'KPH', 'WC', 'MH', 'KÄYTÄVÄ', 'VAR', 'ET',
              'Huone', 'VARASTO', 'IVK'}
STRUCT_NAMES = {'US1', 'US2', 'YP1', 'AP1', 'VP'}

DIM_PATTERN = re.compile(r'^\d{3,5}$')
ELEV_PATTERN = re.compile(r'^[+-]?\d+\.\d{3}$')


def _maybe_reverse(s: str) -> int:
    """Return the integer value of a dimension string, reversing if it appears rotated."""
    val = int(s)
    rev_s = s[::-1]
    rev = int(rev_s)

    # If original starts with '0', it's definitely reversed (e.g. "0081" -> "1800")
    if s[0] == '0':
        return rev

    # If val is unrealistically large for a building dimension (> 20000mm = 20m)
    # and its reverse is plausible, use the reverse (e.g. "27441" -> 14472)
    if val > 20000 and rev <= 20000:
        return rev

    # Prefer the "rounder" number (more trailing zeros = more likely a real dimension)
    def trailing_zeros(n):
        s2 = str(n)
        return len(s2) - len(s2.rstrip('0'))

    if trailing_zeros(rev) > trailing_zeros(val):
        return rev

    return val


def extract_text_annotations(pdf_path: str) -> dict:
    """Extract all dimension annotations, elevations, room labels, and structure labels from PDF page 0."""
    dimensions_mm = []
    elevations = []
    room_labels = []
    structure_labels = []
    page_size = {}

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        page_size = {'width': float(page.width), 'height': float(page.height)}

        words = page.extract_words(extra_attrs=['size', 'fontname'])

        for word in words:
            text = word['text'].strip()
            x = float(word['x0'])
            y = float(word['top'])

            if DIM_PATTERN.match(text):
                val = _maybe_reverse(text)
                dimensions_mm.append({'value': val, 'raw': text, 'x': x, 'y': y})
            elif ELEV_PATTERN.match(text):
                elevations.append({'value': text, 'x': x, 'y': y})
            elif text in ROOM_NAMES:
                room_labels.append({'name': text, 'x': x, 'y': y})
            elif text in STRUCT_NAMES:
                structure_labels.append({'name': text, 'x': x, 'y': y})

    return {
        'dimensions_mm': dimensions_mm,
        'elevations': elevations,
        'room_labels': room_labels,
        'structure_labels': structure_labels,
        'page_size': page_size,
    }


def compute_building_dimensions(floor_plan_annotations: dict) -> dict:
    """Compute total building length and width by summing dimension chains programmatically.

    In the floor plan, dimension chains are groups of annotations at similar x or y coordinates.
    - Left-side vertical chain (similar x, varying y): segments along building LENGTH
    - Top/bottom horizontal chain (similar y, varying x): segments along building WIDTH
    """
    dims = floor_plan_annotations['dimensions_mm']
    page = floor_plan_annotations['page_size']

    # Only consider dimensions in the ground floor area (left ~40% of page for this layout)
    ground_floor_x_limit = page['width'] * 0.45
    ground_dims = [d for d in dims if d['x'] < ground_floor_x_limit]

    # --- Find the LEFT-SIDE vertical chain (building length) ---
    # These share a similar x coordinate (leftmost dimension column)
    min_x = min(d['x'] for d in ground_dims) if ground_dims else 0
    left_chain = sorted(
        [d for d in ground_dims if abs(d['x'] - min_x) < 30],
        key=lambda d: d['y']
    )
    total_length_mm = sum(d['value'] for d in left_chain) if left_chain else 0

    # The largest single value in the left chain is typically the main heated section
    heated_length_mm = max((d['value'] for d in left_chain), default=0)

    # --- Find the TOP horizontal chain (building width) ---
    # These share a similar y coordinate (topmost dimension row)
    min_y = min(d['y'] for d in ground_dims) if ground_dims else 0
    top_chain = sorted(
        [d for d in ground_dims if abs(d['y'] - min_y) < 15],
        key=lambda d: d['x']
    )
    total_width_mm = sum(d['value'] for d in top_chain) if top_chain else 0

    # Look for a labeled overall width (a single dimension at a slightly different y, close to the top chain)
    # This is the main building width without extensions
    overall_width_dims = [
        d for d in ground_dims
        if abs(d['y'] - min_y) > 10 and abs(d['y'] - min_y) < 40
        and d['value'] > 5000  # must be a significant dimension
    ]
    heated_width_mm = max((d['value'] for d in overall_width_dims), default=total_width_mm)

    total_perimeter_mm = 2 * (total_length_mm + total_width_mm)
    heated_perimeter_mm = 2 * (heated_length_mm + heated_width_mm)

    return {
        'total_length_mm': total_length_mm,
        'total_width_mm': total_width_mm,
        'heated_length_mm': heated_length_mm,
        'heated_width_mm': heated_width_mm,
        'total_perimeter_mm': total_perimeter_mm,
        'heated_perimeter_mm': heated_perimeter_mm,
        'left_chain': [d['value'] for d in left_chain],
        'top_chain': [d['value'] for d in top_chain],
    }


def compute_wall_height(section_annotations: dict, facade_annotations: dict) -> dict:
    """Compute wall height from elevation markers in the section and facade drawings.

    Wall height = eave_level - building_datum (+-0.000)

    Finnish section drawings often show BOTH relative elevations (±0.000 based) and
    absolute sea-level elevations side by side. Absolute values are typically > 10m in
    Finnish residential context, so we filter them out to work only with relative values.
    """
    from collections import Counter

    # Combine elevations from both section and facade PDFs
    all_elevations = section_annotations.get('elevations', []) + facade_annotations.get('elevations', [])
    all_values = [float(e['value']) for e in all_elevations]

    if not all_values:
        return {'wall_height_mm': 3000, 'eave_level': 3.0, 'ridge_level': 6.0,
                'datum': 0.0, 'gable_height_mm': 3000}

    # Filter out absolute sea-level elevations: Finnish residential buildings have
    # relative heights < 12m. Values > 12 are absolute (sea-level reference).
    relative_values = [v for v in all_values if v <= 12.0]
    if not relative_values:
        relative_values = all_values  # fallback: use all if nothing passes filter

    # Building datum is closest to 0.000 (either -0.000, +0.000, or -0.020)
    datum = min(relative_values, key=lambda v: abs(v))

    # Ridge level: highest relative elevation (peak of roof)
    # Some chimneys/exhausts might be higher or slightly lower than ridge, 
    # but eave usually repeats on both sides.
    
    # Let's count frequencies of values rounded to 2 decimal places to group together slight variations
    from collections import Counter
    freq = Counter([round(v, 2) for v in relative_values])

    ridge_level = max(relative_values)

    # Use original values rounded to 3 places but mapped to their group frequencies
    rounded_vals = [round(v, 3) for v in relative_values]
    distinct_levels = sorted(list(set(rounded_vals)), reverse=True)
    
    eave_level = ridge_level  # fallback
    
    valid_levels = [level for level in distinct_levels if level < ridge_level - 0.3 and level > 0]
    if valid_levels:
        # Pick the level with highest frequency (using 2 decimal places mapping), on tie, pick highest level
        valid_levels.sort(key=lambda lvl: (freq[round(lvl, 2)], lvl), reverse=True)
        eave_level = valid_levels[0]

    wall_height_m = eave_level - max(datum, 0.0)  # height from datum (or 0.0) to eave
    wall_height_mm = round(wall_height_m * 1000)
    gable_height_mm = round((ridge_level - eave_level) * 1000)

    return {
        'wall_height_mm': wall_height_mm,
        'eave_level': eave_level,
        'ridge_level': ridge_level,
        'datum': datum,
        'gable_height_mm': gable_height_mm,
    }


def render_page_to_image(pdf_path: str, page_num: int = 0, dpi: int = 200) -> bytes:
    """Render a PDF page as PNG bytes."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def render_cropped_region(pdf_path: str, page_num: int, bbox_fraction: tuple, dpi: int = 200) -> bytes:
    """Render a cropped region of a PDF page as PNG bytes.
    bbox_fraction = (x0_frac, y0_frac, x1_frac, y1_frac) as 0-1 fractions of page dimensions.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    r = page.rect  # full page rect

    x0 = r.x0 + bbox_fraction[0] * r.width
    y0 = r.y0 + bbox_fraction[1] * r.height
    x1 = r.x0 + bbox_fraction[2] * r.width
    y1 = r.y0 + bbox_fraction[3] * r.height

    clip = fitz.Rect(x0, y0, x1, y1)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    return pix.tobytes("png")


if __name__ == "__main__":
    import os
    import json

    here = os.path.join(os.path.dirname(__file__), "here")
    pdfs = {
        'floor_plan': os.path.join(here, "ARK 02 Pohjakuva 1111 (2).pdf"),
        'facades':    os.path.join(here, "ARK 03 Julkisivut.pdf"),
        'section':    os.path.join(here, "ARK 04 Leikkaus.pdf"),
    }

    os.makedirs("output", exist_ok=True)

    for name, path in pdfs.items():
        print(f"\n=== {name}: {os.path.basename(path)} ===")
        ann = extract_text_annotations(path)
        print(f"  Page size: {ann['page_size']}")
        print(f"  Dimensions ({len(ann['dimensions_mm'])}): {ann['dimensions_mm'][:15]}")
        print(f"  Elevations ({len(ann['elevations'])}): {ann['elevations']}")
        print(f"  Room labels ({len(ann['room_labels'])}): {ann['room_labels']}")
        print(f"  Structure labels ({len(ann['structure_labels'])}): {ann['structure_labels']}")

        img = render_page_to_image(path, dpi=100)
        out = f"output/page_{name}.png"
        with open(out, "wb") as f:
            f.write(img)
        print(f"  Rendered -> {out}")

    print("\n=== Facade crops ===")
    for direction, bbox in FACADE_CROPS.items():
        img = render_cropped_region(pdfs['facades'], 0, bbox, dpi=150)
        out = f"output/facade_{direction}.png"
        with open(out, "wb") as f:
            f.write(img)
        print(f"  {direction} -> {out}")

    print("\nDone. Check output/ folder.")
