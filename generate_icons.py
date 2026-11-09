"""Generate distributable icon sizes from the original Akış mark."""
from pathlib import Path
from PIL import Image, ImageDraw

assets = Path(__file__).resolve().parent
assets.mkdir(exist_ok=True)
scale = 4
image = Image.new('RGBA', (256 * scale, 256 * scale))
draw = ImageDraw.Draw(image)
def points(values):
    return [(int(x * scale), int(y * scale)) for x, y in values]
draw.rounded_rectangle((8*scale, 8*scale, 248*scale, 248*scale), radius=68*scale, fill='#7357f5')
draw.polygon(points([(57,185),(115,64),(140,64),(199,185),(165,185),(128,106),(91,185)]), fill='white')
draw.line(points([(99,158),(156,135)]), fill='#d8ccff', width=17*scale)
for x, y in [(99,158),(156,135)]:
    r = 8.5*scale
    draw.ellipse((x*scale-r,y*scale-r,x*scale+r,y*scale+r), fill='#d8ccff')
image = image.resize((256,256), Image.Resampling.LANCZOS)
image.save(assets / 'logo.png')
image.save(assets / 'app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
