import math

# Material coverage constants
VAAKA_EFFECTIVE_COVERAGE_MM = 145   # 28x170 panel with overlap
ULKO_EFFECTIVE_COVERAGE_MM = 80     # 21x95 panel with overlap

VAAKA_RM_PER_M2 = 1000 / VAAKA_EFFECTIVE_COVERAGE_MM  # ~6.90
ULKO_RM_PER_M2 = 1000 / ULKO_EFFECTIVE_COVERAGE_MM    # 12.50

WASTE_FACTOR = 1.12

SOKKEL_HEIGHT_MM = 380  # concrete foundation from ~-0.400 to ~-0.020, not clad


def calculate_quantities(facade_results: list, total_perimeter_mm: float,
                         heated_perimeter_mm: float = 0,
                         wall_height_mm: float = 0) -> dict:
    """
    Compute exterior wall metrics, cladding areas, and material quantities.

    facade_results:      list of dicts from Phase 3 (one per facade direction)
    total_perimeter_mm:  total exterior wall perimeter (all walls including porches/storage)
    heated_perimeter_mm: heated envelope perimeter only (optional)
    wall_height_mm:      programmatic wall height from elevation markers (datum to eave)
    """
    per_facade = []

    for f in facade_results:
        direction = f.get('facade_direction', 'unknown')
        wall_h = f.get('wall_height_mm', {})
        height_mm = wall_h.get('from_ground_to_eave') or wall_height_mm
        length_mm = f.get('wall_length_mm') or 0

        # Rectangular wall area (from +-0.000 to eave)
        rect_area_m2 = (length_mm / 1000) * (height_mm / 1000)

        # Gable triangle area (east/west only)
        triangle_area_m2 = 0.0
        if wall_h.get('has_gable_triangle') and wall_h.get('gable_triangle_height_mm', 0) > 0:
            tri_h_mm = wall_h['gable_triangle_height_mm']
            triangle_area_m2 = 0.5 * (length_mm / 1000) * (tri_h_mm / 1000)

        gross_area_m2 = rect_area_m2 + triangle_area_m2

        # Opening area
        opening_area_m2 = sum(
            (o['width_mm'] / 1000) * (o['height_mm'] / 1000) * o.get('count', 1)
            for o in f.get('openings', [])
        )

        # Sokkel deduction: concrete foundation strip at the base (not clad)
        sokkel_area_m2 = (length_mm / 1000) * (SOKKEL_HEIGHT_MM / 1000)

        # Net cladding = gross minus openings minus sokkel
        net_cladding_area_m2 = max(0.0, gross_area_m2 - opening_area_m2 - sokkel_area_m2)

        per_facade.append({
            'direction': direction,
            'wall_length_mm': length_mm,
            'wall_height_mm': height_mm,
            'has_gable_triangle': wall_h.get('has_gable_triangle', False),
            'gross_area_m2': round(gross_area_m2, 2),
            'triangle_area_m2': round(triangle_area_m2, 2),
            'opening_area_m2': round(opening_area_m2, 2),
            'sokkel_area_m2': round(sokkel_area_m2, 2),
            'net_cladding_area_m2': round(net_cladding_area_m2, 2),
            'openings': f.get('openings', []),
        })

    total_gross = sum(f['gross_area_m2'] for f in per_facade)
    total_openings = sum(f['opening_area_m2'] for f in per_facade)
    total_sokkel = sum(f['sokkel_area_m2'] for f in per_facade)
    total_net = sum(f['net_cladding_area_m2'] for f in per_facade)

    # Exterior wall surface area = total perimeter × wall height (no deductions)
    perimeter_m = total_perimeter_mm / 1000
    # Prefer average of dynamically matched facade heights, fallback to programmatic overall height
    avg_facade_h = sum(f['wall_height_mm'] for f in per_facade) / max(len(per_facade), 1)
    wall_height_m = (avg_facade_h if avg_facade_h > 0 else wall_height_mm) / 1000
    exterior_wall_surface_area_m2 = round(perimeter_m * wall_height_m, 2)

    # Material split — per-facade, using each facade's own cladding percentages
    vaaka_area = 0.0
    ulko_area = 0.0
    for f_result, f_calc in zip(facade_results, per_facade):
        cm = f_result.get('cladding_material', {})
        p_pct = (cm.get('primary_coverage_percent', 70)) / 100
        s_pct = (cm.get('secondary_coverage_percent', 30)) / 100
        net = f_calc['net_cladding_area_m2']
        vaaka_area += net * p_pct
        ulko_area += net * s_pct

    vaaka_rm = vaaka_area * VAAKA_RM_PER_M2
    ulko_rm = ulko_area * ULKO_RM_PER_M2

    vaaka_rm_waste = vaaka_rm * WASTE_FACTOR
    ulko_rm_waste = ulko_rm * WASTE_FACTOR

    vaaka_boards_3m = math.ceil(vaaka_rm_waste / 3)
    vaaka_boards_4m = math.ceil(vaaka_rm_waste / 4)
    ulko_boards_3m = math.ceil(ulko_rm_waste / 3)
    ulko_boards_4m = math.ceil(ulko_rm_waste / 4)

    # Perimeter validation
    wall_lengths_sum = sum(f['wall_length_mm'] for f in per_facade)
    expected = total_perimeter_mm
    deviation = abs(wall_lengths_sum - expected) / expected * 100 if expected > 0 else 0.0

    return {
        'perimeter_m': round(perimeter_m, 2),
        'heated_perimeter_m': round(heated_perimeter_mm / 1000, 2) if heated_perimeter_mm else 0,
        'exterior_wall_surface_area_m2': exterior_wall_surface_area_m2,
        'per_facade': per_facade,
        'totals': {
            'total_gross_wall_area_m2': round(total_gross, 2),
            'total_opening_area_m2': round(total_openings, 2),
            'total_sokkel_area_m2': round(total_sokkel, 2),
            'total_net_cladding_area_m2': round(total_net, 2),
        },
        'materials': {
            'vaakaulkoverhouspaneeli_28x170': {
                'area_m2': round(vaaka_area, 2),
                'running_meters': round(vaaka_rm, 1),
                'running_meters_with_waste': round(vaaka_rm_waste, 1),
                'board_count_3m': vaaka_boards_3m,
                'board_count_4m': vaaka_boards_4m,
            },
            'ulkoverhouspaneeli_21x95': {
                'area_m2': round(ulko_area, 2),
                'running_meters': round(ulko_rm, 1),
                'running_meters_with_waste': round(ulko_rm_waste, 1),
                'board_count_3m': ulko_boards_3m,
                'board_count_4m': ulko_boards_4m,
            },
        },
        'validation': {
            'perimeter_closure_check': deviation <= 2.0,
            'expected_perimeter_mm': int(expected),
            'calculated_perimeter_mm': int(wall_lengths_sum),
            'deviation_percent': round(deviation, 2),
        },
    }


