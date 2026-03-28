# CLAUDE.md — ArchiMeasure: Architectural Drawing Analyzer MVP

## PROJECT OVERVIEW

### What This Is
ArchiMeasure is a hackathon MVP that takes standard Finnish architectural PDF drawings (floor plan, facade elevations, cross-section) and automatically calculates:
1. **Heated perimeter** — the in-wall perimeter of the insulated building envelope, excluding porches, decks, and unheated structures
2. **Exterior wall area** — gross and net (minus windows/doors/sokkel) per facade direction
3. **Cladding material quantities** — board running meters, board counts, and waste-adjusted totals for the specific panel types specified in the drawings

### The Problem It Solves
Construction quantity takeoff from architectural drawings is manual, slow, and error-prone. An architect or estimator reads each drawing, traces the exterior walls, measures heights from section drawings, counts windows and doors from elevations, then calculates material needs by hand or in Excel. For a single-family house this takes 1-3 hours. ArchiMeasure does it in under 60 seconds.

### Core Technical Approach
The system uses a **hybrid programmatic + vision LLM pipeline** — not a naive "screenshot the PDF and ask GPT." PDFs contain a machine-readable text layer with dimension annotations and room labels already embedded. We extract those first (zero hallucination risk), then use a vision LLM only for the harder task of understanding spatial relationships: which dimensions belong to which walls, where the heated envelope boundary is, and what openings exist on each facade.

The pipeline runs in 4 phases:
1. **Programmatic text extraction** (pdfplumber) — pulls all dimensions, elevations, room labels, and structural markers with (x,y) coordinates. No LLM.
2. **Orchestrator** (1 Gemini vision call) — receives the floor plan image + pre-extracted annotations, identifies the exterior wall polygon, excludes porches (KUISTI), returns wall segments as structured JSON.
3. **Facade sub-agents** (4 Gemini vision calls, one per facade) — each receives a cropped facade elevation image + section drawing, returns wall heights, window/door openings, and cladding material types.
4. **Quantity calculation** (pure math) — computes perimeter, gross/net wall areas, and material quantities with waste factors. Validates via perimeter closure check.

### Why This Wins
- **Accuracy**: Dimensions come from the PDF text layer, not LLM OCR. The LLM reasons about spatial relationships, which is what it's good at.
- **Verifiability**: Perimeter closure check (wall segments must form a closed polygon) catches extraction errors automatically.
- **Domain specificity**: Prompts encode Finnish architectural standards — US1/US2 wall types, sokkel height subtraction, window code conventions (10x21 = 1000×2100mm), cladding coverage factors.
- **Decomposition**: Each facade analyzed independently with a focused sub-agent, reducing context noise and error rate vs. one monolithic call.

### Target Users
Construction estimators, architects, and building material suppliers who need quick quantity estimates from standard Finnish ARK drawings.

---

## PERSONA & RULES

You are building a hackathon MVP. You are a senior Python engineer who writes clean, minimal code. You do NOT over-engineer. You do NOT add features not specified. You follow this plan exactly.

### HARD RULES
1. **NO frameworks**: No LangChain, no LangGraph, no CrewAI. Plain Python with functions.
2. **NO unnecessary abstraction**: No class hierarchies, no factory patterns, no abstract base classes. Functions and dicts.
3. **ONE file for the pipeline**: `pipeline.py` — the entire extraction + analysis + calculation pipeline.
4. **ONE file for the UI**: `app.py` — a Streamlit app for upload + results display.
5. **Gemini API only** for vision LLM calls. Use `google-genai` SDK.
6. **Test with the 3 provided PDFs** in `test_data/` before considering anything else.
7. **Every LLM call must have a structured output schema**. Always request JSON. Always validate.
8. **No streaming, no async**. Simple synchronous calls. This is a hackathon.
9. **Print progress** to stdout at every stage so we can debug.

---

## PROJECT STRUCTURE

