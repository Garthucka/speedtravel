"""Загрузка CSV и расчёт хода/скорости. Взято из breakerdiag/data.py (CSV-часть без изменений логики)."""
import csv,hashlib,io,json,re
from pathlib import Path
import numpy as np
from scipy.signal import savgol_filter

CONFIG={'dt':.1,'window':1.5,'points':256,'hold_ms':3.}
CONFIG['velocity_version']='central4_detect_v1'
CONFIG['sampling_version']='pkv_channel_events_v1'

class MappingNeeded(ValueError):
    def __init__(self,spec):self.spec=spec;super().__init__('Требуется однократное сопоставление каналов нового формата')

def read_text(path):
    raw=Path(path).read_bytes()
    encs=('utf-16',) if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-8-sig','cp1251')
    for encoding in encs:
        try:return raw.decode(encoding)
        except UnicodeDecodeError:pass
    raise ValueError('Не распознана кодировка')

def norm(s):return re.sub(r'[^a-zа-я0-9]','',s.lower().replace('ё','е'))

def number(s):
    return float(str(s).strip().replace('\u00a0','').replace(' ','').replace(',','.'))

def csv_spec(path):
    text=read_text(path);lines=[l for l in text.splitlines() if l.strip()]
    if not lines:raise ValueError('Пустой CSV')
    best=None
    for sep in (';','\t',','):
        rows=list(csv.reader(lines,delimiter=sep))
        for i,row in enumerate(rows[:30]):
            if len(row)<2:continue
            names=[norm(x) for x in row]
            timecols=[j for j,n in enumerate(names) if n.startswith(('время','time','timestamp')) or n in ('t','tms','ts')]
            if timecols:
                valid=0
                for values in rows[i+1:i+8]:
                    if len(values)!=len(row):continue
                    try:
                        number(values[timecols[0]])
                        others=[]
                        for j,value in enumerate(values):
                            if j==timecols[0]:continue
                            try:others.append(number(value))
                            except (ValueError,TypeError):pass
                        if others:valid+=(len(others)+1)/len(values)
                    except (ValueError,TypeError):pass
                score=(valid,len(row))
                candidate=(score,sep,i,rows,timecols[0])
                if best is None or candidate[0]>best[0]:best=candidate
                break
    if best is None:
        sep=max((';','\t',','),key=lambda s:len(next(csv.reader([lines[0]],delimiter=s))))
        rows=list(csv.reader(lines,delimiter=sep));best=(len(rows[0]),sep,0,rows,None)
    _,sep,start,rows,timeindex=best;headers=[h.strip() for h in rows[start]]
    if len(headers)<2:raise ValueError('Не найден табличный CSV')
    signature=hashlib.sha256(json.dumps([sep,headers],ensure_ascii=False).encode()).hexdigest()
    travel=[];contacts={};time_known=False;suggest={'time':timeindex,'travel':None,'contacts':[],'time_unit':'ms','factor_mm':1.,'offset_mm':0.}
    for i,h in enumerate(headers):
        n=norm(h);lower=h.lower()
        if i==timeindex:
            unit=re.search(r'(?:[, (\[])(?:\s*)(мс|мкс|с|ms|us|s|sec)(?:[ )\]]|$)',lower)
            if unit:time_known=True;suggest['time_unit']={'мс':'ms','мкс':'us','с':'s','ms':'ms','us':'us','s':'s','sec':'s'}[unit.group(1)]
            continue
        is_speed=('скорост' in n or 'velocity' in n or 'speed' in n or re.search(r'\(\s*v\s*\)',lower))
        if not is_speed and (n.startswith(('датчик','sensor')) or any(w in n for w in ('ход','перемещ','travel','displacement','position'))):travel.append(i)
        canonical=h.strip().upper().translate(str.maketrans({'А':'A','В':'B','С':'C'}))
        if canonical in ('A','B','C'):contacts[canonical]=i
    if len(travel)==1:suggest['travel']=travel[0]
    suggest['contacts']=[contacts[k] for k in ('A','B','C') if k in contacts]
    units_known=suggest['travel'] is not None and (any(w in headers[suggest['travel']].lower() for w in ('мм','mm')) or norm(headers[suggest['travel']]) in ('датчик1','sensor1'))
    auto=timeindex is not None and suggest['travel'] is not None and units_known and time_known
    return dict(headers=headers,rows=rows[start+1:],separator=sep,signature=signature,suggest=suggest,auto=auto,path=str(path))

