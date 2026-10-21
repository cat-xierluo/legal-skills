#!/usr/bin/env python3
"""Independent non-sensitive scrolling extraction regressions, generated fixtures."""
from __future__ import annotations
import argparse
import csv
import shutil
from types import SimpleNamespace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from PIL import Image, ImageDraw
from scroll_text import (select_roi, observations, stitch, pixel_hash, promote_new,
                         resolve_new_output, parse_args, run, write_texts, deadline_exceeded)
from scroll_ocr import normalize_lines, OCRFailure
import check_scroll_env as env_probe


def line(text, y, h=.022):
    return {'text':text, 'bbox':[.03,y,.96,y+h], 'confidence':.9, 'raw_index': int(y*1000)}


def frame(n):
    return {'id': f'F{n:06d}', 'sample_seconds': (n-1)*.5}


def page(n, entries):
    ls=[]
    for speaker, clock, text in entries:
        ls += [line(speaker,.1+len(ls)*.025),line(clock,.1+(len(ls)+1)*.025),line(text,.1+(len(ls)+2)*.025)]
    return frame(n), observations(ls, frame(n))


def fixtures():
    # Same horizontal width and alternate body starting points; generate actual pixels.
    for start in (.2,.38):
        a=Image.new('RGB',(400,900),'white'); b=a.copy()
        for im, offset in [(a,0),(b,7)]:
            d=ImageDraw.Draw(im); d.rectangle((5,45,390,60),fill='black')
            for y in range(int(start*900),800,45):
                d.rectangle((10,y+offset,380,y+offset+15), fill='black')
        ls=[line('Transcript',.045),line('A long visible body line at the start', start)]
        roi=select_roi(a,[b],ls)
        assert roi['method']=='ocr_and_neighbor_fixed_ui', roi
        assert roi['box'][1] < start*900 and roi['box'][0]==0 and roi['box'][2]==400
        # A ticking status clock above the fixed tab must not suppress body detection.
        ImageDraw.Draw(b).rectangle((5,3,30,12),fill='black')
        with_clock=select_roi(a,[b],ls)
        assert with_clock['box'][1]<start*900 and with_clock['method']=='ocr_and_neighbor_fixed_ui'
        footer=select_roi(a,[b],ls+[line('播放',.95)])
        assert footer['box'][3]<900 and footer['box'][3]>780
        stable=select_roi(a,[a.copy()],ls)
        assert stable['box']==[0,0,400,900]
        boxless=select_roi(a,[b],[{'text':'Transcript','bbox':None,'raw_index':0}])
        assert boxless['method']=='full_page_fallback'
    # New text appended near the bottom must not cause the unchanged body to be cropped away.
    a=Image.new('RGB',(400,900),'white'); b=a.copy()
    ImageDraw.Draw(b).rectangle((10,800,380,825),fill='black')
    assert select_roi(a,[b],[line('Transcript',.05),line('A long real body must survive',.2)])['box']==[0,0,400,900]
    cut=select_roi(a,[b],[line('edge',.85)], [0,780,400,890])
    assert cut['boundary_lines'], cut
    # Pixel-only caching preserves a one-pixel change (small new character surrogate).
    b.putpixel((390,820),(1,2,3)); assert pixel_hash(a)!=pixel_hash(b)
    entries=[('我','17:09','Alpha unchanged long paragraph for sequence anchor.'),
             ('我','17:09','Beta unchanged long paragraph for sequence anchor.'),
             ('我','17:10','Small new letter X')]
    blocks,issues=stitch([page(1,entries[:2]),page(2,entries),page(3,entries[:2]),page(4,entries)])
    assert len(blocks)==3 and blocks[-1]['text']=='Small new letter X', (len(blocks),issues)
    extended=entries+[('其他','17:10','Another new long fragment after the tail.') ]
    forward,_=stitch([page(1,entries[:2]),page(2,extended)])
    assert all(not b['uncertain_alignment'] for b in forward[-2:])
    # Two true, identical short utterances in one screen are distinct sequence positions.
    repeated=[('我','18:15','Long preceding paragraph acting as a unique contextual anchor.'),
              ('我','18:15','真的。'),('我','18:15','真的。'),
              ('其他','18:15','Long following paragraph acting as a second contextual anchor.')]
    blocks,_=stitch([page(1,repeated),page(2,repeated),page(3,repeated[1:])])
    assert sum(b['text']=='真的。' for b in blocks)==2, blocks
    # An edge truncation replaced by a real complete OCR observation; originals conserved.
    shortened=entries[:2]+[('我','17:10','Small new letter')]
    blocks,_=stitch([page(1,shortened),page(2,entries)])
    assert len(blocks)==3 and len(blocks[-1]['variants'])==2
    assert {v['text'] for v in blocks[-1]['variants']}=={'Small new letter','Small new letter X'}
    unknown=[('我','17:20','An unrelated entirely different screen sentence to preserve.')]
    blocks,issues=stitch([page(1,entries),page(2,unknown)])
    assert any(x['kind']=='unaligned_page' for x in issues) and len(blocks)==4
    with tempfile.TemporaryDirectory(prefix='scroll-text-render-') as folder:
        rendered=Path(folder)
        write_texts(rendered,blocks,issues,'draft_requires_review')
        assert unknown[0][2] in (rendered/'uncertain.md').read_text()
        assert '[待核对齐]' in (rendered/'transcript.txt').read_text()
    # Legacy boxless helpers do not get invented boxes or scores.
    assert normalize_lines({'lines':['legacy'], 'error':''})[0]['bbox'] is None
    edge=normalize_lines({'lines':[{'text':'edge fragment','bbox':[.04,.976,.21,1.00024],'confidence':.9}]})[0]
    assert edge['bbox'][3]==1.00024 and edge['bbox_outside_image']
    for bad in [{'lines':[{'text':'x','bbox':[0,.5,1,.3]}]}, {'lines':[], 'error':'failed'}]:
        try: normalize_lines(bad)
        except OCRFailure: pass
        else: raise AssertionError('invalid OCR succeeded')


