import os
import json
from pipeline import run_pipeline

base_dir = os.path.dirname(__file__)
here_dir = os.path.join(base_dir, 'here')

houses = [
    {
        "name": "House 1 (Original)",
        "floor": "ARK 02 Pohjakuva 1111 (2).pdf",
        "facade": "ARK 03 Julkisivut.pdf",
        "section": "ARK 04 Leikkaus.pdf"
    },
    {
        "name": "House 2 (House A)",
        "floor": "ARK 02 Pohjakuva_A_1602.pdf",
        "facade": "ARK 03 Julkisivut_A_2609.pdf",
        "section": "ARK 04 Leikkaus_A_2609.pdf"
    },
    {
        "name": "House 3 (House B)",
        "floor": "ARK 02 Pohjakuva Talo B 8_12.pdf",
        "facade": "ARK 03 Julkisivut Talo B 22_12.pdf",
        "section": "ARK 04 Leikkaus Talo B 8_12.pdf"
    }
]

def main():
    os.makedirs('output', exist_ok=True)
    summary_results = []

    for house in houses:
        print(f"\n{'='*60}")
        print(f"🚀 Running Pipeline on: {house['name']}")
        print(f"{'='*60}")
        
        try:
            fp_path = os.path.join(here_dir, house['floor'])
            fa_path = os.path.join(here_dir, house['facade'])
            se_path = os.path.join(here_dir, house['section'])
            
            result = run_pipeline(fp_path, fa_path, se_path)
            
            q = result['quantities']
            summary_results.append({
                "house": house['name'],
                "status": "SUCCESS",
                "perimeter_m": q['perimeter_m'],
                "exterior_wall_surface_area_m2": q['exterior_wall_surface_area_m2'],
                "net_cladding_area_m2": q['totals']['total_net_cladding_area_m2']
            })
            
            # Save individual result json
            out_file = f"output/result_{house['name'].replace(' ', '_')}.json"
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"❌ Failed processing {house['name']}: {e}")
            summary_results.append({
                "house": house['name'],
                "status": "FAILED",
                "error": str(e)
            })

    print(f"\n\n{'='*60}")
    print("📊 BATCH SUMMARY")
    print(f"{'='*60}")
    for res in summary_results:
        print(f"▶ {res['house']}: {res['status']}")
        if res['status'] == 'SUCCESS':
            print(f"   Perimeter:     {res['perimeter_m']} m")
            print(f"   Total Wall:    {res['exterior_wall_surface_area_m2']} m²")
            print(f"   Net Cladding:  {res['net_cladding_area_m2']} m²")
        else:
            print(f"   Error: {res.get('error')}")

if __name__ == "__main__":
    main()
