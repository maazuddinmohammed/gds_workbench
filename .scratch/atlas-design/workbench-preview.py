"""Static design artifact only; synthetic values; no workspace or runtime access."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import textwrap

S = 2
W, H = 1440, 920
image = Image.new('RGB', (W*S, H*S), '#eceeea')
draw = ImageDraw.Draw(image)
regular = '/System/Library/Fonts/Helvetica.ttc'
mono = '/System/Library/Fonts/SFNSMono.ttf'
ink, muted, line, accent = '#24312e', '#69746f', '#dfe5df', '#a15338'

def rect(box, fill, radius=0, outline=None):
    box = tuple(int(v*S) for v in box)
    if radius:
        draw.rounded_rectangle(box, radius*S, fill, outline, width=S)
    else:
        draw.rectangle(box, fill, outline, width=S)

def text(x, y, value, size=14, color=ink, bold=False, fixed=False):
    font = ImageFont.truetype(mono if fixed else regular, round(size*S), index=1 if bold and not fixed else 0)
    draw.text((x*S, y*S), value, font=font, fill=color)

def button(x, y, width, label, primary=False):
    rect((x,y,x+width,y+36), accent if primary else '#fbfcfa', 7, None if primary else line)
    text(x+13,y+10,label,13,'#ffffff' if primary else ink,True)

def rule(x1,y,x2):
    draw.line((x1*S,y*S,x2*S,y*S),fill=line,width=S)

text(28,22,'atlas / workbench',16,ink,True)
text(1050,24,'STATIC DESIGN  ·  SYNTHETIC DATA',11,muted)
shadow=Image.new('RGBA',image.size,(0,0,0,0))
sd=ImageDraw.Draw(shadow)
sd.rounded_rectangle((24*S,72*S,1416*S,888*S),18*S,fill=(37,48,40,34))
image=Image.alpha_composite(image.convert('RGBA'),shadow.filter(ImageFilter.GaussianBlur(12*S))).convert('RGB')
draw=ImageDraw.Draw(image)
rect((24,64,1416,888),'#fdfefb',16)
rect((25,65,1415,127),'#f5f8f3',15)
text(45,79,'atlas',28,ink,True)
text(139,90,'Workbench',15,muted)
text(320,80,'Northwind  /  Sales',16,ink,True)
text(320,104,'SQL Essential  ·  dev',12,muted)
button(935,79,140,'Reload local files')
button(1084,79,138,'Validate locally')
button(1231,79,162,'Generate DBML')
rule(24,128,1416)
text(47,148,'Metadata',14,muted)
text(159,148,'Model',14,accent,True)
text(245,148,'Validation results',14,muted)
rect((156,174,204,177),accent)
text(1161,150,'Model snapshot · revision 12',12,muted)
rule(24,178,1416)
rect((25,179,207,851),'#f6f8f4')
text(44,203,'MODEL DATA',11,muted,True)
for y,label in [(240,'Input scope'),(286,'Profiling'),(332,'Analysis'),(378,'Conceptual'),(434,'Logical entities')]:
    text(44,y,label,14,muted)
rect((34,472,198,512),'#eee5dd',7)
text(45,484,'Logical attributes',14,accent,True)
text(44,535,'Relationships',14,muted)
rule(42,581,190)
for y,label in [(607,'Bindings'),(653,'Mapping'),(699,'Code'),(745,'Validation checks')]:
    text(44,y,label,14,muted)
draw.line((208*S,178*S,208*S,852*S),fill=line,width=S)
text(237,203,'Logical attributes',28,ink,True)
text(239,246,'Customer  ·  Review the proposed local records',14,muted)
rect((237,280,532,324),'#eef1eb',8)
text(253,294,'Snapshot  24',13,muted)
rect((381,284,528,320),'#ffffff',6,line)
text(395,294,'Change Set  3',13,accent,True)
button(824,284,147,'Add record')
button(238,347,172,'Entity: Customer')
button(850,347,120,'Columns')
rect((237,404,971,442),'#f5f7f2',0)
for x,label in [(263,'Attribute'),(502,'Data type'),(602,'Nullable'),(696,'Key role'),(820,'Local change')]:
    text(x,416,label,12,muted,True)
rule(237,442,971)
records=[('CustomerName','STRING','Yes','None','Changed'),('Email','STRING','Yes','None','Added'),('CustomerCode','STRING','No','Natural','Changed')]
for i,row in enumerate(records):
    y=443+i*66
    rect((237,y,971,y+65),'#fbf2e9' if i==0 else '#ffffff')
    if i==0: rect((237,y,240,y+65),accent)
    rect((250,y+23,263,y+36),'#ffffff',3,'#aeb9b0')
    text(277,y+23,row[0],15,ink,True)
    text(502,y+24,row[1],13,muted,False,True)
    text(602,y+23,row[2],14)
    text(696,y+23,row[3],14)
    text(820,y+23,row[4],13,accent)
    text(951,y+19,'›',22,muted)
    rule(237,y+65,971)
text(239,664,'3 complete records',12,muted)
text(717,664,'Downloaded Snapshot stays unchanged.',12,muted)
text(239,742,'Local changes',14,ink,True)
text(239,768,'Review values here, then acknowledge the batch with your agent.',13,muted)
draw.line((997*S,178*S,997*S,852*S),fill=line,width=S)
rect((998,179,1415,851),'#fafbf8')
text(1025,204,'RECORD DETAILS',11,muted,True)
text(1375,199,'×',23,muted)
text(1025,239,'CustomerName',24,ink,True)
text(1025,274,'Customer  ·  STRING  ·  Unlocked',13,muted)
rect((1025,309,1110,337),'#efe4d9',5)
text(1037,317,'Changed',12,accent,True)
text(1120,317,'1 field updated',12,muted)
rule(1025,366,1387)
text(1025,389,'Description',16,ink,True)
text(1025,427,'SNAPSHOT',11,muted,True)
text(1025,452,'Customer name.',15,muted)
text(1025,498,'PROPOSED',11,accent,True)
rect((1024,521,1387,634),'#f2eee6',7)
for i,part in enumerate(textwrap.wrap('Name used to identify the customer in correspondence and customer-facing documents.',37)):
    text(1039,538+i*24,part,15)
text(1025,663,'Null and empty values stay distinct.',12,muted)
button(1025,754,138,'Edit draft',True)
text(1026,809,'Saved locally · not submitted',12,muted)
rule(24,852,1416)
text(44,865,'sales-workspace',12,muted)
text(1183,865,'Local workspace  ·  Model',12,muted)
out=Path('atlas/atlas-plugin/docs/assets/workbench-table-preview.png')
out.parent.mkdir(parents=True,exist_ok=True)
image.save(out)
print(out.resolve())