def audit_content_regressions():
    # A fixed short speaker/time and a fixed long footer-adjacent sentence are body,
    # even when only the middle of the screen is moving.
    for start in (180, 340):
        a=Image.new('RGB',(400,900),'white'); b=a.copy()
        for im,offset in ((a,0),(b,7)):
            d=ImageDraw.Draw(im);d.rectangle((5,45,390,60),fill='black')
            for y in range(start,700,45):d.rectangle((10,y+offset,380,y+offset+15),fill='black')
            d.text((10,140),'NAME TIME',fill='black');d.text((10,760),'STATIONARY BODY',fill='black')
            d.text((10,850),'PLAY',fill='black')
        lines=[line('Transcript',.045),line('张三',.15),line('17:09',.18),line('收到。',.21),
               line('Long stationary body below moving region',.84),line('播放',.95)]
        roi=select_roi(a,[b],lines)
        assert roi['box'][1] <= .15*900 and roi['box'][3] >= .862*900, roi
    # Crossing long equal statements provide ambiguous identity. Keep both observations.
    A,X,B,C='甲'*30,'重复长句'*10,'乙'*30,'丙'*30
    entries=lambda seq:[('我','18:15',t) for t in seq]
    blocks,issues=stitch([page(1,entries([A,X,B])),page(2,entries([B,X,C]))])
    assert [x['text'] for x in blocks]==[A,X,B,B,X,C]
    assert any(x['kind']=='ambiguous_sequence_alignment' for x in issues)
    assert all(x['uncertain_alignment'] for x in blocks[3:])
    for name,clock in [('张三','17:09'),('我','35:20')]:
        parsed=observations([line(name,.1),line(clock,.13),line('实际正文',.2)],frame(1))
        assert parsed[0]['speaker']==name and parsed[0]['page_time']==clock
        assert parsed[0]['text']=='实际正文'
    ls=normalize_lines({'lines':[{'text':'我','bbox':[.03,.106,.08,.128]},
                                {'text':'17:09','bbox':[.15,.104,.23,.126]},
                                {'text':'正文','bbox':[.03,.20,.90,.24]}]})
    parsed=observations(ls,frame(1))
    assert parsed[0]['speaker']=='我' and parsed[0]['page_time']=='17:09'
    # A visible timestamp with no OCR body is a gap, not an absent utterance.
    missing=observations([line('其他',.10),line('18:27',.13),line('我',.20),line('18:28',.23),line('下一句正文',.3)],frame(1))
    assert len(missing)==2 and missing[0]['page_time']=='18:27' and missing[0]['text']==''
    blocks,issues=stitch([(frame(1),missing)])
    assert any(x['kind']=='header_without_body' and x['page_time']=='18:27' for x in issues)
    with tempfile.TemporaryDirectory(prefix='scroll-missing-body-') as folder:
        root=Path(folder);write_texts(root,blocks,issues,'draft_requires_review')
        assert '18:27' in (root/'transcript.txt').read_text() and '正文未识别' in (root/'transcript.txt').read_text()
        from scroll_text import make_review
        fs=[dict(frame(i),roi={'method':'full_page_fallback','box':[0,0,10,10],'boundary_lines':[]},full='full.png',body='body.png') for i in range(1,20)]
        make_review(root,fs,issues,1,3)
        questions=json.loads((root/'review/questions.json').read_text())['questions']
        assert questions[0]['target']=='F000001' and '标签无正文' in questions[0]['question']
    from ocr_runtime import backend_candidates
    assert backend_candidates('rapidocr',rapid_python='/__absent_explicit_interpreter__')==[]


