# ArchiMeasure

### PDF Architectural Drawings &rarr; Cladding Material Quantities in 60 Seconds

<br>

> **Hackathon Result &mdash; House B (Test Run)**
>
> | Metric | Value |
> |---|---|
> | **Perimeter** | `49.84 m` |
> | **Total Wall Area** | `227.38 m2` |
> | **Net Cladding** | `262.13 m2` |
>
> *3 PDFs in, full bill of quantities out. No manual measurement.*

<br>

---

## What It Does

ArchiMeasure reads **standard Finnish architectural PDFs** (floor plan, facade elevations, cross-section) and automatically calculates exterior cladding material quantities &mdash; replacing 1-3 hours of manual takeoff with a single button click.

```
 3 Finnish ARK PDFs
        |
        v
 +--------------+     +---------------+     +----------------+     +------------------+
 | Phase 1      | --> | Phase 2       | --> | Phase 3        | --> | Phase 4          |
 | PDF Text     |     | Building      |     | Facade         |     | Quantity         |
 | Extraction   |     | Outline       |     | Analysis       |     | Calculation      |
 | (pdfplumber) |     | (Gemini x1)   |     | (Gemini x4)    |     | (pure math)      |
 +--------------+     +---------------+     +----------------+     +------------------+
        |                    |                      |                       |
   dimensions,          wall segments,         heights, openings,     areas, running
   elevations,          perimeters             cladding splits        meters, boards
   room labels
```

---

## The Pipeline

### Phase 1 &mdash; PDF Text Extraction (No LLM)

Extracts machine-readable text from PDFs with `pdfplumber`. Zero hallucination risk.

```
PDF Text Layer
    |
    +-- Dimensions:  regex /^\d{3,5}$/     -->  [14472, 9168, 1800, ...]  (mm)
    +-- Elevations:  regex /^[+-]?\d+\.\d{3}$/  -->  [+4.015, -0.400, +6.800, ...]
    +-- Room labels: KUISTI, OLESKELU, WC, KPH, VARASTO, ...
    +-- Structure:   US1 (ext. wall), US2, YP1 (roof), AP1, VP
```

**Rotated text fix** &mdash; Finnish PDFs rotate dimensions 180deg. `pdfplumber` reads them backwards:

```
  PDF text    "27441"  -->  reversed  -->  14472 mm  (correct)
  PDF text    "0081"   -->  reversed  -->  1800 mm   (correct)
```

Heuristics: reverse if starts with `0`, or has more trailing zeros reversed, or `val > 7000` and reversed is in plausible room range (1000-6000 mm).

**Dimension chains** &mdash; groups co-linear dimensions by spatial position and sums them:

```
  Left chain (vertical):    3600 + 1800 + 3600 + ... = total_length
  Top chain (horizontal):   4584 + 4584             = total_width
  Perimeter = 2 x (length + width)
```

**Elevation detection** &mdash; frequency analysis to find the true eave level:

```
  All elevation markers:  -0.400, +0.000, +4.015, +4.015, +6.800, ...
                                            ^^^^^ most frequent > 1m = eave
  Wall height = eave - datum = 4.015 - 0.000 = 4015 mm
  Gable height = ridge - eave = 6.800 - 4.015 = 2785 mm
```

---

### Phase 2 &mdash; Building Outline Identification (1 Gemini Call)

Sends the floor plan image + pre-extracted annotations to Gemini 2.5 Flash. The LLM does spatial reasoning (which walls form the exterior envelope), NOT OCR.

```
                    N
            +-------+-------+
            |               |
            |   Unit A      |    14472 mm
         W  |               |  E
            |   Unit B      |
            |               |
            +-------+-------+
                    S
                 9168 mm

  Perimeter = 2 x (14472 + 9168) = 47,280 mm
```

**Validation** &mdash; perimeter closure check:

```
  |calculated_perimeter - expected_perimeter|
  ------------------------------------------ x 100  <=  2%
            expected_perimeter
```

---

