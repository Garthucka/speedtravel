"""Построение графиков хода, скорости и контактов (общая функция для GUI и экспорта PNG)."""
import numpy as np
import matplotlib
matplotlib.rcParams['font.family']='DejaVu Sans'

def draw(fig,name,d,p):
    fig.clear()
    gs=fig.add_gridspec(3,1,height_ratios=[3,3,1],hspace=0.28)
    a1=fig.add_subplot(gs[0]);a2=fig.add_subplot(gs[1],sharex=a1);a3=fig.add_subplot(gs[2],sharex=a1)
    kt=d.get('motion_t',d['t']);kx=d.get('motion_x',d['x'])
    a1.plot(kt,kx,'.',ms=2,color='gray',label='узлы датчика')
    a1.plot(p['t'],p['x'],color='tab:blue',lw=1.2,label='ход (сглаженный)')
    a1.set_ylabel('Ход, мм');a1.legend(loc='best');a1.grid(True);a1.set_title(name,fontsize=9)
    a2.plot(p['t'],p['v'],color='tab:red',lw=1)
    for lo,hi in p.get('velocity_quality',{}).get('edge_unresolved_ms',[]):
        if hi>lo:a2.axvspan(lo,hi,color='orange',alpha=.2)
    i=int(np.argmax(np.abs(p['v'])))
    a2.plot([p['t'][i]],[p['v'][i]],'ko',ms=4)
    a2.annotate(f"Vmax {p['v'][i]:.2f} м/с",(p['t'][i],p['v'][i]),textcoords='offset points',xytext=(8,-4),fontsize=8)
    a2.set_ylabel('Скорость, м/с');a2.grid(True)
    for j in range(d['c'].shape[1]):
        a3.step(d['t'],d['c'][:,j]+1.2*j,where='post',label='ABC'[j])
    a3.set_ylabel('Контакты');a3.set_xlabel('Время, мс');a3.grid(True)
    if d['c'].shape[1]:a3.legend(loc='right',ncol=3,fontsize=7)
    plt_setp=[ax.tick_params(labelsize=8) for ax in (a1,a2,a3)]
    return a1,a2,a3
