#!/usr/bin/env python3
"""Independent non-sensitive scrolling extraction regressions, generated fixtures."""
from __future__ import annotations
import argparse
import csv
from types import SimpleNamespace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from PIL import Image, ImageDraw
from scroll_text import (select_roi, observations, stitch, pixel_hash, promote_new,
                         resolve_new_output, parse_args, run, write_texts)
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


def verify_output(root):
    manifest=json.loads((root/'output-manifest.json').read_text())['files']
    actual={str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name!='output-manifest.json'}
    assert actual==manifest
    frames=json.loads((root/'frames.json').read_text())['frames']
    receipt=json.loads((root/'receipt.json').read_text())
    assert len(frames)==receipt['frame_count']==len(list((root/'frames').glob('frame_*.png')))
    assert receipt['ocr_images']<=receipt['parameters']['max_ocr_images']
    assert receipt['frame_count']<=receipt['parameters']['max_frames']
    assert receipt['source_sha256_before']==receipt['source_sha256_after']
    assert sha256(Path(receipt['source']).read_bytes()).hexdigest()==receipt['source_sha256_before']
    for index,f in enumerate(frames):
        assert sha256((root/f['full']).read_bytes()).hexdigest()==f['full_sha256']
        assert (root/f['body']).is_file()
        box=f['roi']['box'];w,h=f['size']
        assert 0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h
        assert abs(f['sample_seconds']-index*receipt['parameters']['interval'])<.0001
        with Image.open(root/f['full']) as full,Image.open(root/f['body']) as body:
            assert full.size[0]*full.size[1]<=receipt['parameters']['max_pixels']
            assert full.crop(box).convert('RGB').tobytes()==body.convert('RGB').tobytes()
    review=json.loads((root/'review/questions.json').read_text())
    ids={f['id'] for f in frames}
    review_ids={fid for q in review['questions'] for fid in q['frames']}
    assert review['unique_images']==len(review_ids)<=review['max_images'] and len(review['questions'])<=review['max_groups']
    assert review_ids<=ids and review['status']=='not_reviewed'
    raw={}
    if (root/'raw-ocr.jsonl').exists():
        for row in (root/'raw-ocr.jsonl').read_text().splitlines():
            item=json.loads(row)
            if item['stage']=='body':
                raw[item['frame']]={x['raw_index']:x for x in item['record']['normalized_lines']}
    with (root/'provenance.tsv').open() as stream:
        for row in csv.DictReader(stream,delimiter='\t'):
            assert row['line_index'] != '' and int(row['line_index']) in raw[row['frame']]
    blocks=json.loads((root/'blocks.json').read_text())
    assert len(blocks)==receipt['blocks']
    for block in blocks:
        assert block['text'] in {v['text'] for v in block['variants']}
        for r in block['refs']+block['header_refs']:
            assert r['frame'] in raw and r['line_index'] in raw[r['frame']]
        for variant in block['variants']:
            observed=[raw[r['frame']][r['line_index']]['text'].strip() for r in variant['refs']]
            # Variants may contain repeated observations from identical samples; original text
            # must appear as a contiguous actually observed line sequence, not a rewrite.
            expected=variant['text'].splitlines()
            assert any(observed[k:k+len(expected)]==expected for k in range(len(observed)-len(expected)+1))


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
        # Bad input never touches existing output.
        bad_video=root/'bad.mp4';bad_video.write_text('not a video')
        p=subprocess.run([sys.executable,str(script),'-i',str(bad_video),'-o',str(root/'bad-output')],capture_output=True)
        assert p.returncode==2 and not (root/'bad-output').exists()
        assert original=={str(x.relative_to(out)):x.read_bytes() for x in out.rglob('*') if x.is_file()}
        # Invalid ROI/NaN/max budgets fail without overwriting prior results.
        for extra in [['--interval','nan'],['--max-review-images','25'],['--roi','0,3,400,1']]:
            p=invoke(root/('invalid-'+str(len(extra))+extra[0].strip('-')),extra)
            assert p.returncode!=0


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
        verify_output(args.verify_output);print('SCROLL_OUTPUT_BINDING_PASSED');return
    if args.case in ('all','core'):
        fixtures()
        environment_fixtures()
        runtime_fixtures()
    if args.case in ('all','cli'): cli_fixtures()
    print('SCROLL_DOMAIN_CHECKS_PASSED')

if __name__=='__main__': main()