```
project/
├── CLAUDE.md
├── requirements.txt
├── pipeline.py          # Core extraction + calculation engine
├── app.py               # Streamlit UI
├── prompts.py           # All LLM prompt templates (no prompts in pipeline.py)
├── pdf_utils.py         # PDF text extraction + image rendering helpers
├── calculations.py      # Pure math: perimeter, wall area, cladding quantities
├── test_data/           # The 3 test PDFs go here
│   ├── ARK_02_Pohjakuva_1111__2_.pdf
│   ├── ARK_03_Julkisivut.pdf
│   └── ARK_04_Leikkaus.pdf
└── output/              # Generated results (JSON + HTML report)
```

---

## TECH STACK

```
# requirements.txt
streamlit>=1.30.0
google-genai>=1.0.0
pdfplumber>=0.11.0
PyMuPDF>=1.24.0
Pillow>=10.0.0
jinja2>=3.1.0
```

---

## THE PIPELINE — 4 PHASES

### PHASE 1: PDF Ingestion & Programmatic Text Extraction (NO LLM)

File: `pdf_utils.py`

**Purpose**: Extract all text annotations with their (x, y) coordinates from each PDF page using pdfplumber. Also render each PDF page as a high-DPI PNG using PyMuPDF for the vision LLM.

**Critical implementation details**:

1. **Rotated text reversal bug**: pdfplumber reads rotated dimension annotations backwards. For example, `14472` appears as `27441`, `3077` appears as `7703`, `4159` appears as `9514`, `1800` appears as `0081`. You MUST detect and reverse these. The heuristic: if a numeric string > 3 digits starts with `0` or its reverse is a "rounder" number (ends in `0` or `00`), reverse it. Also cross-check: the same dimension often appears twice in the drawing (top and bottom, or left and right) — one instance reads correctly, the other is reversed.

2. **Dimension extraction**: Find all text matching `^\d{3,5}$` — these are millimeter dimensions. Record text + (x0, top) coordinates.

3. **Elevation markers**: Find all text matching `^[+-]?\d+\.\d{3}$` — these are elevation levels like `+4.015`, `-0.400`. Record text + coordinates.

4. **Room labels**: Find text matching known Finnish room names: `KUISTI`, `OLESKELU`, `KPH`, `WC`, `MH`, `KÄYTÄVÄ`, `VAR`, `ET`, `Huone`, `VARASTO`, `IVK`. Record text + coordinates.

5. **Structure labels**: Find `US1`, `US2`, `YP1`, `AP1`, `VP` — wall/roof/floor type identifiers.

6. **Image rendering**: Use PyMuPDF (`fitz`) to render each page at 200 DPI as PNG. For the facade PDF which has 4 views on one page, also produce 4 cropped images (one per facade quadrant: top-left=West, top-right=North, bottom-left=East, bottom-right=South).

**Function signatures**:
```python
def extract_text_annotations(pdf_path: str) -> dict:
    """Returns {
        'dimensions_mm': [{'value': 14472, 'x': 259.3, 'y': 621.2}, ...],
        'elevations': [{'value': '+4.015', 'x': 235.2, 'y': 304.0}, ...],
        'room_labels': [{'name': 'KUISTI', 'x': 570.6, 'y': 138.7}, ...],
        'structure_labels': [{'name': 'US1', 'x': 1265.0, 'y': 208.9}, ...],
        'page_size': {'width': 3572, 'height': 1264}
    }"""

def render_page_to_image(pdf_path: str, page_num: int = 0, dpi: int = 200) -> bytes:
    """Returns PNG bytes of the full page."""

def render_cropped_region(pdf_path: str, page_num: int, bbox_fraction: tuple, dpi: int = 200) -> bytes:
    """bbox_fraction = (x0_frac, y0_frac, x1_frac, y1_frac) as 0-1 fractions of page.
    Returns PNG bytes of the cropped region."""
```