### Phase 3 &mdash; Per-Facade Analysis (4 Gemini Calls)

One cropped facade image per direction. Each call extracts:

```
  +============================================+  <-- ridge (+6.800)
  |\                                          /|
  | \          gable triangle               /  |
  |  \       (East/West only)             /    |
  |   +----------------------------------+     |  <-- eave (+4.015)
  |   |     [win]   [win]   [door]       |     |
  |   |                                  |     |   wall_height
  |   |     [win]            [win]       |     |   (ground to eave)
  |   +----------------------------------+     |  <-- ground (+/-0.000)
  |   |//////// sokkel (380mm) //////////|     |  <-- datum (-0.400)
  +---+----------------------------------+-----+
                  wall_length
```

**Window/door codes** (Finnish convention):

```
  UO 10x21  -->  ulko-ovi (ext. door)  1000 x 2100 mm
  A-15x5    -->  ikkuna (window)       1500 x  500 mm
  A-8x21    -->  ikkuna (window)        800 x 2100 mm
```

**Cladding split** per facade (LLM identifies from drawing):

```
  Primary:   VAAKAULKOVERHOUSPANEELI 28x170  (horizontal boards)  ~70-90%
  Secondary: ULKOVERHOUSPANEELI 21x95        (vertical boards)    ~10-30%
```

---

### Phase 4 &mdash; Quantity Calculation (Pure Math)

No LLM. Deterministic formulas only.

---

#### Per-Facade Area Formulas

**Rectangular wall area:**

```
                        wall_length (mm)        wall_height (mm)
  A_rect  =  ──────────────────────  x  ──────────────────────      [m2]
                        1000                       1000
```

**Gable triangle area** (East/West facades only):

```
                    1       wall_length (mm)       gable_height (mm)
  A_triangle  =  ───  x  ──────────────────  x  ────────────────────    [m2]
                    2           1000                    1000
```

**Gross wall area:**

```
  A_gross  =  A_rect  +  A_triangle
```

**Opening area** (sum of all windows + doors):

```
                     n
  A_openings  =  SUM    ( width_i / 1000 ) x ( height_i / 1000 ) x count_i     [m2]
                    i=1
```

**Sokkel deduction** (concrete foundation, not clad):

```
                    wall_length (mm)       380
  A_sokkel  =  ──────────────────────  x  ─────     [m2]
                       1000               1000
```

**Net cladding area:**

```
  A_net  =  max( 0,  A_gross  -  A_openings  -  A_sokkel )
```

---

#### Material Quantity Formulas

Two panel types with different effective coverage due to board overlap:

```
  Panel Type                      Nominal   Overlap   Effective    rm/m2
  ──────────────────────────────  ───────   ───────   ─────────   ──────
  VAAKAULKOVERHOUSPANEELI 28x170   170mm     25mm      145mm      6.90
  ULKOVERHOUSPANEELI 21x95          95mm     15mm       80mm     12.50
```

**Running meters per m2:**

```
                   1000
  rm_per_m2  =  ─────────────────
                effective_coverage
```

**Per-facade material split:**

```
  A_primary    =  A_net  x  ( primary_coverage_%  / 100 )
  A_secondary  =  A_net  x  ( secondary_coverage_%  / 100 )
```

**Running meters (aggregated across all facades):**

```
  RM_vaaka  =  ( SUM  A_primary_i )  x  6.90
  RM_ulko   =  ( SUM  A_secondary_i )  x  12.50
```

**Waste factor** (12% for cuts, corners, damaged boards):

```
  RM_with_waste  =  RM  x  1.12
```

**Board count:**

```
  boards_3m  =  ceil( RM_with_waste / 3.0 )
  boards_4m  =  ceil( RM_with_waste / 4.0 )
```

---

#### Validation

```
  Perimeter closure error:

             | SUM(wall_lengths) - expected_perimeter |
  error%  =  ──────────────────────────────────────────  x  100
                        expected_perimeter

  PASS if error% <= 2.0
```

---

