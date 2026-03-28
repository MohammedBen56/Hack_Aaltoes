import os
import json

# Load .env file if present (before any API calls)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from google import genai
from google.genai import types

from pdf_utils import (extract_text_annotations, render_page_to_image, render_cropped_region,
                       FACADE_CROPS, compute_building_dimensions, compute_wall_height)
from prompts import ORCHESTRATOR_PROMPT, FACADE_PROMPT
from calculations import calculate_quantities

FACADE_META = {
    'north': {'direction_fi': 'pohjoinen', 'suuntaan': 'POHJOISEEN'},
    'south': {'direction_fi': 'etelä', 'suuntaan': 'ETELÄÄN'},
    'east': {'direction_fi': 'itä', 'suuntaan': 'ITÄÄN'},
    'west': {'direction_fi': 'länsi', 'suuntaan': 'LÄNTEEN'},
}


def call_gemini_vision(image_bytes: bytes, prompt: str, additional_images: list = None) -> dict:
    """Call Gemini with image(s) + prompt. Return parsed JSON. Retry up to 3 times."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    contents = [types.Part.from_bytes(data=image_bytes, mime_type="image/png")]
    if additional_images:
        for img in additional_images:
            contents.append(types.Part.from_bytes(data=img, mime_type="image/png"))
    contents.append(types.Part.from_text(text=prompt))

    last_text = ""
    for attempt in range(3):
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = response.text.strip()
        last_text = text

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"  [WARN] JSON parse failed on attempt {attempt + 1}, retrying...")

    os.makedirs("output", exist_ok=True)
    debug_path = "output/debug_last_response.txt"
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(last_text)
    raise ValueError(
        f"Failed to get valid JSON from Gemini after 3 attempts. "
        f"Last response saved to {debug_path}\nPreview: {last_text[:300]}"
    )


def identify_building_outline(floor_plan_image: bytes, annotations: dict, bldg_dims: dict) -> dict:
    """Phase 2: one Gemini call to identify the heated building envelope."""
    print("  Calling Gemini — building outline identification...")

    prompt = ORCHESTRATOR_PROMPT.format(
        dimensions_json=json.dumps(annotations['dimensions_mm'], indent=2),
        room_labels_json=json.dumps(annotations['room_labels'], indent=2),
        structure_labels_json=json.dumps(annotations['structure_labels'], indent=2),
        programmatic_dims_json=json.dumps(bldg_dims, indent=2),
    )

    result = call_gemini_vision(floor_plan_image, prompt)

    # Validate perimeter closure against total building dimensions
    outline = result.get('building_outline', {})
    length = outline.get('total_length_mm', 0)
    width = outline.get('total_width_mm', 0)
    reported = result.get('total_perimeter_mm', 0)

    if length > 0 and width > 0 and reported > 0:
        expected = 2 * (length + width)
        dev = abs(reported - expected) / expected * 100
        if dev > 2:
            print(f"  [WARN] Perimeter closure: expected {expected}mm, got {reported}mm ({dev:.1f}% off)")
        else:
            print(f"  [OK] Perimeter closure: {reported}mm ({dev:.1f}% deviation)")

    return result


def analyze_facade(direction: str, facade_image: bytes, section_image: bytes,
                   wall_segment: dict, wall_length_mm: int, is_gable_end: bool) -> dict:
    """Phase 3: one Gemini call per facade to extract openings and heights."""
    print(f"  Calling Gemini — {direction} facade analysis...")

    meta = FACADE_META[direction]

    if is_gable_end:
        wall_type_label = "GABLE END (pääty)"
        gable_instruction = ("Gable end walls have a triangular area above the eave. "
                             "Set has_gable_triangle=true and determine gable_triangle_height_mm "
                             "from elevation markers (ridge_level - eave_level) * 1000.")
    else:
        wall_type_label = "LONG WALL (pitkä seinä)"
        gable_instruction = ("Long walls do NOT have gable triangles. "
                             "Set has_gable_triangle=false and gable_triangle_height_mm=0.")

    prompt = FACADE_PROMPT.format(
        direction_fi=meta['direction_fi'],
        suuntaan=meta['suuntaan'],
        direction_en=direction,
        wall_segment_json=json.dumps(wall_segment, indent=2),
        wall_length_mm=wall_length_mm,
        wall_type_label=wall_type_label,
        gable_instruction=gable_instruction,
    )

    result = call_gemini_vision(facade_image, prompt, additional_images=[section_image])
    result['facade_direction'] = direction  # enforce correct direction
    return result


def run_pipeline(floor_plan_path: str, facades_path: str, section_path: str,
                 progress_callback=None) -> dict:
    """
    Run the full 4-phase ArchiMeasure pipeline.

    progress_callback(stage: int, message: str) — optional hook for UI updates.
    Returns a dict with keys: annotations, building_outline, facade_results, quantities.
    """

    def progress(stage, msg):
        print(f"[Stage {stage}] {msg}")
        if progress_callback:
            progress_callback(stage, msg)

    # ── PHASE 1: Extract text + render images ────────────────────────────────
    progress(1, "Extracting text annotations from PDFs...")

    floor_ann = extract_text_annotations(floor_plan_path)
    facades_ann = extract_text_annotations(facades_path)
    section_ann = extract_text_annotations(section_path)

    print(f"  Floor plan: {len(floor_ann['dimensions_mm'])} dims, "
          f"{len(floor_ann['room_labels'])} room labels, "
          f"{len(floor_ann['structure_labels'])} structure labels")
    print(f"  Facades:    {len(facades_ann['dimensions_mm'])} dims, "
          f"{len(facades_ann['elevations'])} elevations")
    print(f"  Section:    {len(section_ann['dimensions_mm'])} dims, "
          f"{len(section_ann['elevations'])} elevations")

    # Programmatically compute building dimensions from dimension chains
    bldg_dims = compute_building_dimensions(floor_ann)
    print(f"  Building dims (programmatic): "
          f"length={bldg_dims['total_length_mm']}mm ({'+'.join(str(v) for v in bldg_dims['left_chain'])}), "
          f"width={bldg_dims['total_width_mm']}mm ({'+'.join(str(v) for v in bldg_dims['top_chain'])})")
    print(f"  Total perimeter (programmatic): {bldg_dims['total_perimeter_mm']}mm = {bldg_dims['total_perimeter_mm']/1000:.2f}m")
    print(f"  Heated perimeter (programmatic): {bldg_dims['heated_perimeter_mm']}mm = {bldg_dims['heated_perimeter_mm']/1000:.2f}m")

    # Programmatically compute wall height from elevation markers
    wall_h = compute_wall_height(section_ann, facades_ann)
    print(f"  Wall height (programmatic): {wall_h['wall_height_mm']}mm "
          f"(eave={wall_h['eave_level']}, datum={wall_h['datum']}, "
          f"ridge={wall_h['ridge_level']}, gable_h={wall_h['gable_height_mm']}mm)")

    total_perimeter_mm = bldg_dims['total_perimeter_mm']
    heated_perimeter_mm = bldg_dims['heated_perimeter_mm']

    floor_plan_image = render_page_to_image(floor_plan_path, dpi=200)
    section_image = render_page_to_image(section_path, dpi=200)

    facade_images = {}
    for direction, bbox in FACADE_CROPS.items():
        facade_images[direction] = render_cropped_region(facades_path, 0, bbox, dpi=200)

    # ── PHASE 2: Building outline (LLM calculates dimensions) ──
    progress(2, "Identifying building outline...")

    outline_result = identify_building_outline(floor_plan_image, floor_ann, bldg_dims)
    
    # Use LLM's dynamically calculated perimeters if available, else fallback
    total_perimeter_mm = outline_result.get('total_perimeter_mm') or bldg_dims['total_perimeter_mm']
    heated_perimeter_mm = outline_result.get('heated_perimeter_mm') or bldg_dims['heated_perimeter_mm']

    # Build wall segment lookup by direction
    wall_segments = {
        seg['direction']: seg
        for seg in outline_result.get('building_outline', {}).get('wall_segments', [])
    }

    # ── PHASE 3: Per-facade analysis ──────────────────────────────────────────
    facade_results = []

    # Determine gable assignment: N/S = long sides (no gable), E/W = short/gable ends
    # Use heated dimensions for facade wall lengths (excludes porch/storage extensions)
    prog_length = bldg_dims['heated_length_mm'] or bldg_dims['total_length_mm']
    prog_width = bldg_dims['heated_width_mm'] or bldg_dims['total_width_mm']
    facade_config = {
        'north': {'wall_length_mm': prog_length, 'is_gable_end': False},
        'south': {'wall_length_mm': prog_length, 'is_gable_end': False},
        'east':  {'wall_length_mm': prog_width,  'is_gable_end': True},
        'west':  {'wall_length_mm': prog_width,  'is_gable_end': True},
    }

    for i, direction in enumerate(['north', 'south', 'east', 'west'], 1):
        progress(3, f"Analyzing facades ({i}/4): {direction}...")

        wall_seg = wall_segments.get(direction, {})
        cfg = facade_config[direction]
        try:
            data = analyze_facade(direction, facade_images[direction], section_image,
                                  wall_seg, cfg['wall_length_mm'], cfg['is_gable_end'])

            # Belt-and-suspenders: override LLM values with programmatic data
            data['wall_length_mm'] = cfg['wall_length_mm']
            if not cfg['is_gable_end']:
                data.setdefault('wall_height_mm', {})['has_gable_triangle'] = False
                data.setdefault('wall_height_mm', {})['gable_triangle_height_mm'] = 0

            # Cross-check wall height against programmatic value
            llm_h = data.get('wall_height_mm', {}).get('from_ground_to_eave', 0)
            if llm_h and wall_h['wall_height_mm'] and abs(llm_h - wall_h['wall_height_mm']) / wall_h['wall_height_mm'] > 0.10:
                print(f"  [WARN] {direction} height mismatch: LLM={llm_h}mm vs programmatic={wall_h['wall_height_mm']}mm, using programmatic")
                data['wall_height_mm']['from_ground_to_eave'] = wall_h['wall_height_mm']

            facade_results.append(data)
            n_openings = len(data.get('openings', []))
            h = data.get('wall_height_mm', {}).get('from_ground_to_eave', '?')
            length = data.get('wall_length_mm', '?')
            print(f"  {direction}: length={length}mm, height={h}mm, {n_openings} opening type(s)")
        except Exception as e:
            print(f"  [ERROR] {direction} facade failed: {e}")
            facade_results.append({
                'facade_direction': direction,
                'error': str(e),
                'manual_review_needed': True,
                'wall_height_mm': {
                    'from_ground_to_eave': wall_h['wall_height_mm'],
                    'has_gable_triangle': cfg['is_gable_end'],
                    'gable_triangle_height_mm': wall_h['gable_height_mm'] if cfg['is_gable_end'] else 0,
                },
                'wall_length_mm': cfg['wall_length_mm'],
                'openings': [],
                'cladding_material': {
                    'primary_coverage_percent': 70,
                    'secondary_coverage_percent': 30,
                },
            })

    # ── PHASE 4: Quantity calculation ─────────────────────────────────────────
    progress(4, "Calculating quantities...")

    quantities = calculate_quantities(facade_results, total_perimeter_mm, heated_perimeter_mm,
                                      wall_height_mm=wall_h['wall_height_mm'])

    # Print summary
    q = quantities
    t = q['totals']
    m = q['materials']
    print(f"\n{'='*50}")
    print(f"  Ext. wall perimeter:     {q['perimeter_m']} m")
    print(f"  Ext. wall surface area:  {q['exterior_wall_surface_area_m2']} m2")
    print(f"  Heated perimeter:        {q['heated_perimeter_m']} m")
    print(f"  Gross wall area:         {t['total_gross_wall_area_m2']} m2")
    print(f"  Total openings:          {t['total_opening_area_m2']} m2")
    print(f"  Net cladding area:       {t['total_net_cladding_area_m2']} m2")
    print(f"  VAAKA 28x170 (w/waste):  {m['vaakaulkoverhouspaneeli_28x170']['running_meters_with_waste']} rm")
    print(f"  ULKO  21x95  (w/waste):  {m['ulkoverhouspaneeli_21x95']['running_meters_with_waste']} rm")
    val = q['validation']
    status = "PASS" if val['perimeter_closure_check'] else "FAIL"
    print(f"  Perimeter closure:       {status} ({val['deviation_percent']:.1f}% deviation)")
    print(f"{'='*50}")

    # Save output
    os.makedirs("output", exist_ok=True)
    result = {
        'annotations': {
            'floor_plan': floor_ann,
            'facades': facades_ann,
            'section': section_ann,
        },
        'building_outline': outline_result,
        'facade_results': facade_results,
        'quantities': quantities,
    }
    out_path = "output/results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Results saved -> {out_path}")

    return result


if __name__ == "__main__":
    import os

    here = os.path.join(os.path.dirname(__file__), "here")
    result = run_pipeline(
        floor_plan_path=os.path.join(here, "ARK 02 Pohjakuva 1111 (2).pdf"),
        facades_path=os.path.join(here, "ARK 03 Julkisivut.pdf"),
        section_path=os.path.join(here, "ARK 04 Leikkaus.pdf"),
    )
