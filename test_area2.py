from pdf_utils import extract_text_annotations, compute_wall_height, compute_building_dimensions

here = 'here'

def print_house(name, fp_pdf, s_pdf, j_pdf):
    fp = extract_text_annotations(f'{here}/{fp_pdf}')
    s = extract_text_annotations(f'{here}/{s_pdf}')
    j = extract_text_annotations(f'{here}/{j_pdf}')

    dims = compute_building_dimensions(fp)
    heights = compute_wall_height(s, j)

    p_mm = dims['total_perimeter_mm']
    h_mm = heights['wall_height_mm']
    w_mm = dims['total_width_mm']
    g_mm = heights['gable_height_mm']
    
    # 2 long walls + 2 short walls = perimeter * wall_height
    rect_area = (p_mm / 1000) * (h_mm / 1000)
    
    # 2 gable triangles (assuming standard pitched roof on the width axis)
    tri_area = 2 * (0.5 * (w_mm / 1000) * (g_mm / 1000))
    
    total_area = rect_area + tri_area
    
    print(f'=== {name} ===')
    print(f'Total Perimeter: {p_mm} mm ({p_mm/1000:.2f} m)')
    print(f'Wall Height: {h_mm} mm ({h_mm/1000:.2f} m)')
    print(f'Total Width: {w_mm} mm ({w_mm/1000:.2f} m)')
    print(f'Gable Height: {g_mm} mm ({g_mm/1000:.2f} m)')
    print(f'Calculated Rectangular Wall Area: {rect_area:.2f} m²')
    print(f'Calculated Gable Triangle Area: {tri_area:.2f} m²')
    print(f'TOTAL Outer Wall Area (gross): {total_area:.2f} m²')
    print()

print_house('HOUSE 1 (Original)', 'ARK 02 Pohjakuva 1111 (2).pdf', 'ARK 04 Leikkaus.pdf', 'ARK 03 Julkisivut.pdf')
print_house('HOUSE 2 (New)', 'ARK 02 Pohjakuva_A_1602.pdf', 'ARK 04 Leikkaus_A_2609.pdf', 'ARK 03 Julkisivut_A_2609.pdf')