**Known PDF layout for the test data**:
- `ARK_02_Pohjakuva_1111__2_.pdf`: Page is 3572 × 1264 pts. Left half is the ground floor (POHJA 1:50). Right half has the parvi (loft) plan and a data table.
- `ARK_03_Julkisivut.pdf`: Page is 2381 × 842 pts. 4 facade views arranged in 2×2 grid: top-left = JULKISIVU LÄNTEEN (West), top-right = JULKISIVU POHJOISEEN (North), bottom-left = JULKISIVU ITÄÄN (East), bottom-right = JULKISIVU ETELÄÄN (South). Right side has material legend.
- `ARK_04_Leikkaus.pdf`: Page is 2381 × 842 pts. Left half is the section drawing (LEIKKAUS B-B). Right half has structure specifications and U-value table.

**Facade cropping coordinates** (as fractions of page):
```python
FACADE_CROPS = {
    'west':  (0.00, 0.00, 0.42, 0.50),  # top-left quadrant
    'north': (0.30, 0.00, 0.72, 0.50),  # top-right quadrant
    'east':  (0.00, 0.45, 0.42, 1.00),  # bottom-left quadrant
    'south': (0.30, 0.45, 0.72, 1.00),  # bottom-right quadrant
}
```

---

### PHASE 2: Orchestrator — Building Outline Identification (1 Gemini Call)

File: `pipeline.py`, function `identify_building_outline()`

**Input to the LLM**:
- The full floor plan image (rendered PNG from Phase 1)
- The extracted text annotations from Phase 1 (dimensions + room labels as JSON)

**What we ask the LLM**:
We give it the dimensions already extracted programmatically and ask it to assign them to wall segments of the exterior envelope. We are NOT asking it to OCR numbers — that's already done.

**Critical constraint**: The LLM must distinguish between:
- **Exterior insulated walls (US1)**: These form the heated envelope. Include in perimeter.
- **Porch boundaries (KUISTI)**: Open or uninsulated. EXCLUDE from perimeter.
- **Storage walls (VARASTO/US2)**: May be uninsulated. EXCLUDE from heated perimeter unless attached.

**The prompt must specify**:
- "You are a Finnish architect reading a 1:50 pohjakuva (floor plan)."
- "I've already extracted these dimension annotations from the PDF: [JSON list]"
- "I've already extracted these room labels: [JSON list]"  
- "Identify the exterior wall polygon of the HEATED building envelope (US1 walls only)."
- "EXCLUDE porch areas (KUISTI) from the perimeter."
- "The building is a duplex (two mirrored loma-asunto units A and B)."
- "Return a JSON object with this exact schema:" (see below)

**Expected output schema**:
```json
{
  "building_outline": {
    "description": "Brief description of building shape",
    "total_length_mm": 14472,
    "total_width_mm": 9168,
    "wall_segments": [
      {
        "id": "N1",
        "direction": "north",
        "length_mm": 14472,
        "description": "Full north wall",
        "is_heated_envelope": true,
        "has_porch_in_front": false
      },
      {
        "id": "S1", 
        "direction": "south",
        "length_mm": 14472,
        "description": "Full south wall",
        "is_heated_envelope": true,
        "has_porch_in_front": false
      },
      {
        "id": "E1",
        "direction": "east",
        "length_mm": 9168,
        "description": "East gable wall (apartment A)",
        "is_heated_envelope": true,
        "has_porch_in_front": true
      },
      {
        "id": "W1",
        "direction": "west", 
        "length_mm": 9168,
        "description": "West gable wall (apartment B)",
        "is_heated_envelope": true,
        "has_porch_in_front": true
      }
    ]
  },
  "excluded_areas": [
    {"name": "KUISTI east", "reason": "Open porch, not heated envelope"},
    {"name": "KUISTI west", "reason": "Open porch, not heated envelope"}
  ],
  "perimeter_mm": 47280,
  "confidence_notes": "Any uncertainties or assumptions"
}
```

**Validation after this step**:
- Perimeter closure check: For a rectangular building, 2*(length + width) should equal the reported perimeter. Allow 2% tolerance.
- If it doesn't close, log a warning but continue.

---

### PHASE 3: Sub-Agents — Per-Facade Wall Analysis (4 Gemini Calls)

File: `pipeline.py`, function `analyze_facade()`