def verify_output(root):
    root = Path(root).resolve()
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('output contains symbolic links')
    manifest = json.loads((root / 'output-manifest.json').read_text())['files']
    actual = {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name != 'output-manifest.json'}
    if not actual == manifest:
        raise ValueError('output binding mismatch: actual == manifest')
    frames = json.loads((root / 'frames.json').read_text())['frames']
    receipt = json.loads((root / 'receipt.json').read_text())
    if not len(frames) == receipt['frame_count'] == len(list((root / 'frames').glob('frame_*.png'))):
        raise ValueError("output binding mismatch: len(frames) == receipt['frame_count'] == len(list((root / 'frames').glob('frame_*.png')))")
    if not receipt['ocr_images'] <= receipt['parameters']['max_ocr_images']:
        raise ValueError("output binding mismatch: receipt['ocr_images'] <= receipt['parameters']['max_ocr_images']")
    if not receipt['frame_count'] <= receipt['parameters']['max_frames']:
        raise ValueError("output binding mismatch: receipt['frame_count'] <= receipt['parameters']['max_frames']")
    if not receipt['source_sha256_before'] == receipt['source_sha256_after']:
        raise ValueError("output binding mismatch: receipt['source_sha256_before'] == receipt['source_sha256_after']")
    if not sha256(Path(receipt['source']).read_bytes()).hexdigest() == receipt['source_sha256_before']:
        raise ValueError("output binding mismatch: sha256(Path(receipt['source']).read_bytes()).hexdigest() == receipt['source_sha256_before']")
    for index, f in enumerate(frames):
        if not sha256((root / f['full']).read_bytes()).hexdigest() == f['full_sha256']:
            raise ValueError("output binding mismatch: sha256((root / f['full']).read_bytes()).hexdigest() == f['full_sha256']")
        if not (root / f['body']).is_file():
            raise ValueError("output binding mismatch: (root / f['body']).is_file()")
        box = f['roi']['box']
        w, h = f['size']
        if not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h):
            raise ValueError('output binding mismatch: 0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h')
        if not abs(f['sample_seconds'] - index * receipt['parameters']['interval']) < 0.0001:
            raise ValueError("output binding mismatch: abs(f['sample_seconds'] - index * receipt['parameters']['interval']) < 0.0001")
        with Image.open(root / f['full']) as full, Image.open(root / f['body']) as body:
            if not full.size[0] * full.size[1] <= receipt['parameters']['max_pixels']:
                raise ValueError("output binding mismatch: full.size[0] * full.size[1] <= receipt['parameters']['max_pixels']")
            if not full.crop(box).convert('RGB').tobytes() == body.convert('RGB').tobytes():
                raise ValueError("output binding mismatch: full.crop(box).convert('RGB').tobytes() == body.convert('RGB').tobytes()")
    review = json.loads((root / 'review/questions.json').read_text())
    ids = {f['id'] for f in frames}
    review_ids = {fid for q in review['questions'] for fid in q['frames']}
    if not (review['unique_images'] == len(review_ids) <= review['max_images'] and len(review['questions']) <= review['max_groups']):
        raise ValueError("output binding mismatch: review['unique_images'] == len(review_ids) <= review['max_images'] and len(review['questions']) <= review['max_groups']")
    if not (review_ids <= ids and review['status'] == 'not_reviewed'):
        raise ValueError("output binding mismatch: review_ids <= ids and review['status'] == 'not_reviewed'")
    # The canonical blocks must actually render to the delivered reading files.
    blocks_data = json.loads((root / 'blocks.json').read_text())
    issues_data = json.loads((root / 'issues.json').read_text())
    with tempfile.TemporaryDirectory(prefix='scroll-render-verify-') as directory:
        rendered = Path(directory)
        write_texts(rendered, blocks_data, issues_data, receipt['status'])
        for name in ('transcript.txt', 'transcript.md', 'provenance.tsv', 'uncertain.md'):
            if (root / name).read_bytes() != (rendered / name).read_bytes():
                raise ValueError('rendered output differs from canonical observations: ' + name)
    by_id = {f['id']: f for f in frames}
    if len(by_id) != len(frames):
        raise ValueError('duplicate frame id')
    raw = {}
    body_records = {}
    if (root / 'raw-ocr.jsonl').exists():
        for row in (root / 'raw-ocr.jsonl').read_text().splitlines():
            item = json.loads(row)
            relative = Path(item['input_relative'])
            if relative.is_absolute() or '..' in relative.parts or not (root / relative).is_file():
                raise ValueError('raw OCR image source missing/outside output')
            expected_path = Path(receipt['staging_path']) / relative
            if Path(item['record']['path']) != expected_path:
                raise ValueError('raw OCR path does not bind original staging input')
            stage = item['stage']
            frame_data = by_id[item['frame']]
            if stage not in ('layout', 'body'):
                raise ValueError('unknown OCR stage')
            expected_image = frame_data['full' if stage == 'layout' else 'body']
            with Image.open(root / relative) as seen, Image.open(root / expected_image) as expected:
                if pixel_hash(seen) != pixel_hash(expected):
                    raise ValueError('OCR cache image differs from frame input')
            if normalize_lines(item['record']) != item['record']['normalized_lines']:
                raise ValueError('normalized OCR differs from original engine lines')
            if item['stage'] == 'body':
                if item['frame'] in body_records:
                    raise ValueError('duplicate body OCR frame')
                body_records[item['frame']] = item['record']['normalized_lines']
                raw[item['frame']] = {x['raw_index']: x for x in item['record']['normalized_lines']}
    expected_recognized = {f['id'] for f in frames if f.get('ocr_status') == 'recognized'}
    if set(body_records) != expected_recognized:
        raise ValueError('recognized frames/body OCR coverage mismatch')
    # Recreate header parsing and sequence alignment from saved raw observations.
    # This also binds labels, per-line coordinates, timestamps and variant membership.
    rebuilt, _ = stitch([(f, observations(body_records[f['id']], f)) for f in frames if f['id'] in body_records])
    if rebuilt != blocks_data:
        raise ValueError('canonical blocks differ from raw observations/order/labels/coordinates')
    with (root / 'provenance.tsv').open() as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            if not (row['line_index'] != '' and int(row['line_index']) in raw[row['frame']]):
                raise ValueError("output binding mismatch: row['line_index'] != '' and int(row['line_index']) in raw[row['frame']]")
    blocks = json.loads((root / 'blocks.json').read_text())
    if not len(blocks) == receipt['blocks']:
        raise ValueError("output binding mismatch: len(blocks) == receipt['blocks']")
    for block in blocks:
        if not block['text'] in {v['text'] for v in block['variants']}:
            raise ValueError("output binding mismatch: block['text'] in {v['text'] for v in block['variants']}")
        for r in block['refs'] + block['header_refs']:
            if not (r['frame'] in raw and r['line_index'] in raw[r['frame']]):
                raise ValueError("output binding mismatch: r['frame'] in raw and r['line_index'] in raw[r['frame']]")
        for variant in block['variants']:
            observed = [raw[r['frame']][r['line_index']]['text'].strip() for r in variant['refs']]
            expected = variant['text'].splitlines()
            if not any((observed[k:k + len(expected)] == expected for k in range(len(observed) - len(expected) + 1))):
                raise ValueError('output binding mismatch: any((observed[k:k + len(expected)] == expected for k in range(len(observed) - len(expected) + 1)))')

