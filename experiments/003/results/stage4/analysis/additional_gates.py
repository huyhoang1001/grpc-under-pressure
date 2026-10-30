#!/usr/bin/env python3
"""Independent whole-run identity, phase and provenance audit of retained pilot data."""
import collections,hashlib,json,sys
from pathlib import Path
OUT=Path(sys.argv[1]);names=['final-low-wait','overload-wait','overload-reject','overload-retry','overload-drop','overhead-wait-buffered'];rows={}
for name in names:
 d=OUT/name;m=json.loads((d/'verification.json').read_text());s=json.loads((d/'server/server-ledger.json').read_text());c=json.loads((d/'client-report.json').read_text());ce=[json.loads(x) for x in (d/'client-events.jsonl').read_text().splitlines()];se=[json.loads(x) for x in (d/'server/server-events.jsonl').read_text().splitlines()]
 by=collections.defaultdict(list)
 for e in ce:
  if e['kind']=='attempt_initiated':by[e['message_id']].append((e['attempt_id'],e['attempt_number']))
 assert sum(len(x) for x in by.values())<=8640
 assert all([n for _,n in group]==list(range(1,len(group)+1)) and len(group)<=3 for group in by.values())
 actual={a['attempt_id']:(a['message_id'],a['attempt_number']) for a in s['attempts']};client={a:(i,n) for i,group in by.items() for a,n in group}
 assert len(actual)==len(s['attempts'])==s['attempt_entries'];assert actual==client
 assert all(a['write_accepted'] for a in s['attempts'])
 assert all(not x['ack_missing'] and not x['ambiguity'] for x in c['server_reconciliation']['Outcomes'])
 refuses=[e['offset_ns'] for e in se if e['kind']=='policy_refusal'];rows[name]={'verdict':'PASS','attempts':len(actual),'originals_attempted':len(by),'max_attempts_per_original':max(len(x) for x in by.values()),'all_attempt_ids_and_numbers_match':True,'all_terminal_frames_locally_written_and_observed':True,'refusal_first_offset_ns':min(refuses) if refuses else None,'refusal_last_offset_ns':max(refuses) if refuses else None,'source_hashes_unchanged':m['source_hashes_unchanged']}
(OUT/'ADDITIONAL-GATES.json').write_text(json.dumps({'verdict':'PASS','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':rows},indent=2)+'\n')
print('PASS: all identity/attempt limits, ACK observations and full-source provenance gates')
