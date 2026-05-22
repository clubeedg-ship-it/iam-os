#!/usr/bin/env python3
"""IAM LiDAR Tracker v2.2 — Exact zoals het origineel"""
import sys,os,json,time,math,struct,socket,threading,argparse
import numpy as np
try:import cv2
except:print("pip install opencv-python");sys.exit(1)
try:from pyrplidar import PyRPlidar;HP=True
except:HP=False
try:import serial,serial.tools.list_ports
except:pass
try:from pythonosc import osc_bundle_builder as OB,osc_message_builder as OM,udp_client;HO=True
except:HO=False

# Config
DIST_MIN=200;DIST_MAX=6000;CL_TOL=100;TR_TOL=150;BL_TH=150;MIN_CL=8;MAX_CL=300
TUIO_H='127.0.0.1';TUIO_P=3333
CAL_FILE='calibration.json'

# TUIO sender
class Tuio:
    def __init__(s):
        s.seq=0;s.c=udp_client.SimpleUDPClient(TUIO_H,TUIO_P)if HO else None
    def send(s,cur):
        s.seq+=1
        if not s.c:return
        b=OB.OscBundleBuilder(OB.IMMEDIATELY)
        a=OM.OscMessageBuilder('/tuio/2Dcur');a.add_arg('alive')
        for c in cur:a.add_arg(int(c['id']))
        b.add_content(a.build())
        for c in cur:
            m=OM.OscMessageBuilder('/tuio/2Dcur')
            for v in['set',int(c['id']),float(c['x']),float(c['y']),0.0,0.0,0.0]:m.add_arg(v)
            b.add_content(m.build())
        f=OM.OscMessageBuilder('/tuio/2Dcur');f.add_arg('fseq');f.add_arg(int(s.seq));b.add_content(f.build())
        try:s.c.send(b.build())
        except:pass

# Touch detector — exact zoals origineel
class Detect:
    def __init__(s):
        s.bl=s.bla=s.mat=None;s.prev=[];s.nid=1
    def set_bl(s,sc):
        a,d=[],[]
        for q,ang,dist in sc:
            if DIST_MIN<dist<DIST_MAX:a.append(ang);d.append(dist)
        if len(a)<10:return False
        s.bla=np.array(a);s.bl=np.array(d);return True
    def set_cal(s,src_pts):
        """Perspective transform zoals origineel: src→scherm, dan flipH+flipV.
        Equivalent aan dst=[(1,1),(0,1),(1,0),(0,0)]"""
        if len(src_pts)!=4:return False
        src=np.float32(src_pts)
        dst=np.float32([[1,1],[0,1],[1,0],[0,0]])  # = origineel dst + flipHV
        s.mat=cv2.getPerspectiveTransform(src,dst)
        return True
    def detect(s,sc):
        if s.bl is None or not sc:return[]
        pts=[]
        for q,a,d in sc:
            if not(DIST_MIN<d<DIST_MAX):continue
            i=np.argmin(np.abs(s.bla-a))
            if s.bl[i]-d>BL_TH:
                r=math.radians(a);pts.append((d*math.cos(r),d*math.sin(r)))
        if not pts:s.prev=[];return[]
        # Cluster
        u=[False]*len(pts);cls=[]
        for i in range(len(pts)):
            if u[i]:continue
            c=[pts[i]];u[i]=True;q=[i]
            while q:
                ci=q.pop(0)
                for j in range(len(pts)):
                    if not u[j]and math.hypot(pts[j][0]-pts[ci][0],pts[j][1]-pts[ci][1])<=CL_TOL:
                        u[j]=True;c.append(pts[j]);q.append(j)
            cls.append(c)
        # Centroids + transform
        ts=[]
        for c in cls:
            if not(MIN_CL<=len(c)<=MAX_CL):continue
            rx=sum(p[0]for p in c)/len(c);ry=sum(p[1]for p in c)/len(c)
            if s.mat is not None:
                t=cv2.perspectiveTransform(np.float32([[[rx,ry]]]),s.mat)
                nx,ny=float(t[0][0][0]),float(t[0][0][1])
            else:
                nx,ny=0.5,0.5
            ts.append({'x':max(0,min(1,nx)),'y':max(0,min(1,ny)),'rx':rx,'ry':ry,'sz':len(c)})
        # Track
        if not s.prev:
            for t in ts:t['id']=s.nid;s.nid+=1
        else:
            used=set()
            for t in ts:
                bi,bd=None,float('inf')
                for p in s.prev:
                    if p['id']in used:continue
                    d=math.hypot(t['rx']-p['rx'],t['ry']-p['ry'])
                    if d<bd and d<TR_TOL:bd=d;bi=p['id']
                if bi:t['id']=bi;used.add(bi)
                else:t['id']=s.nid;s.nid+=1
        s.prev=ts;return ts

