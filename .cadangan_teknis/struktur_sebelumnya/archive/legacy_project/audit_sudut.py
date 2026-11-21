from pathlib import Path
import cv2 as cv,numpy as np,csv
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent;out=root/'audit_sudut';out.mkdir(exist_ok=True)
z=np.load(root/'hasil_semua_foto/parameter_kalibrasi.npz')
photos={p.name:p for p in (root.parent/'Photo').rglob('*.jpg')}
rows=[]
for i,(name,o,p,r,t) in enumerate(zip(z['files'],z['object_points'],z['image_points'],z['rvecs'],z['tvecs'])):
 proj,_=cv.projectPoints(o,r,t,z['K'],z['distortion']);dist=np.linalg.norm((p-proj).reshape(-1,2),axis=1)
 for j,e in enumerate(dist):
  rows.append(dict(file=str(name),index=j,row=j//7+1,col=j%7+1,error_px=float(e),u=float(p[j,0,0]),v=float(p[j,0,1]),projected_u=float(proj[j,0,0]),projected_v=float(proj[j,0,1])))
rows.sort(key=lambda x:-x['error_px'])
with (out/'residual_awal_per_titik.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for page in range(3):
 canvas=Image.new('RGB',(880,1440),'white');d=ImageDraw.Draw(canvas)
 for k,a in enumerate(rows[page*24:(page+1)*24]):
  im=Image.open(photos[a['file']]);x,y=round(a['u']),round(a['v']);box=(x-100,y-100,x+100,y+100);crop=im.crop(box)
  cd=ImageDraw.Draw(crop);cd.line((93,100,107,100),fill='red',width=2);cd.line((100,93,100,107),fill='red',width=2)
  px,py=a['projected_u']-box[0],a['projected_v']-box[1];cd.ellipse((px-5,py-5,px+5,py+5),outline='cyan',width=2)
  xx=k%4*220;yy=k//4*240;canvas.paste(crop,(xx,yy));d.text((xx,yy+201),f"{a['file'].split('WA')[-1]} r{a['row']}c{a['col']}\ne={a['error_px']:.1f}px i={a['index']}",fill='black')
 canvas.save(out/f'periksa_awal_{page+1}.png')
print([(a['file'][-8:],a['index'],round(a['error_px'],1)) for a in rows[:24]])
