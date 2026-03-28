import os, tempfile

# Load .env before importing pipeline (which needs GEMINI_API_KEY)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

import streamlit as st
import tempfile
import os
import json
import pandas as pd

st.set_page_config(
    page_title="ArchiMeasure",
    page_icon="🏗️",
    layout="wide",
)

st.markdown("""
<style>
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 2rem 2.5rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    color: white;
}
.main-header h1 { margin: 0 0 0.4rem 0; font-size: 2rem; }
.main-header p  { margin: 0; opacity: 0.8; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
  <h1>🏗️ ArchiMeasure</h1>
  <p>Upload Finnish ARK drawings to calculate perimeter, wall area, and cladding material quantities.</p>
</div>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def save_upload(uploaded_file, path: str):
    with open(path, "wb") as f:
        f.write(uploaded_file.read())
    uploaded_file.seek(0)  # reset so we can read again for display


def run_analysis(floor_plan_file, facades_file, section_file) -> dict:
    from pipeline import run_pipeline

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    def progress_callback(stage, msg):
        stage_pcts = {1: 0.10, 2: 0.35, 4: 0.95}
        if stage == 3:
            # Extract "n/4" from message like "Analyzing facades (2/4): south..."
            try:
                part = msg.split("(")[1].split(")")[0]
                n = int(part.split("/")[0])
                pct = 0.35 + (n / 4) * 0.55
            except Exception:
                pct = 0.50
        else:
            pct = stage_pcts.get(stage, 0.0)
        progress_bar.progress(min(pct, 1.0))
        status_text.text(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        fp_path = os.path.join(tmpdir, "floor_plan.pdf")
        fa_path = os.path.join(tmpdir, "facades.pdf")
        se_path = os.path.join(tmpdir, "section.pdf")

        save_upload(floor_plan_file, fp_path)
        save_upload(facades_file, fa_path)
        save_upload(section_file, se_path)

        result = run_pipeline(fp_path, fa_path, se_path, progress_callback=progress_callback)

    progress_bar.progress(1.0)
    status_text.text("✅ Analysis complete!")
    return result


# ── Results display ────────────────────────────────────────────────────────────

def show_results(result: dict):
    q = result['quantities']
    totals = q['totals']
    mats = q['materials']
    val = q['validation']
    per_facade = q['per_facade']

    # Top metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("📐 Exterior Wall Perimeter", f"{q['perimeter_m']:.2f} m")
    c2.metric("🧱 Exterior Wall Surface Area", f"{q['exterior_wall_surface_area_m2']:.2f} m²")
    vaaka = mats['vaakaulkoverhouspaneeli_28x170']
    ulko  = mats['ulkoverhouspaneeli_21x95']
    total_rm = vaaka['running_meters_with_waste'] + ulko['running_meters_with_waste']
    c3.metric("📏 Total Running Meters (incl. waste)", f"{total_rm:.1f} rm")

    # Secondary metrics
    sc1, sc2 = st.columns(2)
    sc1.metric("🏠 Heated Perimeter", f"{q.get('heated_perimeter_m', 0):.2f} m")
    sc2.metric("🪵 Net Cladding Area", f"{totals['total_net_cladding_area_m2']:.2f} m²")

    # Perimeter closure validation
    if val['perimeter_closure_check']:
        st.success(
            f"✅ Perimeter closure OK — {val['deviation_percent']:.1f}% deviation "
            f"({val['calculated_perimeter_mm']:,}mm vs expected {val['expected_perimeter_mm']:,}mm)"
        )
    else:
        st.warning(
            f"⚠️ Perimeter closure: {val['deviation_percent']:.1f}% deviation "
            f"({val['calculated_perimeter_mm']:,}mm vs expected {val['expected_perimeter_mm']:,}mm) — manual review recommended"
        )

    st.divider()

    # Per-facade breakdown
    st.subheader("Per-Facade Breakdown")
    facade_rows = [
        {
            'Facade': f['direction'].capitalize(),
            'Length (m)': f"{f['wall_length_mm'] / 1000:.3f}",
            'Height (m)': f"{f['wall_height_mm'] / 1000:.3f}",
            'Gross Area (m²)': f"{f['gross_area_m2']:.2f}",
            'Gable Triangle (m²)': f"{f.get('triangle_area_m2', 0):.2f}",
            'Openings (m²)': f"{f['opening_area_m2']:.2f}",
            'Sokkel (m²)': f"{f.get('sokkel_area_m2', 0):.2f}",
            'Net Cladding (m²)': f"{f['net_cladding_area_m2']:.2f}",
        }
        for f in per_facade
    ]
    st.dataframe(pd.DataFrame(facade_rows), use_container_width=True, hide_index=True)

    st.divider()

    # Material bill of quantities
    st.subheader("Material Bill of Quantities")
    mat_rows = []
    for key, label in [
        ('vaakaulkoverhouspaneeli_28x170', 'VAAKAULKOVERHOUSPANEELI 28×170'),
        ('ulkoverhouspaneeli_21x95',       'ULKOVERHOUSPANEELI 21×95'),
    ]:
        m = mats[key]
        mat_rows.append({
            'Material': label,
            'Area (m²)': f"{m['area_m2']:.2f}",
            'Running Meters': f"{m['running_meters']:.1f}",
            '+12% Waste (rm)': f"{m['running_meters_with_waste']:.1f}",
            'Boards @ 3 m': m['board_count_3m'],
            'Boards @ 4 m': m['board_count_4m'],
        })
    st.dataframe(pd.DataFrame(mat_rows), use_container_width=True, hide_index=True)

    st.divider()

    # Expandable details
    st.subheader("Details")

    with st.expander("Building Outline (from LLM)"):
        st.json(result['building_outline'])

    with st.expander("Per-Facade Analysis (from LLM)"):
        for f in result['facade_results']:
            direction = f.get('facade_direction', '?').capitalize()
            if f.get('manual_review_needed'):
                st.warning(f"⚠️ {direction}: analysis failed — used fallback values")
            else:
                st.write(f"**{direction} facade**")
            st.json(f)

    with st.expander("Validation Checks"):
        st.json(val)
        notes = result['building_outline'].get('confidence_notes', '')
        if notes:
            st.write(f"**LLM confidence notes:** {notes}")

    with st.expander("Extracted Annotations (from PDFs)"):
        for pdf_name, ann in result['annotations'].items():
            st.write(f"**{pdf_name}**")
            st.json(ann)

    st.divider()

    # Visual reference — re-render from stored session files if available
    st.subheader("Visual Reference")
    if 'uploaded_images' in st.session_state:
        imgs = st.session_state['uploaded_images']
        cols = st.columns(3)
        labels = ['Floor Plan (Pohjakuva)', 'Facades (Julkisivut)', 'Section (Leikkaus)']
        for col, (label, img_bytes) in zip(cols, zip(labels, imgs)):
            with col:
                st.caption(label)
                st.image(img_bytes, use_container_width=True)
    else:
        st.info("Visual reference not available (images were rendered during analysis).")


# ── Main ───────────────────────────────────────────────────────────────────────

if 'result' not in st.session_state:
    # Upload state
    st.subheader("Upload Drawings")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.caption("📐 Floor Plan — Pohjakuva (ARK 02)")
        floor_plan_file = st.file_uploader(
            "floor_plan", type=["pdf"], label_visibility="collapsed", key="fp"
        )
        if floor_plan_file:
            st.success(f"✓ {floor_plan_file.name}")

    with c2:
        st.caption("🏠 Facade Elevations — Julkisivut (ARK 03)")
        facades_file = st.file_uploader(
            "facades", type=["pdf"], label_visibility="collapsed", key="fa"
        )
        if facades_file:
            st.success(f"✓ {facades_file.name}")

    with c3:
        st.caption("✂️ Section Drawing — Leikkaus (ARK 04)")
        section_file = st.file_uploader(
            "section", type=["pdf"], label_visibility="collapsed", key="se"
        )
        if section_file:
            st.success(f"✓ {section_file.name}")

    st.divider()
    all_uploaded = floor_plan_file and facades_file and section_file

    if not all_uploaded:
        st.info("Upload all 3 PDF files to enable analysis.")

    if st.button("🔍 Analyze", disabled=not all_uploaded, type="primary", use_container_width=True):
        # Capture preview images before analysis consumes the file objects
        from pdf_utils import render_page_to_image
        import tempfile, os
        try:
            preview_imgs = []
            for uf in [floor_plan_file, facades_file, section_file]:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(uf.read())
                    tmp_path = tmp.name
                uf.seek(0)
                preview_imgs.append(render_page_to_image(tmp_path, dpi=72))
                os.unlink(tmp_path)
            st.session_state['uploaded_images'] = preview_imgs
        except Exception:
            pass  # preview is optional

        try:
            result = run_analysis(floor_plan_file, facades_file, section_file)
            st.session_state['result'] = result
            st.rerun()
        except Exception as e:
            st.error(f"Pipeline error: {e}")
            st.exception(e)

else:
    # Results state
    if st.button("← New Analysis"):
        for key in ('result', 'uploaded_images'):
            st.session_state.pop(key, None)
        st.rerun()

    show_results(st.session_state['result'])
