"""Scan complet du template Orange Black And White."""
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

TPL = r'C:\Users\ALPHEE COLOMBE\Downloads\Orange Black And White Modern Construction Company.pptx'
prs = Presentation(TPL)

print(f"SLIDES: {len(prs.slides)}")
print(f"LAYOUTS: {len(prs.slide_layouts)}")
for name_idx, lay in enumerate(prs.slide_layouts):
    print(f"  Layout {name_idx}: '{lay.name}'")

print()
for si, sl in enumerate(prs.slides):
    print(f"\n{'='*60}")
    print(f"SLIDE {si+1}")
    for sh in sl.shapes:
        print(f"  shape_id={sh.shape_id} name='{sh.name}' type={sh.shape_type}")
        if hasattr(sh, 'text_frame'):
            try:
                for pi, para in enumerate(sh.text_frame.paragraphs):
                    txt = para.text.strip()
                    if txt:
                        # Get font info from first run
                        fonts = []
                        for run in para.runs:
                            f = run.font
                            size = f.size
                            bold = f.bold
                            try:
                                col = str(f.color.rgb) if f.color and f.color.type else 'inherited'
                            except:
                                col = 'inherited'
                            fonts.append(f"size={int(size.pt) if size else '?'}pt bold={bold} color={col} font={f.name}")
                        print(f"    para[{pi}]: '{txt[:60]}' | {'; '.join(fonts[:1])}")
            except Exception as e:
                print(f"    [err: {e}]")
        if hasattr(sh, 'fill'):
            try:
                fill = sh.fill
                if fill.type is not None:
                    fg = fill.fore_color
                    try:
                        print(f"    fill_color={fg.rgb}")
                    except:
                        pass
            except:
                pass