## Complete Data Flow

```
  +----------------------------------------------------------+
  |               3 PDF FILES (INPUT)                        |
  |  Pohjakuva (floor plan) + Julkisivut (facades)           |
  |  + Leikkaus (section)                                    |
  +---------------------------+------------------------------+
                              |
                              v
  +---------------------------------------------------------+
  |  PHASE 1: Programmatic Extraction         [pdf_utils.py] |
  |                                                          |
  |  pdfplumber --> dimensions (mm) with (x,y) coords       |
  |             --> elevation markers (+4.015, -0.400, ...)  |
  |             --> room labels (KUISTI, WC, KPH, ...)       |
  |             --> structure labels (US1, US2, YP1, ...)    |
  |                                                          |
  |  PyMuPDF ----> full page PNGs (200 DPI)                  |
  |            --> 4 cropped facade PNGs (N/S/E/W quadrants) |
  |                                                          |
  |  Compute:  dimension chains --> total_length, total_width|
  |            elevation freq   --> wall_height, gable_height|
  +--------------------------+------------------------------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
      Annotations + Dims              Images (PNGs)
              |                             |
              +-------------+---------------+
                            |
                            v
  +---------------------------------------------------------+
  |  PHASE 2: Building Outline              [pipeline.py]    |
  |           1 Gemini 2.5 Flash call                        |
  |                                                          |
  |  Input:  floor plan PNG + extracted annotations JSON     |
  |  Output: wall_segments[], perimeters, confidence_notes   |
  |                                                          |
  |  The LLM does spatial reasoning, NOT OCR.                |
  |  Dimensions are already extracted -- zero hallucination. |
  +--------------------------+------------------------------+
                             |
                             v
                     Wall Segments
                    + Perimeters
                             |
          +------------------+------------------+
          |         |         |                 |
          v         v         v                 v
        North     South     East              West
        facade    facade    facade            facade
          |         |         |                 |
          v         v         v                 v
  +---------------------------------------------------------+
  |  PHASE 3: Facade Analysis               [pipeline.py]    |
  |           4 Gemini calls (one per direction)             |
  |                                                          |
  |  Each call receives:                                     |
  |    - cropped facade PNG                                  |
  |    - section drawing PNG (height reference)              |
  |    - wall segment info from Phase 2                      |
  |                                                          |
  |  Each call returns:                                      |
  |    - wall_height_mm (ground to eave)                     |
  |    - gable_triangle_height_mm (if gable end)             |
  |    - openings[] (windows, doors with codes + dims)       |
  |    - cladding_material split (primary/secondary %)       |
  +--------------------------+------------------------------+
                             |
                             v
                    Facade Results
                    (per direction)
                             |
                             v
  +---------------------------------------------------------+
  |  PHASE 4: Quantity Calculation        [calculations.py]  |
  |           Pure math, no LLM                              |
  |                                                          |
  |  Per facade:                                             |
  |    A_gross = length x height + 0.5 x base x gable_h     |
  |    A_net   = A_gross - A_openings - A_sokkel             |
  |                                                          |
  |  Materials:                                              |
  |    RM = area x (1000 / effective_coverage)               |
  |    RM_waste = RM x 1.12                                  |
  |    boards = ceil(RM_waste / board_length)                |
  |                                                          |
  |  Validation:                                             |
  |    perimeter closure check (<= 2% deviation)             |
  +--------------------------+------------------------------+
                             |
                             v
  +---------------------------------------------------------+
  |                   RESULTS JSON                           |
  |                                                          |
  |  {                                                       |
  |    perimeter_m, heated_perimeter_m,                      |
  |    exterior_wall_surface_area_m2,                        |
  |    per_facade: [ {direction, gross, openings, net} x4 ], |
  |    materials: { vaaka: {rm, boards}, ulko: {rm, boards}},|
  |    validation: { closure_check, deviation% }             |
  |  }                                                       |
  +--------------------------+------------------------------+
                             |
                             v
  +---------------------------------------------------------+
  |  STREAMLIT UI                              [app.py]      |
  |                                                          |
  |  Upload 3 PDFs --> Progress bar --> Results dashboard    |
  |                                                          |
  |  Metrics | Per-facade table | Material BoQ | Validation  |
  +---------------------------------------------------------+
```

