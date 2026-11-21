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
    ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'hasil_semua_foto')
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
        cache=np.load(Path(__file__).resolve().parent/'hasil'/'parameter_kalibrasi.npz')
        cached_files=list(cache['files'])
        if p.name in cached_files:
            corners=cache['image_points'][cached_files.index(p.name)].copy()
            ok=True;method='previous_detection';blur=0
        else:
            seeds=json.loads((Path(__file__).resolve().parent/'batas_papan.json').read_text())
            src=np.float32(seeds[p.name])*np.float32(wh)
            dst=np.float32([[80,80],[720,80],[720,720],[80,720]])
            H=cv.getPerspectiveTransform(src,dst)
            warp=cv.warpPerspective(gray,H,(800,800))
            ok=False;method='rectified_SB'
            if not ok:
                # Border seeds specify only search regions; coordinates below are
                # measured from image corner response, not a synthetic grid.
                response=cv.cornerMinEigenVal(cv.GaussianBlur(warp,(3,3),0),5,3)
                measured=[]
                for gy in range(1,8):
                    for gx in range(1,8):
                        x0,y0=80+gx*80,80+gy*80
                        roi=response[y0-18:y0+19,x0-18:x0+19].copy()
                        yy,xx=np.mgrid[-18:19,-18:19]
                        roi*=np.exp(-(xx**2+yy**2)/(2*16**2))
                        iy,ix=np.unravel_index(np.argmax(roi),roi.shape)
                        if roi[iy,ix]<=0:raise RuntimeError(f'Corner response absent: {p.name}')
                        measured.append([x0-18+ix,y0-18+iy])
                corners=np.float32(measured).reshape(-1,1,2)
                corners=cv.cornerSubPix(warp,corners,(5,5),(-1,-1),(cv.TERM_CRITERIA_EPS+cv.TERM_CRITERIA_MAX_ITER,60,0.001))
                ok=True;method='border_guided_local_corners';blur=3
            if ok:
                corners=cv.perspectiveTransform(corners.reshape(-1,1,2).astype(np.float32),np.linalg.inv(H))
                corners=cv.cornerSubPix(gray,corners,(7,7),(-1,-1),(cv.TERM_CRITERIA_EPS+cv.TERM_CRITERIA_MAX_ITER,60,0.001))
        row['detection_method']=method if ok else ''
        row['detection_blur']=blur if ok else ''
        if ok:
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