# Scanner
class Scanner:
    def __init__(s):s.li=None;s.ok=s.run=False;s.sd=[];s.lk=threading.Lock();s.th=None;s.bd=0;s.port=''
    def _fl(s):
        try:sr=s.li.lidar_serial._serial;sr.reset_input_buffer();sr.reset_output_buffer()
        except:pass
    def connect(s,port):
        s.port=port
        for bd in[1000000,256000,115200]:
            print(f"[LiDAR] {port}@{bd}...")
            try:
                s.li=PyRPlidar();s.li.connect(port,bd,timeout=3);s._fl()
                try:s.li.stop();time.sleep(0.1);s._fl();s.li.reset();time.sleep(1.5);s._fl()
                except:pass
                try:print(f"[LiDAR] {s.li.get_info()}")
                except:pass
                s.ok=True;s.bd=bd;print(f"[LiDAR] ✓ {bd}");return True
            except Exception as e:
                print(f"  {e}")
                try:s.li.disconnect()
                except:pass
        return False
    def start(s):
        if s.ok:s.run=True;s.th=threading.Thread(target=s._loop,daemon=True);s.th.start()
    def _loop(s):
        while s.run:
            try:
                s._fl()
                try:s.li.stop();time.sleep(0.2);s._fl()
                except:pass
                sg=None;typ=None
                try:typ=s.li.get_scan_mode_typical()
                except:pass
                for m in([typ]if typ is not None else[])+[0,1,2,3]:
                    try:
                        s._fl();s.li.stop();time.sleep(0.1);s._fl()
                        gf=s.li.start_scan_express(m);tg=gf();ok=0
                        for k,mm in enumerate(tg):
                            try:float(mm.angle);float(mm.distance);ok+=1
                            except:pass
                            if k>100 or ok>=50:break
                        if ok>=30:
                            s.li.stop();time.sleep(0.1);s._fl()
                            sg=s.li.start_scan_express(m);print(f"[LiDAR] Mode {m} ✓");break
                    except:pass
                if not sg:
                    try:s._fl();sg=s.li.start_scan()
                    except:raise Exception("Geen mode")
                g=sg();buf=[];t0=time.time();first=True
                for mm in g:
                    if not s.run:return
                    try:
                        a,d=float(mm.angle),float(mm.distance)
                        if d>0:buf.append((15,a,d))
                    except:continue
                    if time.time()-t0>=0.1 and buf:
                        with s.lk:s.sd=list(buf)
                        if first:print(f"[LiDAR] ✓ {len(buf)} pt/scan");first=False
                        buf=[];t0=time.time()
            except Exception as e:
                print(f"[LiDAR] {e}");time.sleep(2)
                try:s.li.stop();s.li.disconnect();time.sleep(1)
                except:pass
                try:s.li=PyRPlidar();s.li.connect(s.port,s.bd,timeout=3);s._fl();s.li.reset();time.sleep(1.5);s._fl()
                except:time.sleep(3)
    def get(s):
        with s.lk:return list(s.sd)
    def stop(s):
        s.run=False
        try:s.li.stop();s.li.set_motor_pwm(0);s.li.disconnect()
        except:pass

class Sim:
    def __init__(s):s.t=0
    def connect(s,p):return True
    def start(s):pass
    def get(s):
        s.t+=0.033;d=[]
        for i in range(360):
            a=float(i)
            if 90<=a<=270:d.append((15,a,2000+20*math.sin(a*0.1)))
        ta=180+40*math.sin(s.t*0.8);td=1200+200*math.sin(s.t*1.5)
        for da in range(-5,6):d.append((15,ta+da*0.5,td+da*3))
        return d
    def stop(s):pass