def cli_fixtures():
    with tempfile.TemporaryDirectory(prefix='scroll-fixtures-') as folder:
        root=Path(folder).resolve()
        video=root/'sample.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=400x900:d=2:r=10',
                        '-c:v','libx264','-pix_fmt','yuv420p',str(video)], check=True, capture_output=True)
        helper=root/'ocr-helper'
        helper.write_text('#!'+sys.executable+'\nimport json,sys\nfor path in sys.argv[1:]:\n print(json.dumps({"path":path,"error":"","lines":[{"text":"A generated non-sensitive sentence.","bbox":[.05,.2,.9,.24],"confidence":.9}]}))\n')
        helper.chmod(0o700)
        script=Path(__file__).with_name('scroll_text.py')
        missing_pillow=subprocess.run([sys.executable,'-I','-S',str(script),'--help'],capture_output=True,text=True)
        assert missing_pillow.returncode==2 and 'Pillow' in missing_pillow.stderr
        def invoke(target, extra=(), helper_path=helper):
            return subprocess.run([sys.executable,str(script),'-i',str(video),'-o',str(target),'--engine','vision','--ocr-executable',str(helper_path),*extra],capture_output=True,text=True)
        out=root/'valid'
        p=invoke(out); assert p.returncode==0,(p.stdout,p.stderr)
        verify_output(out)
        original={str(x.relative_to(out)):x.read_bytes() for x in out.rglob('*') if x.is_file()}
        # Public verification must reject a rewritten reading draft/raw path,
        # even after a new self-authored manifest, and under Python optimization.
        for fault in ('render','raw_source','raw_lines','optimized','label','bbox','sample_time'):
            target=root/('fault-'+fault);shutil.copytree(out,target)
            if fault=='render':
                (target/'transcript.txt').write_text('FABRICATED BODY')
            elif fault in ('raw_source','raw_lines'):
                records=[json.loads(x) for x in (target/'raw-ocr.jsonl').read_text().splitlines()]
                for item in records:
                    if fault=='raw_source':item['input_relative']='missing-image.png'
                    else:item['record']['lines'][0]['text']='UNOBSERVED ENGINE TEXT'
                (target/'raw-ocr.jsonl').write_text('\n'.join(json.dumps(x) for x in records)+'\n')
            elif fault in ('label','bbox','sample_time'):
                bad_blocks=json.loads((target/'blocks.json').read_text())
                if fault=='label':bad_blocks[0]['speaker']='李四';bad_blocks[0]['page_time']='99:59'
                elif fault=='bbox':bad_blocks[0]['refs'][0]['bbox']=[.90,.90,.99,.99]
                else:bad_blocks[0]['refs'][0]['sample_seconds']=12345
                receipt=json.loads((target/'receipt.json').read_text())
                write_texts(target,bad_blocks,json.loads((target/'issues.json').read_text()),receipt['status'])
            else:
                receipt=json.loads((target/'receipt.json').read_text());receipt['source_sha256_after']='bad'
                (target/'receipt.json').write_text(json.dumps(receipt))
            manifest=json.loads((target/'output-manifest.json').read_text())
            manifest['files']={str(x.relative_to(target)):sha256(x.read_bytes()).hexdigest() for x in target.rglob('*') if x.is_file() and x.name!='output-manifest.json'}
            (target/'output-manifest.json').write_text(json.dumps(manifest))
            args=[sys.executable]+(['-O'] if fault=='optimized' else [])+[str(Path(__file__).resolve()),'--verify-output',str(target)]
            failed=subprocess.run(args,capture_output=True,text=True)
            assert failed.returncode==1 and 'SCROLL_OUTPUT_BINDING_PASSED' not in failed.stdout,(fault,failed.stdout,failed.stderr)
        # Force the crop branch while real FFmpeg/helper calls exhaust the shared budget.
        fallback=root/'body-budget-fallback'
        args=parse_args(['-i',str(video),'-o',str(fallback),'--engine','vision','--ocr-executable',str(helper),'--max-frames','2','--max-ocr-images','2'])
        def crop(*a,**kw):return {'box':[0,100,400,850],'method':'explicit','confidence':'test_fixture','boundary_lines':[]}
        with patch('scroll_text.select_roi',side_effect=crop):
            assert run(args)==3
        receipt=json.loads((fallback/'receipt.json').read_text())
        assert receipt['ocr_images']==2 and receipt['blocks']>0 and receipt['status']=='partial'
        assert any(i['kind']=='body_ocr_fallback_full_page' for i in json.loads((fallback/'issues.json').read_text()))
        verify_output(fallback)
        assert invoke(out).returncode==2
        assert original=={str(x.relative_to(out)):x.read_bytes() for x in out.rglob('*') if x.is_file()}
        link=root/'linked';link.symlink_to(out,target_is_directory=True)
        assert invoke(link).returncode==2
        assert invoke(root/'missing', helper_path=root/'absent').returncode==2
        assert not (root/'missing').exists()
        bad=root/'bad-helper'; bad.write_text('#!'+sys.executable+'\nimport sys\nprint("explicit engine failure",file=sys.stderr)\nsys.exit(7)\n');bad.chmod(0o700)
        p=invoke(root/'engine-error',helper_path=bad); assert p.returncode==3,(p.stdout,p.stderr)
        receipt=json.loads((root/'engine-error/receipt.json').read_text())
        assert receipt['status']=='failed' and receipt['ocr_errors'] and receipt['blocks']==0
        verify_output(root/'engine-error')
        malformed=root/'malformed-helper'; malformed.write_text('#!'+sys.executable+'\nprint("not JSON")\n');malformed.chmod(0o700)
        p=invoke(root/'malformed',helper_path=malformed);assert p.returncode==3
        assert json.loads((root/'malformed/receipt.json').read_text())['status']=='failed'
        # Engine budget exhausts in body stage; generate a known UI+motion fixture via patched test adapter.
        p=invoke(root/'limited', ['--max-frames','1']); assert p.returncode==3
        assert json.loads((root/'limited/receipt.json').read_text())['status']=='partial'
        verify_output(root/'limited')
        p=invoke(root/'ocr-limited', ['--max-ocr-images','1']); assert p.returncode==3
        receipt=json.loads((root/'ocr-limited/receipt.json').read_text())
        assert receipt['status']=='partial' and receipt['ocr_images']==1
        verify_output(root/'ocr-limited')
        # Atomic no-replace must refuse even a late concurrent EMPTY target.
        stage=root/'stage';stage.mkdir();(stage/'keep').write_text('payload')
        concurrent=root/'concurrent';concurrent.mkdir()
        try: promote_new(stage,concurrent)
        except OSError: pass
        else: raise AssertionError('late empty target overwritten')
        assert (stage/'keep').read_text()=='payload' and list(concurrent.iterdir())==[]
        promoted=root/'promoted'; promote_new(stage,promoted)
        assert (promoted/'keep').read_text()=='payload'
        # Real PNG-in-MOV strips expose minimum-axis rounding; inspect physical PNG pixels.
        for kind, source_size in [('tall','2x10000'), ('wide','10000x2')]:
            strip=root/(kind+'.mov')
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=white:s='+source_size+':r=1:d=1',
                            '-c:v','png','-pix_fmt','rgb24','-threads','1',str(strip)],check=True,capture_output=True)
            output=root/(kind+'-output')
            result=subprocess.run([sys.executable,str(script),'-i',str(strip),'-o',str(output),
                                   '--engine','vision','--ocr-executable',str(helper),
                                   '--max-pixels','10000','--max-frames','4'],capture_output=True,text=True)
            assert result.returncode==0,(kind,result.stdout,result.stderr)
            metadata=json.loads((output/'frames.json').read_text())
            for entry in metadata['frames']:
                with Image.open(output/entry['full']) as pixels:
                    assert pixels.width*pixels.height<=10000,(kind,pixels.size)
                    assert list(pixels.size)==entry['size']
            verify_output(output)
            bad_output=root/(kind+'-bad-budget')
            result=subprocess.run([sys.executable,str(script),'-i',str(strip),'-o',str(bad_output),
                                   '--max-pixels','9999'],capture_output=True,text=True)
            assert result.returncode==2 and not bad_output.exists()
        # Bad input never touches existing output.
        bad_video=root/'bad.mp4';bad_video.write_text('not a video')
        p=subprocess.run([sys.executable,str(script),'-i',str(bad_video),'-o',str(root/'bad-output')],capture_output=True)
        assert p.returncode==2 and not (root/'bad-output').exists()
        assert original=={str(x.relative_to(out)):x.read_bytes() for x in out.rglob('*') if x.is_file()}
        # Invalid ROI/NaN/max budgets fail without overwriting prior results.
        for extra in [['--interval','nan'],['--max-review-images','25'],['--roi','0,3,400,1']]:
            p=invoke(root/('invalid-'+str(len(extra))+extra[0].strip('-')),extra)
            assert p.returncode!=0