if __name__ == "__main__":
    # Quick sanity test with corrected expected values
    test_facades = [
        {
            'facade_direction': 'north',
            'wall_height_mm': {'from_ground_to_eave': 4015, 'has_gable_triangle': False, 'gable_triangle_height_mm': 0},
            'wall_length_mm': 14472,
            'openings': [
                {'type': 'window', 'code': 'A-15x5', 'width_mm': 1500, 'height_mm': 500, 'count': 2},
            ],
            'cladding_material': {'primary_coverage_percent': 70, 'secondary_coverage_percent': 30},
        },
        {
            'facade_direction': 'south',
            'wall_height_mm': {'from_ground_to_eave': 4015, 'has_gable_triangle': False, 'gable_triangle_height_mm': 0},
            'wall_length_mm': 14472,
            'openings': [
                {'type': 'door', 'code': 'UO 10x21', 'width_mm': 1000, 'height_mm': 2100, 'count': 2},
                {'type': 'window', 'code': 'A-8x21', 'width_mm': 800, 'height_mm': 2100, 'count': 4},
            ],
            'cladding_material': {'primary_coverage_percent': 70, 'secondary_coverage_percent': 30},
        },
        {
            'facade_direction': 'east',
            'wall_height_mm': {'from_ground_to_eave': 4015, 'has_gable_triangle': True, 'gable_triangle_height_mm': 2885},
            'wall_length_mm': 9168,
            'openings': [],
            'cladding_material': {'primary_coverage_percent': 70, 'secondary_coverage_percent': 30},
        },
        {
            'facade_direction': 'west',
            'wall_height_mm': {'from_ground_to_eave': 4015, 'has_gable_triangle': True, 'gable_triangle_height_mm': 2885},
            'wall_length_mm': 9168,
            'openings': [],
            'cladding_material': {'primary_coverage_percent': 70, 'secondary_coverage_percent': 30},
        },
    ]

    import json
    result = calculate_quantities(test_facades, total_perimeter_mm=59430, heated_perimeter_mm=47280, wall_height_mm=4015)
    print(json.dumps(result, indent=2))
    print(f"\nExterior wall perimeter: {result['perimeter_m']} m (expected 59.43)")
    print(f"Exterior wall surface area: {result['exterior_wall_surface_area_m2']} m2 (expected ~238.53)")
