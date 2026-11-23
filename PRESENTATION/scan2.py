"""Scan COMPLET de toutes les slides du template."""
from pptx import Presentation

TPL = r'C:\Users\ALPHEE COLOMBE\Downloads\Orange Black And White Modern Construction Company.pptx'
prs = Presentation(TPL)

for si, sl in enumerate(prs.slides):
    print(f"\n{'='*55}")
    print(f"SLIDE {si+1}")
    for sh in sl.shapes:
        if hasattr(sh, 'text_frame'):
            try:
                t = sh.text_frame.text.strip()
                if t:
                    print(f"  {sh.name}: '{t[:70]}'")
            except:
                pass