For EACH of the 4 facades (North, South, East, West), make one Gemini call with:
- The cropped facade image from Phase 1
- The section drawing image (for height reference)
- The wall segment info from Phase 2

**What we ask each sub-agent**:

"You are a Finnish architect analyzing the [DIRECTION] facade (julkisivu [SUUNTAAN]) of a loma-asunto."

**The prompt must request this exact JSON schema**:
```json
{
  "facade_direction": "north",
  "wall_height_mm": {
    "from_ground_to_eave": 4415,
    "ground_level": -0.400,
    "eave_level": "+4.015",
    "ridge_level": "+6.900",
    "has_gable_triangle": false,
    "gable_triangle_height_mm": 0,
    "notes": "Height measured from maanpinta (-0.400) to räystäs (+4.015)"
  },
  "wall_length_mm": 14472,
  "openings": [
    {
      "type": "window",
      "code": "A-15x5",
      "width_mm": 1500,
      "height_mm": 500,
      "count": 2
    },
    {
      "type": "door",
      "code": "UO 10x21",
      "width_mm": 1000,
      "height_mm": 2100,
      "count": 1
    }
  ],
  "cladding_material": {
    "primary": "VAAKAULKOVERHOUSPANEELI 28x170",
    "secondary": "ULKOVERHOUSPANEELI 21x95",
    "primary_coverage_percent": 70,
    "secondary_coverage_percent": 30
  },
  "gross_wall_area_m2": 0,
  "total_opening_area_m2": 0,
  "net_cladding_area_m2": 0
}
```

**Critical details for the sub-agent prompts**:
- Wall height is from maanpinta (ground level, -0.400m) to räystäs (eave, +4.015m) = 4.415m for the rectangular portion.
- East and West facades have GABLE TRIANGLES above the eave: from +4.015 to ridge +6.900 = 2.885m height. The triangle base equals the building width (9168mm). Triangle area = 0.5 × base × height.
- Window/door codes follow Finnish convention: first number = width in modules of 100mm, second = height in modules of 100mm. So `UO 10x21` = 1000mm × 2100mm. `A-15x5` = 1500mm × 500mm. `A-8x21` = 800mm × 2100mm.
- The sokkel (foundation, from -0.400 to approx -0.020) is concrete, NOT clad with panels. So cladding starts at about -0.020 (or 0.000), not at -0.400. The VISION agent should determine the actual cladding start height from the facade drawing.
- North and South facades are the LONG sides (14472mm). East and West are the SHORT sides / gable ends (9168mm).

**After all 4 calls complete**: Aggregate into a single `facade_results` dict.

---

### PHASE 4: Quantity Takeoff Calculation (NO LLM — Pure Math)

File: `calculations.py`

**Input**: The aggregated facade results from Phase 3.

**Calculations**:

```python
def calculate_quantities(facade_results: list[dict]) -> dict:
    """
    For each facade:
      1. gross_area = wall_length * wall_height_to_eave
         + triangle_area (if gable: 0.5 * wall_length * gable_height)
      2. opening_area = sum(w * h * count for each opening)
      3. net_cladding_area = gross_area - opening_area
      4. Subtract sokkel area: sokkel_height ≈ 380mm (from -0.400 to -0.020)
         sokkel_area = wall_length * 0.380
         net_cladding_area -= sokkel_area
    
    Material calculation:
      VAAKAULKOVERHOUSPANEELI 28x170:
        - Board width 170mm, but with overlap effective coverage ≈ 145mm
        - Running meters per m² ≈ 1000/145 = 6.90 rm/m²
      
      ULKOVERHOUSPANEELI 21x95:
        - Board width 95mm, effective coverage ≈ 80mm  
        - Running meters per m² ≈ 1000/80 = 12.50 rm/m²
      
      Waste factor: 1.12 (12% waste for cuts, corners, damaged boards)
    
    Returns:
      {
        "perimeter_m": float,
        "per_facade": [
          {
            "direction": "north",
            "gross_area_m2": float,
            "opening_area_m2": float,
            "sokkel_area_m2": float,
            "net_cladding_area_m2": float,
          }, ...
        ],
        "totals": {
          "total_gross_wall_area_m2": float,
          "total_opening_area_m2": float,
          "total_sokkel_area_m2": float,
          "total_net_cladding_area_m2": float,
        },
        "materials": {
          "vaakaulkoverhouspaneeli_28x170": {
            "area_m2": float,
            "running_meters": float,
            "running_meters_with_waste": float,
            "board_count_3m": int,
            "board_count_4m": int,
          },
          "ulkoverhouspaneeli_21x95": {
            "area_m2": float,
            "running_meters": float, 
            "running_meters_with_waste": float,
            "board_count_3m": int,
            "board_count_4m": int,
          }
        },
        "validation": {
          "perimeter_closure_check": bool,
          "expected_perimeter_mm": int,
          "calculated_perimeter_mm": int,
          "deviation_percent": float
        }
      }
    """
```