def _tree_digest(root):
    root = Path(root)
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def _helper(root, name):
    path = root / name
    path.write_text('#!' + sys.executable + '\nimport json,sys\nfor p in sys.argv[1:]:\n'
                    + ' print(json.dumps({"path":p,"error":"","lines":[{"text":"A generated non-sensitive sentence.",'
                      '"bbox":[.05,.2,.9,.24],"confidence":.9}]}))\n')
    path.chmod(0o700)
    return path


def budget_resume_fixtures():
    """Wall-clock budget, batch-level resume and cost estimate contracts."""
    # The pure gate is checked directly: None budget never trips, boundary is strict >.
    with patch('scroll_text.time.monotonic', return_value=100):
        assert deadline_exceeded(4, None) is False
    with patch('scroll_text.time.monotonic', return_value=10):
        assert deadline_exceeded(4, 6) is False   # elapsed 6 is not yet over a 6s budget
    with patch('scroll_text.time.monotonic', return_value=11):
        assert deadline_exceeded(4, 6) is True    # 7 > 6 trips
    with tempfile.TemporaryDirectory(prefix='scroll-budget-resume-') as folder:
        root = Path(folder).resolve()
        video = root / 'sample.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=400x900:d=2:r=10',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True, capture_output=True)
        other = root / 'other.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=s=400x900:d=2:r=10',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(other)], check=True, capture_output=True)
        script = Path(__file__).with_name('scroll_text.py')
        helper = _helper(root, 'ocr-helper')

        def invoke(target, extra=(), source=video):
            return subprocess.run([sys.executable, str(script), '-i', str(source), '-o', str(target),
                                   '--engine', 'vision', '--ocr-executable', str(helper), *extra],
                                  capture_output=True, text=True)

        # 1. Deadline stops the layout loop between batches; finished batches survive.
        # 4 unique pages, batch_size 1. Checks: layout F,F,F,trip; the body loop then
        # trips at its first check, so layout readings stand and crops fall back to them.
        cut = root / 'deadline-layout'
        args = parse_args(['-i', str(video), '-o', str(cut), '--engine', 'vision', '--ocr-executable', str(helper),
                           '--batch-size', '1', '--deadline-seconds', '9'])
        with patch('scroll_text.deadline_exceeded', side_effect=[False, False, False, True, True]):
            assert run(args) == 3
        receipt = json.loads((cut / 'receipt.json').read_text())
        assert receipt['deadline_hit'] is True and receipt['status'] == 'partial', receipt
        assert receipt['parameters']['deadline_seconds'] == 9
        issues = json.loads((cut / 'issues.json').read_text())
        hit = [x for x in issues if x['kind'] == 'deadline_exhausted']
        assert hit[0]['stage'] == 'layout' and hit[0]['covered_to_frame'] == 'F000003', issues
        layout_rows = [json.loads(x) for x in (cut / 'raw-ocr.jsonl').read_text().splitlines()
                       if json.loads(x)['stage'] == 'layout']
        assert len(layout_rows) == 3 < receipt['frame_count'], (len(layout_rows), receipt['frame_count'])
        assert 'A generated non-sensitive sentence.' in (cut / 'transcript.txt').read_text()
        assert receipt['ocr_images'] == 3, receipt
        verify_output(cut)
        # 1b. Deadline in the body stage keeps every completed layout reading.
        # Explicit ROI forces real crops: 4 layout checks pass, body batch 1 passes,
        # body check 2 trips. One crop reading is recognized; no frame loses text.
        body_cut = root / 'deadline-body'
        args = parse_args(['-i', str(video), '-o', str(body_cut), '--engine', 'vision', '--ocr-executable', str(helper),
                           '--batch-size', '1', '--deadline-seconds', '9', '--roi', '0,100,400,850'])
        with patch('scroll_text.deadline_exceeded', side_effect=[False, False, False, False, False, True]):
            assert run(args) == 3
        receipt = json.loads((body_cut / 'receipt.json').read_text())
        assert receipt['deadline_hit'] is True and receipt['status'] == 'partial', receipt
        hit = [x for x in json.loads((body_cut / 'issues.json').read_text()) if x['kind'] == 'deadline_exhausted']
        assert hit and hit[-1]['stage'] == 'body', hit
        rows = [json.loads(x) for x in (body_cut / 'raw-ocr.jsonl').read_text().splitlines()]
        assert len([x for x in rows if x['stage'] == 'layout']) == receipt['frame_count'], receipt
        assert receipt['ocr_images'] == 5, receipt
        assert 'A generated non-sensitive sentence.' in (body_cut / 'transcript.txt').read_text()
        verify_output(body_cut)
        # 1c. An invalid deadline never starts a run.
        p = invoke(root / 'deadline-invalid', ['--deadline-seconds', '0'])
        assert p.returncode == 2 and '--deadline-seconds' in p.stderr and not (root / 'deadline-invalid').exists()
        p = invoke(root / 'deadline-nan', ['--deadline-seconds', 'nan'])
        assert p.returncode == 2 and not (root / 'deadline-nan').exists()
        # 1d. A generous budget never trips and the estimate line is emitted.
        priced = root / 'estimate'
        p = invoke(priced)
        assert p.returncode == 0, (p.stdout, p.stderr)
        receipt = json.loads((priced / 'receipt.json').read_text())
        assert receipt['deadline_hit'] is False and receipt['parameters']['deadline_seconds'] is None
        line = '预计 OCR 调用 ≤ %d 张（布局 %d 帧 + 正文 ≤%d 帧；批大小 %d）' % (
            receipt['estimated_ocr_images'], receipt['frame_count'], receipt['frame_count'],
            receipt['parameters']['batch_size'])
        assert line in p.stderr, (line, p.stderr)
        assert receipt['estimated_ocr_images'] == 2*receipt['frame_count'], receipt
        # 2. Resume equivalence: a resumed run reproduces the full run's reading draft.
        partial = root / 'resume-partial'
        p = invoke(partial, ['--max-ocr-images', '1'])
        assert p.returncode == 3, (p.stdout, p.stderr)
        assert json.loads((partial / 'receipt.json').read_text())['status'] == 'partial'
        before = _tree_digest(partial)
        full = root / 'resume-full'
        t0 = time.monotonic()
        p = invoke(full)
        full_seconds = time.monotonic()-t0
        assert p.returncode == 0, (p.stdout, p.stderr)
        f_receipt = json.loads((full / 'receipt.json').read_text())
        resumed = root / 'resume-run'
        t0 = time.monotonic()
        p = invoke(resumed, ['--resume-from', str(partial)])
        resume_seconds = time.monotonic()-t0
        assert p.returncode == 0, (p.stdout, p.stderr)
        r_receipt = json.loads((resumed / 'receipt.json').read_text())
        assert r_receipt['ocr_images'] < f_receipt['ocr_images'], (r_receipt['ocr_images'], f_receipt['ocr_images'])
        assert r_receipt['resumed_readings'] >= 1, r_receipt
        assert r_receipt['resumed_skipped_malformed'] == 0 and r_receipt['resumed_skipped_mismatch'] == 0, r_receipt
        assert r_receipt['status'] == f_receipt['status'] and r_receipt['blocks'] == f_receipt['blocks'], r_receipt
        for name in ('transcript.txt', 'transcript.md', 'blocks.json', 'issues.json'):
            assert (resumed / name).read_bytes() == (full / name).read_bytes(), name
        assert any(json.loads(x).get('resumed') is True
                   for x in (resumed / 'raw-ocr.jsonl').read_text().splitlines())
        verify_output(resumed)
        assert _tree_digest(partial) == before, 'resume modified the previous staging'
        print('RESUME_SAMPLE full=%.3fs resumed=%.3fs calls %d->%d' % (
            full_seconds, resume_seconds, f_receipt['ocr_images'], r_receipt['ocr_images']), file=sys.stderr)
        # 2b. Resuming a completed full run reuses everything: zero new source calls.
        allresume = root / 'resume-all'
        p = invoke(allresume, ['--resume-from', str(full)])
        assert p.returncode == 0, (p.stdout, p.stderr)
        receipt = json.loads((allresume / 'receipt.json').read_text())
        assert receipt['ocr_images'] == 0 and receipt['resumed_readings'] > 0, receipt
        assert (allresume / 'transcript.txt').read_bytes() == (full / 'transcript.txt').read_bytes()
        assert (allresume / 'blocks.json').read_bytes() == (full / 'blocks.json').read_bytes()
        verify_output(allresume)
        # 3. Refusals: different source, engine or batch size never start a new run.
        for name, extra, source in [
                ('refuse-source', ['--resume-from', str(partial)], other),
                ('refuse-engine', ['--resume-from', str(partial), '--engine', 'rapidocr'], video),
                ('refuse-batch', ['--resume-from', str(partial), '--batch-size', '4'], video)]:
            target = root / name
            p = invoke(target, extra, source=source)
            assert p.returncode == 2, (name, p.stdout, p.stderr)
            assert '--resume-from 拒绝' in p.stderr and not target.exists(), (name, p.stderr)
        assert _tree_digest(partial) == before, 'a refused resume modified the previous staging'
        # 4. A same-named frame whose pixels changed is never reused.
        moved = root / 'resume-pixels'; shutil.copytree(partial, moved)
        with Image.open(moved / 'frames' / 'frame_000001.png') as im:
            changed = im.convert('RGB'); changed.putpixel((3, 3), (1, 2, 3)); changed.save(moved / 'frames' / 'frame_000001.png')
        repix = root / 'resume-repixel'
        p = invoke(repix, ['--resume-from', str(moved)])
        assert p.returncode == 0, (p.stdout, p.stderr)
        receipt = json.loads((repix / 'receipt.json').read_text())
        assert receipt['resumed_skipped_mismatch'] >= 1, receipt
        assert receipt['ocr_images'] >= 1, receipt
        # 5. Malformed raw lines are skipped and counted, never fatal.
        broken = root / 'resume-broken'; shutil.copytree(partial, broken)
        with (broken / 'raw-ocr.jsonl').open('a', encoding='utf-8') as f:
            f.write('not a json line\n')
            f.write(json.dumps({'frame': 'F000009', 'stage': 'layout'})+'\n')
        repaired = root / 'resume-repaired'
        p = invoke(repaired, ['--resume-from', str(broken)])
        assert p.returncode == 0, (p.stdout, p.stderr)
        receipt = json.loads((repaired / 'receipt.json').read_text())
        assert receipt['resumed_skipped_malformed'] == 2, receipt
        assert receipt['resumed_readings'] >= 1, receipt
        assert (repaired / 'transcript.txt').read_bytes() == (full / 'transcript.txt').read_bytes()
        # 6. Default behaviour is unchanged: no new flags means no resume and no deadline.
        plain = root / 'resume-plain'
        p = invoke(plain)
        assert p.returncode == 0, (p.stdout, p.stderr)
        receipt = json.loads((plain / 'receipt.json').read_text())
        assert receipt['resumed_readings'] == 0 and receipt['deadline_hit'] is False
        assert receipt['parameters']['resume_from'] is None
        assert (plain / 'transcript.txt').read_bytes() == (full / 'transcript.txt').read_bytes()


