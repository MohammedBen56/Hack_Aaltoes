"""All LLM prompt templates. Use .format() to fill in variables."""

ORCHESTRATOR_PROMPT = """You are a Finnish architect reading a 1:50 pohjakuva (floor plan).

I have already extracted these dimension annotations from the PDF (values in millimeters, with x/y pixel coordinates):
{dimensions_json}

I have already extracted these room labels with their pixel coordinates:
{room_labels_json}

I have already extracted these structure type labels with coordinates:
{structure_labels_json}

Your task: Identify the COMPLETE exterior wall outline of the ENTIRE building footprint, including ALL attached structures.

CRITICAL RULES:
- The "exterior wall perimeter" is the TOTAL length of ALL walls that face the outside, regardless of whether the space behind them is heated or unheated
- INCLUDE porch walls (KUISTI) in the total perimeter — porches are enclosed structures with exterior walls
- INCLUDE storage room walls (VARASTO) in the total perimeter — these have exterior walls too
- INCLUDE any extensions, annexes, or utility rooms attached to the main building
- The party wall between duplex units A and B is NOT an exterior wall — do not include it
- The building is a duplex (loma-asunto A and B sharing a central party wall)

HOW TO DETERMINE DIMENSIONS:
- The drawing has DIMENSION CHAINS — lines of sequential measurements along each axis
- LEFT SIDE vertical chain: shows the building LENGTH broken into segments (KUISTI depth + main section + KUISTI depth). Sum ALL segments to get total length.
- RIGHT SIDE vertical chain: shows a more detailed breakdown of the same length into room-level segments. Note: some numbers may appear reversed due to text rotation — if a number seems wrong, try reading it backwards.
- TOP horizontal chain and BOTTOM horizontal chain: show the building WIDTH broken into room-width segments. Sum ALL segments in the chain to get total width — this may be larger than any single labeled overall dimension if the building has storage extensions.
- The overall width dimension (labeled separately) may only cover the MAIN building width. The full building width includes any VARASTO extension, so sum the individual segments instead.
- Calculate total_perimeter_mm = 2 * (total_length_mm + total_width_mm)
- For heated_perimeter_mm: use only the main heated section dimensions (excluding KUISTI and VARASTO)

PROGRAMMATIC CROSS-CHECK:
I have already computed these building dimensions programmatically from the dimension chains:
{programmatic_dims_json}
Use these as your PRIMARY reference for total_length_mm and total_width_mm.
- North and South walls are the LONG sides (total_length_mm).
- East and West walls are the SHORT sides / gable ends (total_width_mm).
- If your visual analysis disagrees with the programmatic values by more than 5%, note it in confidence_notes but STILL use the programmatic values for the wall_segments lengths.

Finnish terms:
- pohjakuva = floor plan
- KUISTI = porch/veranda (has exterior walls, include in perimeter)
- VARASTO = storage room (has exterior walls, include in perimeter)
- OLESKELU = living area
- US1 = exterior insulated wall type
- US2 = secondary exterior wall type
- loma-asunto = holiday apartment unit

Respond ONLY with valid JSON. No markdown, no explanation, no preamble.

Return exactly this JSON schema (fill in real values from the drawing dimensions):
{{
  "building_outline": {{
    "description": "Brief description of the complete building footprint",
    "total_length_mm": 0,
    "total_width_mm": 0,
    "heated_length_mm": 0,
    "heated_width_mm": 0,
    "wall_segments": [
      {{
        "id": "N1",
        "direction": "north",
        "length_mm": 0,
        "description": "Full north wall including all attached structures"
      }},
      {{
        "id": "S1",
        "direction": "south",
        "length_mm": 0,
        "description": "Full south wall including all attached structures"
      }},
      {{
        "id": "E1",
        "direction": "east",
        "length_mm": 0,
        "description": "Full east wall including any extensions"
      }},
      {{
        "id": "W1",
        "direction": "west",
        "length_mm": 0,
        "description": "Full west wall including any extensions"
      }}
    ]
  }},
  "total_perimeter_mm": 0,
  "heated_perimeter_mm": 0,
  "confidence_notes": "Any uncertainties or assumptions made"
}}"""