---

## STREAMLIT APP (`app.py`)

### Layout & Flow

The app has 3 states:

**State 1 — Upload**:
- Title: "🏗️ ArchiMeasure — Architectural Cladding Calculator"
- Subtitle: "Upload Finnish ARK drawings to calculate perimeter, wall area, and cladding materials"
- 3 file uploaders (or one multi-file uploader): Floor Plan (Pohjakuva), Facades (Julkisivut), Section (Leikkaus)
- Big "Analyze" button
- The file uploaders should indicate which PDF type is expected

**State 2 — Processing** (shown while pipeline runs):
- Progress bar with 4 stages:
  1. "📄 Extracting text annotations from PDFs..."
  2. "🏠 Identifying building outline..."
  3. "🔍 Analyzing facades (1/4, 2/4, 3/4, 4/4)..."
  4. "📊 Calculating quantities..."
- Show intermediate results as they complete (use `st.status` or `st.expander`)

**State 3 — Results Dashboard**:

Use `st.columns`, `st.metric`, `st.dataframe`, and `st.expander` for a clean layout.

**Top row — 3 big metrics**:
- Heated Perimeter (m)
- Total Net Cladding Area (m²)
- Total Board Running Meters (rm)

**Second row — Per-Facade Breakdown** (use `st.dataframe`):
| Facade | Length (m) | Height (m) | Gross Area (m²) | Openings (m²) | Net Cladding (m²) |
|--------|-----------|------------|-----------------|---------------|-------------------|

**Third row — Material Bill of Quantities**:
| Material | Area (m²) | Running Meters | +12% Waste | Boards (3m) | Boards (4m) |
|----------|----------|---------------|------------|-------------|-------------|

**Fourth row — Expandable Details**:
- Expander: "Building Outline (from LLM)" — show the JSON from Phase 2
- Expander: "Per-Facade Analysis (from LLM)" — show each facade's JSON
- Expander: "Validation Checks" — perimeter closure, confidence notes
- Expander: "Extracted Annotations (from PDF)" — raw text extraction data

**Fifth row — Visual Reference**:
- Show the 3 PDF pages as images side by side using `st.image`

### UI Design Rules
- Use `st.set_page_config(layout="wide")` 
- Use a clean color scheme: dark header area, white cards for metrics
- Format all numbers: mm → m conversion, 2 decimal places, thousand separators
- Show the perimeter closure validation prominently: green checkmark if < 2% deviation, red warning if > 2%

---

## PROMPTS FILE (`prompts.py`)

Store ALL prompt templates as string constants. Every prompt must:
1. Start with the Finnish architect persona
2. Include the extracted text data as context
3. Request response in JSON only — "Respond ONLY with valid JSON. No markdown, no explanation, no preamble."
4. Include the exact JSON schema expected
5. Include Finnish architectural terminology definitions where relevant

**Template variables** use Python `.format()` — no f-strings in templates, no jinja.

---

## GEMINI API USAGE

