#!/usr/bin/env python3
"""Explicit synthetic accounting fixtures, NOT system measurements."""
import copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
spec=importlib.util.spec_from_file_location('v',ROOT/'experiments/003/fixtures/verify-stage3.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def main():
 baseline=Path(sys.argv[1]);out=Path(sys.argv[2]);d=v.load(baseline);d=copy.deepcopy(d)
 template=d['workload']['originals'][0]
 d['workload']['originals']=[dict(template,message_id=i,scheduled_offset_ns=i*12_500_000,deadline_offset_ns=i*12_500_000+2_000_000_000) for i in range(2880)]
 d['client_events']=[];d['server_events']=[];s=d['server'];c=d['client'];s['originals']=[];s['attempts']=[]
 for key in ['event_seq','decoded_frames','decoded_attempts','logical_entries','attempt_entries','permits_acquired','permits_released','writer_progress_ns','writer_calls']:s[key]=0
 s['high_water']={k:0 for k in s['high_water']}
 for key in ['Pending','Outstanding','Attempts','FirstAttempts','Retries','SendSuccess','EventQueue','EventSeq','ResponseQueue']:c['client'][key]=0
 c['client']['Originals']=2880;c['client']['HighWater']={k:0 for k in c['client']['HighWater']};c['transport']={k:0 for k in c['transport']}
 c['server_reconciliation']={'N':2880,'U':0,'Attempts':0,'Outcomes':[{'message_id':i,'disposition':'EXPIRED_BEFORE_SEND','ack_missing':False} for i in range(2880)],'Counts':{'EXPIRED_BEFORE_SEND':2880}}
 result=v.verify(d)
 cases=[]
 for code,detail,expected in [(1,'COMPLETED','COMPLETED_ON_TIME'),(2,'','REJECTED_FINAL'),(3,'','DROPPED'),(4,'EXPIRED_QUEUED','EXPIRED_WAITING_OR_QUEUED'),(4,'EXPIRED_PROCESSING','EXPIRED_PROCESSING'),(5,'','PROCESSING_FAILED'),(6,'','CANCELLED')]:
  t={'outcome':code,'offset_ns':100,'detail_code':detail};actual=v.classify(t,100);assert actual==expected;cases.append({'input':t,'deadline_ns':100,'expected':expected,'actual':actual})
 assert v.classify({'outcome':1,'offset_ns':101,'detail_code':'COMPLETED'},100)=='COMPLETED_LATE'
 edge=[]
 for terminal,local,count,observed,decoded,closed,expected in [
  ({'outcome':2,'offset_ns':1,'detail_code':'REJECTED_OVERLOAD'},'EXPIRED_WAITING_OR_QUEUED',1,{},True,True,'EXPIRED_WAITING_OR_QUEUED'),
  ({'outcome':2,'offset_ns':1,'detail_code':'REJECTED_OVERLOAD'},'',2,None,True,True,'REJECTED_FINAL'),
  ({'outcome':2,'offset_ns':1,'detail_code':'REJECTED_OVERLOAD'},'',2,None,False,True,'UNKNOWN'),
  (None,'CLIENT_BACKLOG_EXHAUSTED',0,None,False,True,'CLIENT_BACKLOG_EXHAUSTED')]:
  actual=v.disposition(terminal,100,local,count,observed,decoded,closed);assert actual==expected;edge.append({'expected':expected,'actual':actual})
 # A fully explicit valid failed-Send/UNKNOWN synthetic ledger, not measurements.
 failed=copy.deepcopy(d);failed['manifest']['mode']='documented-transport-ambiguity';failed['manifest']['documented_transport_ambiguity']='synthetic blocked Send cancelled before decode'
 failed['workload']['originals']=failed['workload']['originals'][:1];failed['server']['failed']='STREAM_FAILED';fc=failed['client'];fc['exchange_error']='SYNTHETIC cancelled Send'
 events=[]
 for seq,(kind,offset,pending,outstanding) in enumerate([('original_arrival',0,1,0),('attempt_initiated',0,0,1),('grpc_send_start',1,0,1),('grpc_send_return',2,0,1),('stream_closed',3,0,0)],1):
  events.append({'seq':seq,'kind':kind,'offset_ns':offset,'commit_offset_ns':offset,'message_id':0,'attempt_id':0,'pending':pending,'outstanding':outstanding,'event_queue':seq,'response_queue':0,'attempt_number':1,'send_success':False,'send_duration_ns':1,'send_timing_exact':True})
 failed['client_events']=events
 fc['client'].update(Originals=1,Attempts=1,FirstAttempts=1,EventSeq=5,HighWater={'Pending':1,'Outstanding':1,'Events':5,'Responses':0})
 fc['server_reconciliation']={'N':1,'U':0,'Attempts':1,'Outcomes':[{'message_id':0,'disposition':'UNKNOWN','ack_missing':False}],'Counts':{'UNKNOWN':1}}
 unknown=v.verify(failed);assert unknown['partition']=={'UNKNOWN':1}
 out.write_text(json.dumps({'synthetic_only':True,'no_measured_findings':True,'baseline_for_schema_clock_and_process_fields_only':str(baseline),'all2880_unsent':{'N':result['counter_populations']['N'],'A':result['counter_populations']['A'],'partition':result['partition']},'terminal_classification_cases':cases,'late_boundary':'PASS','retry_and_unknown_edge_cases':edge,'failed_send_before_decode':{'synthetic_only':True,'partition':unknown['partition'],'A':unknown['counter_populations']['A'],'S':unknown['counter_populations']['S'],'R':unknown['counter_populations']['R']},'verdict':'PASS'},indent=2)+'\n')
if __name__=='__main__':main()
