from pdf_utils import extract_text_annotations, compute_wall_height, compute_building_dimensions
from calculations import calculate_facade_area, calculate_total_climate_envelope

here = 'here'

def print_house(name, fp_pdf, s_pdf, j_pdf):
    fp = extract_text_annotations(f'{here}/{fp_pdf}')
    s = extract_text_annotations(f'{here}/{s_pdf}')
    j = extract_text_annotations(f'{here}/{j_pdf}')

    dims = compute_building_dimensions(fp)
    heights = compute_wall_height(s, j)

    # Calculate facade area
    wall = calculate_facade_area(
        dims['total_perimeter_mm'],
        heights['wall_height_mm'],
        dims['total_width_mm'],
        heights['gable_height_mm']
    )
    
    print(f'=== {name} ===')
    print(f'Total Perimeter: {dims["total_perimeter_mm"]} mm ({dims["total_perimeter_mm"]/1000:.2f} m)')
    print(f'Heated Perimeter: {dims["heated_perimeter_mm"]} mm ({dims["heated_perimeter_mm"]/1000:.2f} m)')
    print(f'Wall Height: {heights["wall_height_mm"]} mm ({heights["wall_height_mm"]/1000:.2f} m)')
    print(f'Total Width: {dims["total_width_mm"]} mm ({dims["total_width_mm"]/1000:.2f} m)')
    print(f'Gable Height: {heights["gable_height_mm"]} mm ({heights["gable_height_mm"]/1000:.2f} m)')
    print(f'Total Outer Wall Area (including gables & doors/windows): {wall["total_gross_area_m2"]:.2f} m2')
    print(f'Net Outer Wall Area (excluding assumed doors/windows): {wall["total_net_area_m2"]:.2f} m2')
    print()

print_house('HOUSE 1 (Original)', 'ARK 02 Pohjakuva 1111 (2).pdf', 'ARK 04 Leikkaus.pdf', 'ARK 03 Julkisivut.pdf')
print_house('HOUSE 2 (New)', 'ARK 02 Pohjakuva_A_1602.pdf', 'ARK 04 Leikkaus_A_2609.pdf', 'ARK 03 Julkisivut_A_2609.pdf')