FACADE_PROMPT = """You are a Finnish architect analyzing the {direction_fi} facade (julkisivu {suuntaan}) of a loma-asunto duplex.

The wall segment data from the floor plan analysis is:
{wall_segment_json}

HARD CONSTRAINTS (from floor plan analysis — do NOT override these):
- This facade's wall length is {wall_length_mm}mm. Use this value for wall_length_mm in your response.
- This wall is a {wall_type_label}. {gable_instruction}

I am providing you with two images:
1. The facade elevation drawing (julkisivu) for the {direction_en} side
2. The cross-section drawing (leikkaus B-B) for height reference

VISUAL ANALYSIS REQUIRED:
- For gable end walls: Find the räystäs (eave) and harjakorkeus (ridge) elevation markers in the cross-section drawing (leikkaus) AND the facade drawing to calculate gable_triangle_height_mm = (ridge_level - eave_level) * 1000.
- For long walls: Confirm the wall is rectangular (no gable triangle).

Your task: Extract all wall geometry, openings, and cladding information visible in the facade drawing.

Critical measurements — how to determine wall height:
- Look at the elevation markers (numbers like +X.XXX or -X.XXX) in the section drawing (second image)
- The building datum is +-0.000 (top of the sokkel/foundation). This is where the exterior wall starts.
- The räystäs (eave) is the TOP of the rectangular wall, where the roof overhang begins. It is marked with an elevation like +X.XXX. It is the HIGHEST horizontal line on the wall panel, NOT the ridge.
- Exterior wall height (from_ground_to_eave) = eave_elevation_meters * 1000 (since datum is 0.000)
- The sokkel below +-0.000 is concrete foundation, NOT part of the exterior wall.
- If gable end: the harjakorkeus (ridge) is the peak of the roof, marked with a higher elevation. Triangle height = (ridge_level - eave_level) in meters × 1000.

Finnish window/door code convention (read from the drawing):
- Code format is TYPE WIDTHxHEIGHT where numbers are in 100mm modules
- "UO 10x21" = ulko-ovi (exterior door) 1000mm wide x 2100mm tall
- "A-15x5"  = ikkuna (window) 1500mm wide x 500mm tall
- "A-8x21"  = ikkuna 800mm wide x 2100mm tall
- Count each unique opening code and report how many of each appear on this facade

Cladding materials to identify:
- VAAKAULKOVERHOUSPANEELI 28x170 (horizontal panel, 28mm thick x 170mm wide)
- ULKOVERHOUSPANEELI 21x95 (vertical panel, 21mm thick x 95mm wide)
- Estimate what percentage of the wall uses each type

Important:
- The sokkel (concrete foundation) is below +-0.000 and is NOT part of the exterior wall
- Exterior wall height = from +-0.000 (building datum) to eave level. Determine the exact values from elevation markers in the drawings.
- Set gross_wall_area_m2, total_opening_area_m2, net_cladding_area_m2 to 0 — these are calculated later

Respond ONLY with valid JSON. No markdown, no explanation, no preamble.

Return exactly this JSON schema (fill in real values from the drawing):
{{
  "facade_direction": "{direction_en}",
  "wall_height_mm": {{
    "from_ground_to_eave": 0,
    "ground_level": 0.000,
    "eave_level": "",
    "ridge_level": "",
    "has_gable_triangle": false,
    "gable_triangle_height_mm": 0,
    "notes": "Read elevation values from the section drawing"
  }},
  "wall_length_mm": 0,
  "openings": [
    {{
      "type": "window",
      "code": "A-15x5",
      "width_mm": 1500,
      "height_mm": 500,
      "count": 1
    }}
  ],
  "cladding_material": {{
    "primary": "VAAKAULKOVERHOUSPANEELI 28x170",
    "secondary": "ULKOVERHOUSPANEELI 21x95",
    "primary_coverage_percent": 70,
    "secondary_coverage_percent": 30
  }},
  "gross_wall_area_m2": 0,
  "total_opening_area_m2": 0,
  "net_cladding_area_m2": 0
}}"""
