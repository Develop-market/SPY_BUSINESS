from pptx import Presentation
from pptx.dml.color import RGBColor
import os

files = [
    r'C:\Users\ALPHEE COLOMBE\Downloads\Red and White Modern Project Proposal Presentation.pptx',
    r'C:\Users\ALPHEE COLOMBE\Downloads\Orange Black And White Modern Construction Company.pptx',
    r'C:\Users\ALPHEE COLOMBE\Downloads\Orange And White Modern Professional Financial Report Presentation.pptx',
    r'C:\Users\ALPHEE COLOMBE\Downloads\Blue White and Gray Modern Financial Report Presentation.pptx',
]

for f in files:
    prs = Presentation(f)
    print(f'=== {os.path.basename(f)} ===')
    print(f'  Slides: {len(prs.slides)} | Layouts: {len(prs.slide_layouts)}')
    print(f'  Size: {prs.slide_width.inches:.1f} x {prs.slide_height.inches:.1f} in')
    for i, sl in enumerate(prs.slides):
        if i >= 4:
            break
        print(f'  Slide {i+1}:')
        for sh in sl.shapes:
            if hasattr(sh, 'text_frame'):
                try:
                    txt = sh.text_frame.text.strip()[:80]
                    if txt:
                        print(f'    shape="{sh.name}" text="{txt}"')
                except Exception:
                    pass
    print()
