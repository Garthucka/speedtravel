"""Краткие итоги замера: скорость, ход, длительность."""
import numpy as np

COLUMNS=[('file','Файл'),('vmax','Vmax, м/с'),('t_vmax','t(Vmax), мс'),('vmin','Vmin, м/с'),
         ('stroke','Ход полный, мм'),('x_start','Ход нач., мм'),('x_end','Ход кон., мм'),
         ('t_start','Начало движения, мс'),('t_end','Конец движения, мс'),('t_move','Время движения, мс'),
         ('duration','Длительность записи, мс'),('method','Метод скорости'),('warnings','Предупреждения')]

def summarize(name,d,p):
    t,x,v=p['t'],p['x'],p['v']
    stroke=float(np.ptp(x));x0=float(np.median(x[:max(3,len(x)//50)]));x1=float(np.median(x[-max(3,len(x)//50):]))
    band=max(.01*stroke,.03);moving=np.flatnonzero(np.abs(x-x0)>band)
    ts=float(t[moving[0]]) if len(moving) else float('nan')
    away=np.flatnonzero(np.abs(x-x1)>band)
    te=float(t[away[-1]]) if len(away) else float('nan')
    i=int(np.argmax(np.abs(v)));j=int(np.argmin(v))
    warn=sum(1 for e in d['quality']['entries'] if e['level']=='warning')
    return dict(file=name,vmax=float(v[i]),t_vmax=float(t[i]),vmin=float(v[j]),stroke=stroke,
                x_start=x0,x_end=x1,t_start=ts,t_end=te,t_move=te-ts,duration=float(t[-1]),
                method=p['velocity_method'],warnings=warn)

def short(s):
    return f"{s['file']}  |  Vmax {s['vmax']:.2f} м/с  ход {s['stroke']:.1f} мм  {s['duration']:.0f} мс"

def write_csv(path,rows):
    import csv
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f,delimiter=';');w.writerow([h for _,h in COLUMNS])
        for r in rows:
            w.writerow([ (f"{r[k]:.4f}".replace('.',',') if isinstance(r[k],float) else r[k]) for k,_ in COLUMNS])
