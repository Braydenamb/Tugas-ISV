"""Image-based remeasurement of all corners; homography only locates search regions."""
from pathlib import Path
import cv2 as cv
import numpy as np

def remeasure(gray, old):
    grid=np.mgrid[:7,:7].T.reshape(-1,2).astype(np.float32)
    # Robust homography gives initialization only; all 49 observations stay in fit.
    H,mask=cv.findHomography(grid,old.reshape(-1,2),cv.RANSAC,8.0,maxIters=5000,confidence=.999)
    if H is None:raise ValueError('Homography initialization failed')
    W=np.array([[100.,0,200],[0,100.,200],[0,0,1.]])
    M=W@np.linalg.inv(H)
    warp=cv.warpPerspective(gray,M,(1000,1000),flags=cv.INTER_LINEAR)
    sm=cv.GaussianBlur(warp,(7,7),1.5)
    response=cv.cornerMinEigenVal(sm,7,3)
    measured=[];diagnostics=[]
    for j,(gx,gy) in enumerate(grid):
        x0,y0=int(200+100*gx),int(200+100*gy)
        radius=24
        roi=response[y0-radius:y0+radius+1,x0-radius:x0+radius+1].copy()
        yy,xx=np.mgrid[-radius:radius+1,-radius:radius+1]
        score=roi*np.exp(-(xx**2+yy**2)/(2*18**2))
        iy,ix=np.unravel_index(np.argmax(score),score.shape)
        if ix in (0,2*radius) or iy in (0,2*radius):
            raise ValueError(f'Corner {j} peak on search boundary; inspect manually')
        if roi[iy,ix] <= 0:raise ValueError(f'Corner {j} no response')
        measured.append([x0-radius+ix,y0-radius+iy])
        diagnostics.append([float(roi[iy,ix]),int(ix-radius),int(iy-radius)])
    peaks=np.float32(measured).reshape(-1,1,2)
    sub=cv.cornerSubPix(warp,peaks.copy(),(5,5),(-1,-1),(cv.TERM_CRITERIA_EPS+cv.TERM_CRITERIA_MAX_ITER,60,.001))
    if np.max(np.linalg.norm(sub-peaks,axis=2))>8:
        raise ValueError('Subpixel refinement drifted more than 8 rectified pixels')
    pts=cv.perspectiveTransform(sub,np.linalg.inv(M)).astype(np.float32)
    ref=cv.cornerSubPix(gray,pts.copy(),(5,5),(-1,-1),(cv.TERM_CRITERIA_EPS+cv.TERM_CRITERIA_MAX_ITER,60,.001))
    # Reject large drift to an unrelated texture feature; keep image-measured warp corner.
    drift=np.linalg.norm((ref-pts).reshape(-1,2),axis=1)
    use=drift<=4
    pts[use]=ref[use]
    return pts, {'homography_inliers':int(mask.sum()),'original_refinement_drift_px':drift.tolist(),'original_refinement_used':use.tolist(),'local_response_offsets':diagnostics}
