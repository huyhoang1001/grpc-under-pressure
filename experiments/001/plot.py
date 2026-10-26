#!/usr/bin/env python3
"""Render representative measured runs; repeatability is in analysis.json."""
import argparse,csv,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
data=json.loads((args.directory/'analysis.json').read_text())
fig,axes=plt.subplots(3,1,figsize=(11,10),sharex=True)
for ax,variant in zip(axes,['direct','unbounded','bounded']):
    chosen=next(r for r in data['runs'] if r['variant']==variant and r['name'].startswith('overload') and r['valid'])
    folder=args.directory/chosen['name']
    def read(name):
        with (folder/name).open() as f:return [{k:float(v) for k,v in r.items()} for r in csv.DictReader(f)]
    server=read('server.csv');client=read('client.csv')
    t=[r['elapsed_s'] for r in server]
    ax.plot(t,[r['queue_bytes']/2**20 for r in server],label='Queued payload MiB',color='tab:blue')
    ax.plot(t,[r['rss_bytes']/2**20 for r in server],label='Server RSS MiB',color='tab:orange')
    ax.set_ylabel('MiB');ax.set_title(chosen['name']+' (one representative run)');ax.grid(alpha=.2)
    ax.axvspan(.4,12.4,alpha=.08,color='grey',label='Offered-load interval (approx.)')
    rates=ax.twinx()
    def rate(rows,key,offset):
        return ([b['elapsed_s']+offset for a,b in zip(rows,rows[5:])],[(b[key]-a[key])/(b['elapsed_s']-a['elapsed_s']) for a,b in zip(rows,rows[5:])])
    x,y=rate(server,'processed',0);rates.plot(x,y,label='Worker completions/s',color='tab:green',alpha=.8)
    x,y=rate(client,'completed',.4);rates.plot(x,y,label='Completed Send/s',color='tab:red',alpha=.8)
    rates.set_ylabel('messages/s');rates.set_ylim(0,340)
    handles,labels=ax.get_legend_handles_labels();h,l=rates.get_legend_handles_labels()
    ax.legend(handles+h,labels+l,loc='upper right',fontsize=8)
axes[-1].set_xlabel('Server elapsed seconds; client shifted by approximate 0.4s idle start')
fig.suptitle('Experiment 001 — 12s offered overload, then drain; separate byte and rate scales')
fig.tight_layout()
fig.savefig(args.directory/'comparison.svg');fig.savefig(args.directory/'comparison.png',dpi=150)
