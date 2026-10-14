#!/usr/bin/env python3
"""Independent metadata conservation/budget checker for minimal non-sensitive artifacts.

This checker does not certify OCR correctness or auto-ROI semantics. Actual rendered
crop equality and source-line reachability are checked by check_scroll_text.py.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

CONSERVE = 'SCROLL-TEXT-CONSERVATION'
BOUNDED = 'SCROLL-TEXT-LOCAL-BOUNDED'


def check(data):
    sources = data['observations']
    lookup = {x['id']: x for x in sources}
    assert len(lookup) == len(sources)
    seen, failures = [], []
    conservation = True
    for block in data['blocks']:
        refs = block['observation_ids']
        if not refs or any(r not in lookup for r in refs):
            conservation = False
            continue
        if block['text'] not in {lookup[r]['text'] for r in refs}:
            conservation = False
        positions = [(lookup[r]['frame'], lookup[r]['slot']) for r in refs]
        if len({p[0] for p in positions}) != len(positions):
            # A single block cannot collapse two positions in the same screen.
            conservation = False
        seen.extend(refs)
    conservation &= sorted(seen) == sorted(lookup)
    cache_safe = all(item['pixel_sha256'] == item['cached_pixel_sha256'] for item in data['cache_reuses'])
    conservation &= cache_safe
    if not conservation:
        failures.append(CONSERVE)
    limits = data['budgets']
    bounded = all(0 <= limits[name]['actual'] <= limits[name]['max'] for name in
                  ('frames','pixels_per_frame','ocr_images','review_images','review_groups'))
    if data['engine_error'] and data['status'] not in ('failed','partial'):
        bounded = False
    if data['budget_exhausted'] and data['status'] not in ('partial','failed'):
        bounded = False
    if data['source_sha_before'] != data['source_sha_after'] or data['old_output_sha_before'] != data['old_output_sha_after']:
        bounded = False
    if not bounded:
        failures.append(BOUNDED)
    return failures


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);args=p.parse_args()
    try:
        raw=args.input.read_bytes();data=json.loads(raw);failures=check(data)
        report={'artifact_sha256':{'scroll-validation':sha256(raw).hexdigest()},
                'measurements':{CONSERVE:{'conservation-passed':CONSERVE not in failures},
                                BOUNDED:{'bounded-local-passed':BOUNDED not in failures}}}
        if failures:
            report['failed_constraint_ids']=failures
        else:
            report['passed_constraint_ids']=[CONSERVE,BOUNDED]
            report['observables']={'scroll-source-observation-set':sorted(x['id'] for x in data['observations']),
                                   'scroll-completion-state':[data['status']]}
        print(json.dumps(report,sort_keys=True));return 3 if failures else 0
    except (OSError,ValueError,KeyError,TypeError,AssertionError) as exc:
        print(json.dumps({'error':str(exc)}));return 2

if __name__=='__main__':raise SystemExit(main())