```python
from google import genai
from google.genai import types
import json, base64

def call_gemini_vision(image_bytes: bytes, prompt: str, additional_images: list[bytes] = None) -> dict:
    """
    Call Gemini with image(s) + text prompt. Return parsed JSON.
    
    - Model: gemini-2.0-flash (fast, cheap, good enough for structured extraction)
    - Temperature: 0.1 (we want deterministic output)
    - Response must be valid JSON
    - Retry up to 2 times on JSON parse failure
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    
    contents = []
    # Add primary image
    contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))
    # Add any additional images
    if additional_images:
        for img in additional_images:
            contents.append(types.Part.from_bytes(data=img, mime_type="image/png"))
    # Add text prompt
    contents.append(types.Part.from_text(text=prompt))
    
    for attempt in range(3):
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            )
        )
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]  
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"  [WARN] JSON parse failed on attempt {attempt+1}, retrying...")
            continue
    
    raise ValueError(f"Failed to get valid JSON from Gemini after 3 attempts. Last response: {text[:500]}")
```

---

## IMPLEMENTATION ORDER

Build and test in this exact order:

1. **`pdf_utils.py`** — Run it standalone on the 3 test PDFs. Print all extracted annotations. Verify the reversed-number fix works. Verify image rendering works.

2. **`prompts.py`** — Write all prompt templates. No testing needed yet.

3. **`pipeline.py`** — Wire Phase 1 → Phase 2 → Phase 3 → Phase 4. Run it as a script with hardcoded paths to test PDFs. Print results to stdout. 
   - Test Phase 2 first (outline identification) — verify it correctly excludes KUISTI.
   - Then test Phase 3 (facade analysis) one facade at a time.
   - Then run full pipeline.

4. **`calculations.py`** — Pure math, test with hardcoded values first, then with real pipeline output.

5. **`app.py`** — Build the Streamlit UI last. The pipeline must work before the UI exists.

---

## EXPECTED RESULTS FOR TEST DATA (USE AS VALIDATION)

Based on the provided PDFs, the expected approximate values are:

- **Building overall dimensions**: 14472mm × 9168mm (these are the outer wall dimensions from the pohjakuva)
- **KUISTI (porch)**: 1800mm deep on each end, but the porch is IN FRONT of the wall — the wall itself extends the full 9168mm width. So the perimeter is the full rectangle.
- **Heated perimeter**: approximately 2 × (14472 + 9168) = 47,280 mm = 47.28 m
- **Wall heights**: 
  - Long walls (N, S): from ground (-0.400) to eave (+4.015) = 4415mm = 4.415m for cladding zone. But sokkel occupies the bottom ~380mm, so cladded height ≈ 4.035m
  - Gable walls (E, W): same rectangular portion + triangle from +4.015 to ridge (+6.900) = 2885mm height, base = 9168mm
- **Rough gross wall area**: 
  - North: 14.472 × 4.035 ≈ 58.4 m²
  - South: 14.472 × 4.035 ≈ 58.4 m²
  - East: 9.168 × 4.035 + 0.5 × 9.168 × 2.885 ≈ 37.0 + 13.2 ≈ 50.2 m²
  - West: same ≈ 50.2 m²
  - Total gross ≈ 217 m²
- **Openings**: Multiple windows and doors to subtract. Expect 15-25 m² total opening area.
- **Net cladding area**: Approximately 190-200 m²

If the pipeline returns numbers wildly different from these, something is wrong.

---

## ERROR HANDLING

- If Gemini returns invalid JSON 3 times: save the raw response to a debug file, show an error in the UI, but don't crash.
- If pdfplumber finds no dimensions: log a warning, still send the image to the LLM (it can still extract visually).
- If a facade analysis fails: continue with the other 3 facades, mark the failed one as "manual review needed."
- Never let the pipeline crash. Always return partial results with clear error indicators.

---

## WHAT NOT TO BUILD

- No user authentication
- No database
- No file history or saved sessions
- No multi-language support (English UI is fine, Finnish technical terms in prompts)
- No PDF generation of results
- No 3D visualization
- No cost estimation (just material quantities)
- No integration with material supplier APIs

---

## ENVIRONMENT

- Python 3.11+
- Set `GEMINI_API_KEY` as environment variable before running
- Run with: `streamlit run app.py`
- For pipeline testing: `python pipeline.py`