def load_csv(path,mappings):
    spec=csv_spec(path);mapping=mappings.get(spec['signature'])
    if mapping is None:
        if not spec['auto']:raise MappingNeeded({k:v for k,v in spec.items() if k!='rows'})
        mapping=spec['suggest']
    ti=int(mapping['time']);xi=int(mapping['travel']);ci=[int(i) for i in mapping.get('contacts',[])];factor=float(mapping['factor_mm']);offset=float(mapping.get('offset_mm',0))
    if not np.isfinite([factor,offset]).all() or factor==0:raise ValueError('Неверная калибровка датчика')
    values=[];payload=[];names=[norm(h) for h in spec['headers']]
    for lineno,row in enumerate(spec['rows'],1):
        if not row or all(not str(v).strip() for v in row):continue
        if len(row)!=len(spec['headers']):raise ValueError(f'Неполная строка {lineno} после заголовка')
        try:values.append([number(row[j]) for j in [ti,xi]+ci])
        except Exception as e:raise ValueError(f'Не числовые данные выбранных каналов, строка {lineno}: {e}')
        tokens=[]
        for j,value in enumerate(row):
            if j==ti:continue
            try:
                token=number(value)
                if not np.isfinite(token):raise ValueError(f'NaN/Inf, столбец {j+1}, строка {lineno}')
            except (TypeError,ValueError):
                token=str(value).strip()
                if token.lower() in ('nan','inf','-inf','+inf'):raise ValueError(f'NaN/Inf, столбец {j+1}, строка {lineno}')
            tokens.append(token)
        payload.append(tokens)
    a=np.asarray(values,float)
    if a.ndim!=2 or len(a)<5:raise ValueError('Мало точек')
    units={'ms':1.,'s':1000.,'us':.001};t=a[:,0]*units[mapping['time_unit']];x=a[:,1]*factor+offset;c=a[:,2:]
    result=finish(t,x,c,path,hashlib.sha256(Path(path).read_bytes()).hexdigest(),spec['signature'],[])
    known_pkv=('запо' in names and 'iоткл' in names and names[xi].startswith('датчик') and names[xi]+'v' in names)
    mode=mapping.get('sampling_mode','pkv_events' if known_pkv else 'sampled')
    result['sampling_mode']=mode
    if mode=='pkv_events':
        from .event_sampling import select_motion_rows
        keep=np.r_[np.diff(t)!=0,True]
        values_without_time=np.asarray(payload,dtype=object)[keep]
        sensor_column=xi if xi<ti else xi-1
        mask,summary=select_motion_rows(result['t'],result['x'],values_without_time,sensor_column)
        result['motion_t']=result['t'][mask];result['motion_x']=result['x'][mask]
        result['event_sampling_summary']=summary
        result['notes'].append(f'Событийный экспорт ПКВ: найдено {summary["other_only_rows"]} строк изменений других каналов без изменения хода; они не используются как отдельные отсчёты положения. Начальная площадка и концы записи сохранены.')
        result['notes'].append('Время и контакты исходной таблицы сохранены. Восстановление хода между событиями не доказывает отсутствие остановок между ними.')
    elif mode!='sampled':raise ValueError('Неизвестный режим выборки датчика')
    return result