---

## Example Output

For a typical Finnish duplex holiday home (loma-asunto):

```
  BUILDING GEOMETRY
  ─────────────────────────────────────────────────────
  Total length:        14,472 mm
  Total width:          9,168 mm
  Wall height (eave):   4,015 mm
  Gable height:         2,785 mm
  Perimeter:           47,280 mm  =  47.28 m

  PER-FACADE BREAKDOWN
  ─────────────────────────────────────────────────────
  Direction  Length    Height   Gross    Openings  Sokkel   Net
             (mm)     (mm)     (m2)     (m2)      (m2)     (m2)
  ─────────  ───────  ───────  ───────  ────────  ───────  ───────
  North       9168     4015     49.58     6.63      3.48    39.47
  South       9168     4015     47.28    10.92      3.48    32.88
  East       14472     3915     73.92     2.85      5.52    65.55
  West       14472     4015     74.64     2.85      5.52    66.27
  ─────────  ───────  ───────  ───────  ────────  ───────  ───────
  TOTAL                        245.42    23.25     18.00   204.17

  MATERIAL BILL OF QUANTITIES
  ─────────────────────────────────────────────────────
  Material                        Area     RM      +12%     3m boards   4m boards
  ──────────────────────────────  ──────  ──────  ───────  ──────────  ──────────
  Vaakaulkoverhouspaneeli 28x170  199.95  1379.0  1544.5      515         387
  Ulkoverhouspaneeli 21x95         22.22   277.7   311.0      104          78

  VALIDATION
  ─────────────────────────────────────────────────────
  Perimeter closure: PASS (0.0% deviation)
```

---

## Architecture

```
  app.py  ──────────>  pipeline.py  ──────────>  calculations.py
  (Streamlit UI)       (orchestrator)            (pure math)
       |                    |
       |                    +------>  prompts.py
       |                    |        (LLM prompt templates)
       |                    |
       +------>  pdf_utils.py
                 (text extraction + image rendering)
```

| File | Purpose | LLM Calls |
|---|---|---|
| `pdf_utils.py` | PDF text extraction, dimension chains, elevation detection, image rendering | 0 |
| `prompts.py` | All Gemini prompt templates with Finnish architectural terminology | 0 |
| `pipeline.py` | 4-phase orchestrator: extraction &rarr; outline &rarr; facades &rarr; quantities | 5 (1 + 4) |
| `calculations.py` | Per-facade areas, material splits, running meters, board counts, validation | 0 |
| `app.py` | Streamlit upload &rarr; progress &rarr; results dashboard | 0 |

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Vision LLM | Google Gemini 2.5 Flash |
| PDF text extraction | pdfplumber |
| PDF image rendering | PyMuPDF (fitz) |
| Web UI | Streamlit |
| API client | google-genai SDK |

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Gemini API key
export GEMINI_API_KEY="your-key-here"

# Run the web app
streamlit run app.py

# Or run the pipeline directly
python pipeline.py
```

---

## Key Design Decisions

**Hybrid approach** &mdash; Dimensions come from the PDF text layer (deterministic), not LLM vision (probabilistic). The LLM only does spatial reasoning: which walls are exterior, which openings belong where.

**Decomposed facade analysis** &mdash; One focused LLM call per facade direction instead of one monolithic call. Reduces context noise, improves accuracy, enables independent retry on failure.

**Belt-and-suspenders validation** &mdash; Programmatic dimensions override LLM outputs when they conflict. Perimeter closure check catches extraction errors automatically.

**Finnish domain encoding** &mdash; Prompts contain Finnish architectural standards (US1/US2 wall types, sokkel heights, window code conventions, cladding coverage factors) so the LLM reasons within the correct domain.
