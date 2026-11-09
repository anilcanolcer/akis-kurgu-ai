"""Generate PNG and Windows icon from the original Akış vector design."""
from pathlib import Path
from PIL import Image, ImageDraw
p=Path(__file__).resolve().parent
scale=4
im=Image.new('RGBA',(256*scale,256*scale))
d=ImageDraw.Draw(im)
def points(seq): return [(int(x*scale),int(y*scale)) for x,y in seq]
d.rounded_rectangle((7*scale,7*scale,249*scale,249*scale),radius=70*scale,fill='#141321',outline='#6451aa',width=3*scale)
d.polygon(points([(49,186),(108,65),(142,65),(207,186),(172,186),(125,98),(83,186)]),fill='#8062f4')
d.line(points([(97,159),(157,132)]),fill='#f9f6ff',width=15*scale)
for x,y in [(97,159),(157,132)]:
 r=7.5*scale; d.ellipse((x*scale-r,y*scale-r,x*scale+r,y*scale+r),fill='#f9f6ff')
d.ellipse((172*scale,70*scale,186*scale,84*scale),fill='#e9dcff')
im=im.resize((256,256),Image.Resampling.LANCZOS)
im.save(p/'logo.png')
im.save(p/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
