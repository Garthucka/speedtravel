"""Ход и скорость высоковольтных выключателей — пакетный просмотр CSV."""
import json,os,queue,shutil,threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg,NavigationToolbar2Tk
from matplotlib.figure import Figure
from core import data as bd
from core.plotting import draw
from core.summary import summarize,short,write_csv

CFG_DIR=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SpeedTravel'
MAP_FILE=CFG_DIR/'mappings.json'

def load_mappings():
    try:return json.loads(MAP_FILE.read_text(encoding='utf-8'))
    except Exception:return {}

def save_mappings(m):
    CFG_DIR.mkdir(parents=True,exist_ok=True)
    tmp=MAP_FILE.with_suffix('.tmp');tmp.write_text(json.dumps(m,ensure_ascii=False,indent=1),encoding='utf-8');tmp.replace(MAP_FILE)

class MappingDialog(tk.Toplevel):
    def __init__(self,master,spec):
        super().__init__(master);self.title('Сопоставление каналов');self.result=None;self.grab_set()
        h=spec['headers'];s=spec['suggest']
        ttk.Label(self,text=os.path.basename(spec['path'])).grid(row=0,columnspan=2,pady=4)
        self.t=ttk.Combobox(self,values=h,state='readonly',width=32);self.x=ttk.Combobox(self,values=h,state='readonly',width=32)
        self.u=ttk.Combobox(self,values=['ms','s','us'],state='readonly',width=8)
        self.f=tk.StringVar(value=str(s['factor_mm']));self.o=tk.StringVar(value=str(s['offset_mm']))
        if s['time'] is not None:self.t.current(s['time'])
        if s['travel'] is not None:self.x.current(s['travel'])
        self.u.set(s['time_unit']);self.contacts=list(s['contacts'])
        rows=[('Время',self.t),('Ход',self.x),('Единица времени',self.u),
              ('Коэфф. → мм (мм=1, м=1000, см=10)',ttk.Entry(self,textvariable=self.f)),('Смещение, мм',ttk.Entry(self,textvariable=self.o))]
        for i,(l,w) in enumerate(rows,1):
            ttk.Label(self,text=l).grid(row=i,column=0,sticky='e',padx=4,pady=2);w.grid(row=i,column=1,padx=4,pady=2)
        ttk.Button(self,text='OK',command=self.ok).grid(row=7,columnspan=2,pady=6);self.wait_window()
    def ok(self):
        if self.t.current()<0 or self.x.current()<0:
            messagebox.showwarning('Каналы','Выберите время и ход',parent=self);return
        try:f=float(self.f.get().replace(',','.'));o=float(self.o.get().replace(',','.'))
        except ValueError:
            messagebox.showwarning('Калибровка','Некорректные числа',parent=self);return
        self.result=dict(time=self.t.current(),travel=self.x.current(),contacts=self.contacts,
                         time_unit=self.u.get(),factor_mm=f,offset_mm=o);self.destroy()

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('Ход и скорость выключателя — пакетный просмотр');self.geometry('1400x820')
        self.folder='';self.files=[];self.cache={};self.sums={};self.errors={}
        self.mappings=load_mappings();self.q=queue.Queue();self.gen=0;self._ui();self.after(100,self._poll)

    def _ui(self):
        bar=ttk.Frame(self);bar.pack(fill='x',padx=6,pady=4)
        ttk.Button(bar,text='Выбрать папку…',command=self.open_folder).pack(side='left')
        ttk.Button(bar,text='Сохранить отмеченные…',command=self.save_selected).pack(side='left',padx=6)
        ttk.Button(bar,text='Таблица итогов (все)…',command=self.export_all).pack(side='left')
        ttk.Button(bar,text='Выделить все',command=lambda:self.lb.selection_set(0,'end')).pack(side='left',padx=6)
        self.info=ttk.Label(bar,text='Папка не выбрана');self.info.pack(side='left',padx=10)
        self.pb=ttk.Progressbar(bar,length=160);self.pb.pack(side='right')
        pw=ttk.PanedWindow(self,orient='horizontal');pw.pack(fill='both',expand=True)
        left=ttk.Frame(pw);pw.add(left,weight=2)
        self.lb=tk.Listbox(left,selectmode='extended',exportselection=False,width=60,font=('Consolas',9))
        sb=ttk.Scrollbar(left,command=self.lb.yview);self.lb.config(yscrollcommand=sb.set)
        self.lb.pack(side='left',fill='both',expand=True);sb.pack(side='left',fill='y')
        self.lb.bind('<<ListboxSelect>>',lambda e:self.show())
        right=ttk.Frame(pw);pw.add(right,weight=5)
        self.fig=Figure(figsize=(9,6.4),dpi=100);self.cv=FigureCanvasTkAgg(self.fig,right)
        NavigationToolbar2Tk(self.cv,right).pack(side='bottom',fill='x')
        self.cv.get_tk_widget().pack(fill='both',expand=True)
        self.note=tk.Text(right,height=6,wrap='word');self.note.pack(fill='x')

    # ---------- загрузка ----------
    def open_folder(self):
        d=filedialog.askdirectory()
        if not d:return
        self.gen+=1;self.folder=d;self.cache.clear();self.sums.clear();self.errors.clear()
        self.files=sorted(p.name for p in Path(d).iterdir() if p.suffix.lower()=='.csv')
        self.lb.delete(0,'end')
        for n in self.files:self.lb.insert('end',n+'  |  …')
        self.pb.config(maximum=max(1,len(self.files)),value=0)
        self.info.config(text=f'{d}: {len(self.files)} CSV')
        if self.files:
            self.lb.selection_set(0);threading.Thread(target=self._worker,args=(self.gen,list(self.files),dict(self.mappings)),daemon=True).start()
            self.show()

    def _worker(self,gen,files,maps):
        for n in files:
            try:
                d=bd.load(os.path.join(self.folder,n),maps);p=bd.process(d)
                self.q.put((gen,n,d,p,None))
            except bd.MappingNeeded:self.q.put((gen,n,None,None,'MAP'))
            except Exception as e:self.q.put((gen,n,None,None,str(e)))

    def _set_item(self,i,txt,color='black'):
        was=self.lb.selection_includes(i)
        self.lb.delete(i);self.lb.insert(i,txt);self.lb.itemconfig(i,fg=color)
        if was:self.lb.selection_set(i)

    def _poll(self):
        try:
            while True:
                gen,n,d,p,err=self.q.get_nowait()
                if gen!=self.gen:continue
                i=self.files.index(n)
                if err is None:
                    self.cache[n]=(d,p);self.sums[n]=summarize(n,d,p);txt=short(self.sums[n]);color='black'
                elif err=='MAP':txt=n+'  |  нужно сопоставление каналов';color='#b36b00'
                else:self.errors[n]=err;txt=n+'  |  ОШИБКА';color='red'
                self._set_item(i,txt,color);self.pb.step(1)
        except queue.Empty:pass
        self.after(100,self._poll)

    def get(self,name):
        if name in self.cache:return self.cache[name]
        path=os.path.join(self.folder,name)
        while True:
            try:
                d=bd.load(path,self.mappings);p=bd.process(d)
                self.cache[name]=(d,p);self.sums[name]=summarize(name,d,p);self.errors.pop(name,None)
                self._set_item(self.files.index(name),short(self.sums[name]));return self.cache[name]
            except bd.MappingNeeded as e:
                dlg=MappingDialog(self,e.spec)
                if not dlg.result:self.errors[name]='Сопоставление отменено';return None
                self.mappings[e.spec['signature']]=dlg.result;save_mappings(self.mappings)
            except Exception as e:
                self.errors[name]=str(e);return None

    def show(self):
        sel=self.lb.curselection()
        if not sel:return
        name=self.files[sel[-1]];res=self.get(name);self.note.delete('1.0','end')
        if res is None:
            self.fig.clear();self.cv.draw_idle();self.note.insert('end',f'Ошибка: {self.errors.get(name)}');return
        d,p=res;draw(self.fig,name,d,p);self.cv.draw_idle()
        s=self.sums[name]
        self.note.insert('end',f"Метод скорости: {s['method']}\nVmax = {s['vmax']:.3f} м/с при t = {s['t_vmax']:.1f} мс; "
            f"ход = {s['stroke']:.2f} мм; движение {s['t_start']:.1f}…{s['t_end']:.1f} мс; запись {s['duration']:.1f} мс\n"+'\n'.join(d['notes']))

    # ---------- сохранение ----------
    def _rows(self,names):
        rows=[]
        for n in names:
            if self.get(n) is not None:rows.append(self.sums[n])
        return rows

    def save_selected(self):
        names=[self.files[i] for i in self.lb.curselection()]
        if not names:messagebox.showinfo('Сохранение','Отметьте замеры в списке (Ctrl/Shift)');return
        out=filedialog.askdirectory(title='Папка для выбранных замеров')
        if not out:return
        ok=[]
        for n in names:
            res=self.get(n)
            if res is None:continue
            d,p=res;base=Path(n).stem
            shutil.copy2(os.path.join(self.folder,n),os.path.join(out,n))
            import numpy as np
            np.savetxt(os.path.join(out,base+'_speed.csv'),np.c_[p['t'],p['x'],p['v']],delimiter=';',fmt='%.6f',
                       header='t_ms;travel_mm;speed_mps',comments='',encoding='utf-8-sig')
            f=Figure(figsize=(11,7.5));draw(f,n,d,p);f.savefig(os.path.join(out,base+'.png'),dpi=150);ok.append(n)
        write_csv(os.path.join(out,'summary.csv'),[self.sums[n] for n in ok])
        messagebox.showinfo('Готово',f'Сохранено замеров: {len(ok)}; с ошибкой: {len(names)-len(ok)}\nТаблица итогов: summary.csv')

    def export_all(self):
        if not self.files:return
        path=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='summary_all.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        rows=self._rows(self.files);write_csv(path,rows)
        messagebox.showinfo('Готово',f'Строк в таблице: {len(rows)} из {len(self.files)}')

if __name__=='__main__':
    App().mainloop()
