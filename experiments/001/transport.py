#!/usr/bin/env python3
"""Summarize h2 debug events; these are stack logs, not captured wire packets."""
import argparse,csv,datetime,json,re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
summary={}
for variant in ['unbounded','bounded']:
    folder=args.directory/('diagnostic-'+variant)
    start=None;credit=0;frames=0;ts=[];credits=[];counts=[];first4credit=0;first4frames=0
    for line in (folder/'server.log').read_text().splitlines():
        if not line.startswith('20'):continue
        stamp=datetime.datetime.fromisoformat(line.split()[0].replace('Z','+00:00')).timestamp()
        if start is None:start=stamp
        elapsed=stamp-start
        update=re.search(r'h2::codec::framed_write: send frame=WindowUpdate \{ stream_id: StreamId\(1\), size_increment: (\d+)',line)
        data='h2::codec::framed_read: received frame=Data { stream_id: StreamId(1)' in line
        if update:credit+=int(update.group(1))
        if data:frames+=1
        if update or data:
            ts.append(elapsed);credits.append(credit/2**20);counts.append(frames)
        if elapsed<=4:first4credit=credit;first4frames=frames
    summary[variant]={'stream1_window_update_credit_bytes':credit,'received_data_frame_events':frames,'first4s_stream_credit_bytes':first4credit,'first4s_data_frame_events':first4frames,'note':'Unique h2 DEBUG send-frame / received-frame log events, not packet capture. Time origin is first handshake log.'}
    axes[0].step(ts,credits,where='post',label=variant)
    axes[1].step(ts,counts,where='post',label=variant)
axes[0].set_ylabel('Stream-1 WINDOW_UPDATE credit (MiB)');axes[1].set_ylabel('Received DATA frame events');axes[1].set_xlabel('Seconds since first handshake log')
for ax in axes:ax.axvspan(0,4,color='grey',alpha=.1);ax.legend();ax.grid(alpha=.2)
fig.suptitle('Separate 4s diagnostic offered load + drain — h2 stack events, not packet capture')
fig.tight_layout();fig.savefig(args.directory/'transport.svg');fig.savefig(args.directory/'transport.png',dpi=150)
(args.directory/'transport-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