def environment_fixtures():
    packages={'normal':{'PIL':'pillow','rapidocr_onnxruntime':'rapid','onnxruntime':'user-site/onnx'},
              'isolated':{'PIL':'pillow','rapidocr_onnxruntime':'rapid','onnxruntime':None}}
    args=SimpleNamespace(engine='rapidocr',ocr_executable=None,deny_network=False,timeout=10,rapid_python=None,runtime_dir='/__scroll_fixture_no_runtime__')
    with patch.object(env_probe,'package_visibility',return_value=(packages,None)), patch.object(env_probe.shutil,'which',return_value='/tool'):
        result=env_probe.diagnose(args)
    assert result['status']=='blocked' and result['code']=='USER_SITE_PACKAGES_HIDDEN'
    assert result['hidden_by_user_site_isolation']==['onnxruntime'] and result['engine_probe']=='not_run'
    assert not result['automatic_install'] and not result['cloud_fallback']
    visible={'normal':dict(packages['normal']),'isolated':dict(packages['normal'])}
    args.engine='vision'
    for text, expected in [('LOCAL OCR PROBE 12345','ready'),('some unrelated words','blocked'),('', 'blocked')]:
        class StubEngine:
            executable='/controlled-helper'
            processes=[{'exit_code':0}]
            def __init__(self,*a,**kw):pass
            def recognize(self,paths):
                assert Path(paths[0]).is_file()
                return [{'normalized_lines':[{'text':text}]}]
        with patch.object(env_probe,'package_visibility',return_value=(visible,None)), patch.object(env_probe.shutil,'which',return_value='/tool'), patch('scroll_ocr.LocalOCR',StubEngine):
            result=env_probe.diagnose(args)
        assert result['status']==expected
    with patch.object(env_probe,'package_visibility',return_value=(visible,None)), patch.object(env_probe.shutil,'which',side_effect=lambda name: None if name=='video-screenshot-vision' else '/tool'):
        result=env_probe.diagnose(args)
    assert result['code']=='VISION_HELPER_MISSING' and result['next_action']=='compile_helper_if_swiftc_available'
    # A failed package-discovery child must block rather than fabricate availability.
    with patch.object(env_probe,'package_visibility',return_value=({},'child failed')), patch.object(env_probe.shutil,'which',return_value='/tool'):
        result=env_probe.diagnose(args)
    assert result['code']=='PYTHON_PROBE_FAILED'