def finish(t,x,c,path,sha,signature,notes):
    """Проверяет время и формирует конкретные сообщения о качестве записи."""
    t=np.asarray(t,dtype=float);x=np.asarray(x,dtype=float);c=np.asarray(c,dtype=float)
    if t.ndim!=1 or x.shape!=t.shape or c.ndim!=2 or len(c)!=len(t):
        raise ValueError('Несогласованные размеры времени, хода и контактов')
    if len(t)<5 or not np.isfinite(t).all() or not np.isfinite(x).all():
        raise ValueError('Недопустимые время/ход')
    if np.any(np.diff(t)<0):
        raise ValueError('Время убывает: автоматическая сортировка запрещена')
    if c.size and (not np.isfinite(c).all() or not np.isin(c,[0,1]).all()):
        raise ValueError('Контакты должны быть 0/1')
    messages=list(notes)
    quality={'schema':1,'entries':[],'duplicate_rows':0,'conflicting_duplicate_groups':0}
    origin=float(t[0])
    starts=np.r_[0,np.flatnonzero(np.diff(t)!=0)+1]
    ends=np.r_[starts[1:],len(t)]
    conflicts=[]
    for a,b in zip(starts,ends):
        if b-a<2:continue
        quality['duplicate_rows']+=int(b-a-1)
        channels=[]
        if np.any(x[a:b]!=x[b-1]):channels.append('ход')
        for j in range(c.shape[1]):
            if np.any(c[a:b,j]!=c[b-1,j]):channels.append(f'контакт {j+1}')
        if channels:conflicts.append({'time_ms':float(t[a]-origin),'rows':int(b-a),'channels':channels})
    keep=np.r_[np.diff(t)!=0,True]
    t=t[keep]-origin;x=x[keep];c=c[keep]
    if len(t)<5:raise ValueError('Мало различных меток времени')
    if quality['duplicate_rows']:
        if not conflicts:
            msg=f'Дубликаты времени: {quality["duplicate_rows"]}; ход и выбранные контакты совпадают. Повторные строки исключены.'
            messages.append(msg);quality['entries'].append({'level':'info','code':'identical_duplicates','message':msg})
        else:
            quality['conflicting_duplicate_groups']=len(conflicts)
            detail='; '.join(f'{r["time_ms"]:.6g} мс ({", ".join(r["channels"])})' for r in conflicts[:3])
            msg=f'ВНИМАНИЕ: разные состояния при одинаковом времени: {detail}. Оставлено последнее состояние; последовательность внутри этой метки времени не восстанавливается.'
            messages.append(msg);quality['entries'].append({'level':'warning','code':'conflicting_duplicates','message':msg,'groups':conflicts})
    dt=np.diff(t);dx=np.diff(x);median=float(np.median(dt));maximum=float(np.max(dt))
    quality.update(time_origin_ms=origin,median_dt_ms=median,max_dt_ms=maximum)
    rare=np.flatnonzero(dt>5*median)
    epsilon=max(.01*float(np.ptp(x)),.02)
    changed=[int(i) for i in rare if abs(dx[i])>epsilon]
    quality.update(rare_interval_count=int(len(rare)),large_displacement_threshold_mm=epsilon)
    intervals=[{'start_ms':float(t[i]),'end_ms':float(t[i+1]),'dt_ms':float(dt[i]),'dx_mm':float(dx[i])} for i in changed]
    quality['rare_intervals_with_large_displacement']=intervals
    if len(rare):
        msg=f'Неравномерная сетка времени: медианный шаг {median:.6g} мс, максимальный {maximum:.6g} мс. Это не доказывает потерю данных.'
        messages.append(msg);quality['entries'].append({'level':'info','code':'nonuniform_time','message':msg})
        if intervals:
            details='; '.join(f'{r["start_ms"]:.6g}–{r["end_ms"]:.6g} мс: Δt={r["dt_ms"]:.6g} мс, Δход={r["dx_mm"]:.6g} мм' for r in intervals[:3])
            msg='ВНИМАНИЕ: редкие отсчёты с заметным изменением хода: '+details+'. Скорость между ними зависит от интерполяции; проверьте исходную запись.'
            messages.append(msg);quality['entries'].append({'level':'warning','code':'sparse_motion','message':msg,'intervals':intervals})
        else:
            msg='В разреженных интервалах изменение хода по КРАЙНИМ точкам невелико. Это не исключает неизвестных кратковременных изменений между ними.'
            messages.append(msg);quality['entries'].append({'level':'info','code':'small_endpoint_changes','message':msg})
    return dict(t=t,x=x,c=c,path=str(path),sha256=sha,signature=signature,notes=messages,quality=quality)

def load(path,mappings):
    if Path(path).suffix.lower()!='.csv':raise ValueError('Поддерживается только CSV')
    return load_csv(path,mappings)

def process(d):
    from .velocity_events import corrected_process
    result=corrected_process(d,CONFIG)
    if result['velocity_method']=='event_central_four_intervals':
        info=result['velocity_quality']
        message=f'Скорость: обнаружен период 4 межсобытийных интервалов; использована центральная оценка по четырём интервалам. Медианная ширина оценки {info["median_velocity_support_ms"]:.6g} мс. На краях сохранена прежняя оценка производной.'
        if message not in d['notes']:d['notes'].append(message)
    return result
