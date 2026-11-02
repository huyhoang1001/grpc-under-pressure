#!/usr/bin/env python3
"""Render an existing-endpoint review chart; no new measurements or pooled cohorts."""
import hashlib,json,os,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent

def main():
 r=json.loads((OUT/'audit/REVIEW-AUDIT.json').read_text());rows=[x for x in r['runs'] if x['family']=='PRIMARY'];assert len(rows)==20
 os.environ.setdefault('MPLCONFIGDIR','/tmp/e3-stage7-mpl');os.environ.setdefault('XDG_CACHE_HOME','/tmp/e3-stage7-cache')
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,axes=plt.subplots(1,2,figsize=(10,4.8));policies=['wait','reject','retry','drop'];points=[]
 for j,p in enumerate(policies):
  group=[x for x in rows if x['condition']==p];ys=[100*x['U_over_N'] for x in group]
  axes[0].scatter([j]*5,ys,color='#315b96',s=32);axes[0].plot([j-.13,j+.13],[statistics.mean(ys)]*2,color='black',linewidth=2)
  points += [{'panel':'all-original','family':'PRIMARY','block':x['block'],'policy':p,'value':100*x['U_over_N'],'units':'percent of all2880 scheduled originals','directory':x['directory']} for x in group]
 axes[0].set_xticks(range(4),[p.upper() for p in policies]);axes[0].set(ylim=(0,100),ylabel='On-time originals / all 2,880 scheduled (%)',title='Primary: five blocks; 2 s deadlines')
 for pair in r['primary_recovery_conditional']:
  ys=[pair['reject']['p95']/1e9,pair['retry']['p95']/1e9];axes[1].plot([0,1],ys,'-o',alpha=.8,label='Block '+str(pair['block']))
  for policy in ['reject','retry']:points.append({'panel':'conditional recovery','family':'PRIMARY','block':pair['block'],'policy':policy,'value':pair[policy]['p95']/1e9,'units':'seconds; per-run completed-cohort p95','cohort_n':pair[policy]['n']})
 axes[1].set_xticks([0,1],['REJECT','RETRY']);axes[1].set(ylim=(0,1.3),ylabel='Scheduled→completion p95 (s)',title='Completed originals scheduled in [24, 36) s');axes[1].legend(fontsize=8)
 fig.text(.5,.015,'Recovery cohorts differ: REJECT n=900–932; RETRY n=934–956 per run. Lines pair blocks, not identical original cohorts.',ha='center',fontsize=8);fig.tight_layout(rect=(0,.05,1,1));folder=OUT/'figures';folder.mkdir(exist_ok=True)
 for ext in ['png','svg']:fig.savefig(folder/('primary-tradeoff.'+ext),dpi=170)
 plt.close(fig)
 (OUT/'CHART-DATA.json').write_text(json.dumps(points,indent=2)+'\n')
 charts=[{'id':'primary-outcomes','scope':'PRIMARY','file':'../stage5/analysis/figures/outcomes.png','publication_status':'USE_WITH_CAPTION','caption':'Primary single-client2s study; five matched blocks. Mean fractions of all2880 scheduled originals/run, including never-sent/backlog, expiry, refusal/drop and late completion. No completed-only denominator.'},
 {'id':'primary-tradeoff','scope':'PRIMARY','file':'figures/primary-tradeoff.png','publication_status':'REVIEWED_EXISTING_ENDPOINT_RENDERING','caption':'Primary2s study, five matched blocks. Left: individual U/N values with mean marks, all2880 originals/run. Right: per-run p95 of completed originals scheduled[24,36), REJECT n900–932 and RETRY n934–956; different cohorts, no pooled p95 or per-original causal delay.'},
 {'id':'deadline-panels','scope':'SECONDARY_A','file':'../stage6/analysis/figures/deadline-goodput.png','publication_status':'USE_WITH_CAPTION','caption':'Secondary A actual500ms and5s deadline runs, five matched blocks. All2880 scheduled originals/run; different secondary runtime from primary. Keep valid500ms WAIT block1 visible; no causal explanation or removal. No2s primary interpolation.'},
 {'id':'retry-collision','scope':'SECONDARY_B2','file':'../stage6/analysis/figures/retry-pairs.png','publication_status':'USE_LEFT_PANEL_OR_EXPLAIN_RIGHT_ZOOM','caption':'Secondary B2 eight clients sharing80 originals/s and one server worker, five pairs. Collision uses actual initiated retries in[12,24),60020ms bins and denominator M choose2. Fixed relative backoff, no injected synchronization; means differ from uniform jitter. Right-panel goodput axis is zoomed, not a universal winner.'},
 {'id':'corrected-recovery','scope':'PRIMARY','file':'../stage5/analysis/figures/recovery-observed-intervals.png','publication_status':'APPENDIX_WITH_CAPTION','caption':'Primary recovery observation; five blocks. On-time-rate bins[24,25) through[38,39), with client pending/outstanding endpoints through39s. Pre24-admitted cohort clearance is not whole-system recovery.'},
 {'id':'original-recovery-sentinel','scope':'PRIMARY','file':'../stage5/analysis/figures/recovery.png','publication_status':'DO_NOT_PROMOTE','caption':'Preserved original plot includes an unobserved zero39s closure sentinel for rate; use the corrected display. Do not modify the original evidence.'},
 {'id':'whole-conditional-latency','scope':'PRIMARY','file':'../stage5/analysis/figures/conditional-latency.png','publication_status':'NOT_RECOVERY_EVIDENCE','caption':'Whole-workload completed-cohort p95, five runs/policy. It is not recovery-only p95 and cannot substantiate that phase-specific claim.'}]
 for c in charts:assert (OUT/c['file']).is_file()
 (OUT/'CHARTS.json').write_text(json.dumps({'charts':charts,'data_file':'CHART-DATA.json','generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'no_new_endpoints':True,'performance_runs_executed':0},indent=2)+'\n');print('PASS: existing-endpoint review chart and7 caption/selection records')
if __name__=='__main__':main()
