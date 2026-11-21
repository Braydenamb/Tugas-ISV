"""Kalibrasi papan 8x8 kotak (7x7 sudut dalam), tanpa mengubah foto asli."""
from pathlib import Path
import argparse, csv, json
import cv2 as cv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--photos',type=Path,default=Path(__file__).resolve().parent.parent/'Photo')
    ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'hasil')
    ap.add_argument('--square-mm',type=float,default=44.0,help='Sisi petak dalam mm (default: 44 mm = 4,4 cm)')
    args=ap.parse_args()
    if args.square_mm is not None and args.square_mm <= 0: ap.error('Ukuran kotak harus positif')
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    (out/'deteksi').mkdir(exist_ok=True)
    cv.setNumThreads(4)
    pattern=(7,7);unit=args.square_mm or 1.0
    obj=np.zeros((49,3),np.float32);obj[:,:2]=np.mgrid[:7,:7].T.reshape(-1,2)*unit
    objects=[];points=[];accepted=[];status=[];size=None
    for p in sorted(args.photos.rglob('*')):
        if p.suffix.lower() not in {'.jpg','.jpeg','.png'}:continue
        im=cv.imread(str(p));row={'file':p.name,'status':'unreadable'}
        if im is None:status.append(row);continue
        gray=cv.cvtColor(im,cv.COLOR_BGR2GRAY);wh=gray.shape[::-1]
        if size is None:size=wh
        if wh!=size:row['status']='different_resolution';status.append(row);continue
        scale=min(1.,1040/max(wh));small=cv.resize(gray,None,fx=scale,fy=scale,interpolation=cv.INTER_AREA)
        ok=False
        for blur in [0,3,5,7,9,13,17]:
            detection_image=small if blur==0 else cv.GaussianBlur(small,(blur,blur),0)
            ok,corners=cv.findChessboardCornersSB(detection_image,pattern,cv.CALIB_CB_NORMALIZE_IMAGE)
            method='SB'
            if not ok:
                ok,corners=cv.findChessboardCorners(detection_image,pattern,cv.CALIB_CB_ADAPTIVE_THRESH|cv.CALIB_CB_NORMALIZE_IMAGE)
                method='classic'
            if ok:break
        row['detection_method']=method if ok else ''
        row['detection_blur']=blur if ok else '' 
        if ok:
            corners=corners.reshape(-1,1,2).astype(np.float32)
            # Use actual resize ratios, then refine on full-resolution pixels.
            corners[:,:,0]*=wh[0]/small.shape[1];corners[:,:,1]*=wh[1]/small.shape[0]
            corners=cv.cornerSubPix(gray,corners,(7,7),(-1,-1),(cv.TERM_CRITERIA_EPS+cv.TERM_CRITERIA_MAX_ITER,60,0.001))
            objects.append(obj.copy());points.append(corners);accepted.append(p)
            display=im.copy();cv.drawChessboardCorners(display,pattern,corners,True)
            cv.imwrite(str(out/'deteksi'/p.name),cv.resize(display,(780,1040)))
        row['status']='used' if ok else 'corners_not_found';status.append(row)
        print(p.name,row['status'],flush=True)
    with (out/'deteksi.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=['file','status','detection_blur','detection_method']);w.writeheader();w.writerows(status)
    if len(points)<12:raise RuntimeError(f'Hanya {len(points)} foto valid; perlu minimal 12.')
    rms,K,D,rv,tv=cv.calibrateCamera(objects,points,size,None,None)
    rows=[];all_errors=[];residuals=[]
    for p,o,c,r,t in zip(accepted,objects,points,rv,tv):
        proj,_=cv.projectPoints(o,r,t,K,D);delta=(c-proj).reshape(-1,2)
        errors=np.linalg.norm(delta,axis=1);all_errors.extend(errors);residuals.extend(delta)
        rows.append({'file':p.name,'mean_error_px':float(errors.mean()),'rms_error_px':float(np.sqrt(np.mean(errors**2))),'max_error_px':float(errors.max())})
    errs=np.array(all_errors);residuals=np.array(residuals)
    result={'opencv':cv.__version__,'images_total':len(status),'images_used':len(points),'image_size':list(size),'inner_corners':list(pattern),'square_size':unit,'translation_unit':'mm' if args.square_mm else 'square','K':K.tolist(),'distortion_names':['k1','k2','p1','p2','k3'],'distortion':D.ravel().tolist(),'mean_reprojection_error_px':float(errs.mean()),'rms_reprojection_error_px':float(rms),'rms_recomputed_px':float(np.sqrt(np.mean(errs**2))),'per_image':rows}
    (out/'hasil_kalibrasi.json').write_text(json.dumps(result,indent=2))
    np.savez(out/'parameter_kalibrasi.npz',K=K,distortion=D,rvecs=np.array(rv),tvecs=np.array(tv),image_points=np.array(points),object_points=np.array(objects),image_size=np.array(size),files=np.array([p.name for p in accepted]))
    with (out/'error_per_foto.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.size':10,'figure.dpi':140})
    fig,ax=plt.subplots(figsize=(8,4));bars=ax.bar(result['distortion_names'],D.ravel(),color=['#155e75']*2+['#b45309']*2+['#155e75'])
    ax.axhline(0,color='black',lw=.6);ax.bar_label(bars,fmt='%.5f',padding=4);ax.margins(y=.22);ax.set(ylabel='Koefisien (tanpa satuan)',title='Koefisien distorsi: model 5 parameter');fig.tight_layout();fig.savefig(out/'koefisien_distorsi.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4));ax.bar(range(len(rows)),[r['mean_error_px'] for r in rows],color='#155e75');ax.axhline(errs.mean(),color='#b45309',label=f'Mean global = {errs.mean():.4f} px');ax.set_xticks(range(len(rows)),[p.stem.split('WA')[-1] for p in accepted],rotation=90);ax.set(xlabel='Nomor akhir nama foto (WA)',ylabel='Mean jarak reproyeksi (px)',title='Error setiap foto');ax.legend();fig.tight_layout();fig.savefig(out/'error_per_foto.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(6,5));ax.scatter(residuals[:,0],residuals[:,1],s=5,alpha=.4);ax.axhline(0,color='black',lw=.5);ax.axvline(0,color='black',lw=.5);ax.set(xlabel='Residual u (px)',ylabel='Residual v (px)',title='Residual deteksi - proyeksi');ax.set_aspect('equal',adjustable='datalim');fig.tight_layout();fig.savefig(out/'residual.png');plt.close(fig)
    # Example from median-error view, same K and output extent for direct comparison.
    med=np.argsort([r['mean_error_px'] for r in rows])[len(rows)//2];im=cv.imread(str(accepted[med]));fixed=cv.undistort(im,K,D,None,K)
    a=cv.resize(im,(585,780));b=cv.resize(fixed,(585,780));comparison=np.hstack((a,b));cv.imwrite(str(out/'sebelum_sesudah.jpg'),comparison)
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