def load_presets():
    """Laad alle kalibratie-presets uit calibration.json."""
    if not os.path.exists(CAL_FILE):
        print(f"[Kal] {CAL_FILE} niet gevonden!");return{}
    try:
        with open(CAL_FILE)as f:data=json.load(f)
        # Ons formaat (src/dst)?
        if 'src' in data:
            return {'default':data['src']}
        # Origineel formaat (presets)?
        presets={}
        for name,pts in data.items():
            if isinstance(pts,list)and len(pts)==4:
                presets[name]=pts
        print(f"[Kal] {len(presets)} presets: {', '.join(presets.keys())}")
        return presets
    except Exception as e:
        print(f"[Kal] Fout: {e}");return{}

class App:
    def __init__(s,sc):
        s.sc=sc;s.det=Detect();s.tuio=Tuio()
        s.W,s.H=1200,800;s.cx,s.cy=600,400;s.sc2=s.H/10000;s.fps=0;s.dbg=0
        s.abt=time.time();s.abd=False
        # Presets laden
        s.presets=load_presets()
        s.preset_names=list(s.presets.keys())
        s.preset_idx=0
        # Zoek actief preset uit settings
        if os.path.exists('settings.json'):
            try:
                with open('settings.json')as f:active=json.load(f).get('calibrationPreset','')
                if active in s.presets:s.preset_idx=s.preset_names.index(active)
            except:pass
        if s.preset_names:
            s._apply_preset()
        else:
            print("[Kal] Geen presets — gebruik origineel LidarTracker om te kalibreren")

    def _apply_preset(s):
        name=s.preset_names[s.preset_idx]
        pts=s.presets[name]
        if s.det.set_cal(pts):
            print(f"  ✓ Preset: '{name}' actief")
        else:
            print(f"  ✗ Preset '{name}' ongeldig")
        s.dbg=0  # Reset debug output

    def on_mouse(s,ev,x,y,fl,p):
        if ev!=cv2.EVENT_LBUTTONDOWN:return
        if 65<=y<=95:
            if 12<=x<=142:s._bl()        # Baseline
            elif 152<=x<=342:s._next()    # Preset
        # Geen kalibratie via muisklikken meer — dat werkt niet goed
        # Gebruik het originele LidarTracker.exe om te kalibreren

    def _bl(s):
        sc=s.sc.get()
        if sc and s.det.set_bl(sc):print(f"  ✓ Baseline: {len(s.det.bl)} pt")
        else:print("  ✗ Geen data")

    def _next(s):
        if not s.preset_names:print("  Geen presets");return
        s.preset_idx=(s.preset_idx+1)%len(s.preset_names)
        s._apply_preset()

    def draw(s,scan,ts):
        fr=np.zeros((s.H,s.W,3),dtype=np.uint8);fr[:]=(14,16,22)
        for r in range(500,5000,500):
            pr=int(r*s.sc2);cv2.circle(fr,(s.cx,s.cy),pr,(25,30,38),1)
        for q,a,d in scan:
            if d<=0:continue
            r=math.radians(a);px=s.cx+int(d*math.cos(r)*s.sc2);py=s.cy-int(d*math.sin(r)*s.sc2)
            if 0<=px<s.W and 0<=py<s.H:cv2.circle(fr,(px,py),1,(0,100,0),-1)
        for t in ts:
            rx,ry=s.cx+int(t['rx']*s.sc2),s.cy-int(t['ry']*s.sc2)
            cv2.circle(fr,(rx,ry),14,(0,200,255),2);cv2.circle(fr,(rx,ry),4,(0,200,255),-1)
            cv2.putText(fr,f"x={t['x']:.2f} y={t['y']:.2f}",(rx+16,ry+4),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,200,255),1)
        # Status bar
        cv2.rectangle(fr,(0,0),(s.W,58),(16,22,40),-1)
        cv2.putText(fr,"IAM LiDAR Tracker",(12,22),cv2.FONT_HERSHEY_SIMPLEX,0.55,(220,230,240),1)
        y=45;bl=s.det.bl is not None
        pname=s.preset_names[s.preset_idx]if s.preset_names else'-'
        if not bl and not s.abd:
            rm=max(0,3-(time.time()-s.abt));cv2.putText(fr,f"BL in {rm:.0f}s",(16,y),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,180,255),1)
        else:
            cv2.putText(fr,f"BL:{'OK'if bl else'-'}",(16,y),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,200,100)if bl else(150,160,180),1)
        cv2.putText(fr,f"T:{len(ts)}",(100,y),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,200,255),1)
        cv2.putText(fr,f"Preset: {pname}",(170,y),cv2.FONT_HERSHEY_SIMPLEX,0.35,(0,255,200),1)
        cv2.putText(fr,f"FPS:{s.fps}",(s.W-80,y),cv2.FONT_HERSHEY_SIMPLEX,0.35,(100,110,130),1)
        # Buttons
        cv2.rectangle(fr,(0,58),(s.W,100),(20,26,44),-1)
        for bx,bw,lb in[(12,130,'Baseline [B]'),(152,190,f'Preset: {pname} [M]')]:
            cv2.rectangle(fr,(bx,65),(bx+bw,95),(40,55,80),-1)
            cv2.rectangle(fr,(bx,65),(bx+bw,95),(70,85,110),1)
            ts2=cv2.getTextSize(lb,cv2.FONT_HERSHEY_SIMPLEX,0.35,1)[0]
            cv2.putText(fr,lb,(bx+(bw-ts2[0])//2,65+(30+ts2[1])//2),cv2.FONT_HERSHEY_SIMPLEX,0.35,(200,210,230),1)
        return fr

    def run(s):
        w='IAM LiDAR Tracker';cv2.namedWindow(w,cv2.WINDOW_NORMAL);cv2.resizeWindow(w,s.W,s.H);cv2.setMouseCallback(w,s.on_mouse)
        print(f"\n  TUIO: {TUIO_H}:{TUIO_P}")
        print(f"  Auto-baseline (3s)...\n")
        fc=0;ft=time.time()
        while True:
            scan=s.sc.get()
            if not s.abd and s.det.bl is None and scan and len(scan)>20:
                if time.time()-s.abt>=3:
                    if s.det.set_bl(scan):s.abd=True;print(f"  ✓ Auto-BL: {len(s.det.bl)} pt")
                    elif time.time()-s.abt>=8:s.abd=True
            ts=s.det.detect(scan)
            if ts:
                s.tuio.send([{'id':t['id'],'x':t['x'],'y':t['y']}for t in ts])
                if s.dbg<5:
                    s.dbg+=1;t=ts[0]
                    print(f"[TUIO] id={t['id']} x={t['x']:.3f} y={t['y']:.3f} raw=({t['rx']:.0f},{t['ry']:.0f})")
            else:s.tuio.send([])
            cv2.imshow(w,s.draw(scan,ts))
            fc+=1;now=time.time()
            if now-ft>=1:s.fps=fc;fc=0;ft=now
            k=cv2.waitKey(16)&0xFF
            if k in(ord('q'),27):break
            elif k==ord('b'):s._bl()
            elif k==ord('m'):s._next()
        s.sc.stop();cv2.destroyAllWindows()

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default=None);p.add_argument('--simulate',action='store_true')
    a=p.parse_args()
    print("\n═══════════════════════════════════════\n  IAM LiDAR Tracker v2.2\n═══════════════════════════════════════\n")
    if a.simulate:sc=Sim()
    else:
        if not HP:print("pip install pyrplidar");sys.exit(1)
        port=a.port or'COM3'
        try:
            for pp in serial.tools.list_ports.comports():
                if'CP210'in pp.description or'Silicon'in pp.description:port=pp.device;break
        except:pass
        sc=Scanner()
        if not sc.connect(port):print("\n  ✗ Niet verbonden");sys.exit(1)
        sc.start()
    App(sc).run()

if __name__=='__main__':main()