def runtime_fixtures():
    import ocr_runtime as runtime
    import prepare_ocr
    from scroll_ocr import LocalOCR
    with tempfile.TemporaryDirectory(prefix='scroll-runtime-contract-') as folder:
        root=Path(folder).resolve()/'cache'
        # Ordinary preparation never creates a venv or invokes package installation.
        with patch.object(prepare_ocr.subprocess,'run',side_effect=AssertionError('implicit installation')):
            result=prepare_ocr.prepare('rapidocr',root)
        assert result['code']=='EXPLICIT_DEPENDENCY_PREPARATION_REQUIRED' and not root.exists()
        # A wrong-architecture explicit interpreter must block before any writes.
        mismatch={'version':[3,12],'architecture':'wrong-architecture'}
        proc=SimpleNamespace(returncode=0,stdout=json.dumps(mismatch))
        with patch.object(prepare_ocr.shutil,'which',return_value='/controlled-python'), patch.object(prepare_ocr.subprocess,'run',return_value=proc):
            result=prepare_ocr.prepare('rapidocr',root,True,'explicit-python')
        assert result['code']=='SUPPORTED_NATIVE_PYTHON_NOT_FOUND' and not root.exists()
        assert result['rejected'][0]['reason']=='architecture_mismatch'
        # Unknown/failed cache contents cannot be replaced by another preparation.
        directory=root/runtime.component_key('vision');directory.mkdir(parents=True)
        sentinel=directory/'unknown';sentinel.write_text('retain')
        with patch.object(prepare_ocr.sys,'platform','darwin'), patch.object(prepare_ocr.shutil,'which',return_value='/controlled-swiftc'):
            try:prepare_ocr.prepare('vision',root)
            except FileExistsError:pass
            else:raise AssertionError('unknown cache overwritten')
        assert sentinel.read_text()=='retain'
        # A ready marker must bind the executable bytes and contain only a local relative path.
        executable=directory/'helper';executable.write_text('controlled-helper');executable.chmod(0o700)
        marker={'status':'ready','component_key':runtime.component_key('vision'),'executable_relative':'helper',
                'executable_sha256':sha256(executable.read_bytes()).hexdigest()}
        path=directory/'runtime.json';path.write_text(json.dumps(marker))
        assert runtime.prepared('vision',root)==str(executable)
        executable.write_text('changed');assert runtime.prepared('vision',root) is None
        marker['executable_relative']='../outside';path.write_text(json.dumps(marker))
        assert runtime.prepared('vision',root) is None
        with patch.object(runtime.platform,'machine',return_value='other-arch'):
            assert runtime.component_key('vision')!=directory.name
    # Failed preflight is allowed to try a second backend, but each try is real recognition.
    def recognition(trial,paths):
        trial.calls+=len(paths);trial.processes.append({'engine':trial.engine,'images':len(paths),'exit_code':0})
        text='unrelated' if trial.engine=='vision' else 'LOCAL OCR PROBE 12345'
        return [{'normalized_lines':[{'text':text}]}]
    choices=lambda kind,*args: [('vision','/controlled-helper'),('rapidocr',sys.executable)] if kind=='auto' else [(kind,'/controlled-helper' if kind=='vision' else sys.executable)]
    with patch('scroll_ocr.backend_candidates',side_effect=choices),patch.object(LocalOCR,'recognize',recognition):
        engine=LocalOCR('auto')
    assert engine.engine=='rapidocr' and engine.calls==0 and engine.processes==[]
    assert len(engine.preflight_processes)==2 and engine.backend_selection_failures[0]['engine']=='vision'
    with patch('scroll_ocr.backend_candidates',return_value=[]):
        try:LocalOCR('auto')
        except OCRFailure:pass
        else:raise AssertionError('missing backends passed')


def main():
    p=argparse.ArgumentParser();p.add_argument('--case', choices=['all','core','cli'],default='all');p.add_argument('--verify-output',type=Path)
    args=p.parse_args()
    if args.verify_output:
        try:
            verify_output(args.verify_output)
        except (ValueError, OSError, KeyError, TypeError, IndexError, OCRFailure) as exc:
            print('SCROLL_OUTPUT_BINDING_FAILED: '+str(exc), file=sys.stderr)
            raise SystemExit(1)
        print('SCROLL_OUTPUT_BINDING_PASSED');return
    if args.case in ('all','core'):
        fixtures()
        audit_content_regressions()
        environment_fixtures()
        runtime_fixtures()
    if args.case in ('all','cli'):
        cli_fixtures()
        budget_resume_fixtures()
    print('SCROLL_DOMAIN_CHECKS_PASSED')

if __name__=='__main__': main()
