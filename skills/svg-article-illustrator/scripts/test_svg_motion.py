#!/usr/bin/env python3
"""Standard-library regression tests; --browser-fixture DIR builds actual DOM checks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from svg_motion import SVG, Invalid, compile_svg, preview, publish_svg, validate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKELETON = ROOT.joinpath('assets/demo.skeleton.svg').read_text()
PLAN = json.loads(ROOT.joinpath('assets/demo.timeline.json').read_text())

class MotionTests(unittest.TestCase):
    def test_compile_tracks_seconds_and_layers(self):
        output = compile_svg(SKELETON, PLAN)
        root = ET.fromstring(output)
        animations = [e for e in root.iter() if e.tag.endswith(('}animate', '}animateTransform'))]
        self.assertEqual(len(animations),4)
        self.assertEqual({e.get('dur') for e in animations},{'5s'})
        for actual, expected in zip([float(v) for v in animations[0].get('keyTimes').split(';')],[0,.4,.88,1]): self.assertAlmostEqual(actual,expected,places=12)
        target = next(e for e in root.iter() if e.get('data-cue')=='cursor')
        self.assertEqual(target.get('transform'),'translate(350 220)')
        self.assertEqual(target[0].get('data-motion-layer'),'translate')
        self.assertEqual(target[0].find('{'+SVG+'}g').get('data-motion-layer'),'scale')
        self.assertEqual(validate(output)['errors'],[])

    def test_bad_keytimes_and_splines(self):
        good = compile_svg(SKELETON, PLAN)
        for value in ['0;0.9;0.8;1','0;0.5;1','0;NaN;0.8;1','0;0;0.8;1','0;0.4;0.8;0.9']:
            root=ET.fromstring(good)
            a=next(e for e in root.iter() if e.tag.endswith('}animate'))
            a.set('keyTimes',value)
            self.assertFalse(validate(ET.tostring(root,encoding='unicode'))['ok'],value)
        p=copy.deepcopy(PLAN);p['tracks'][0]['calcMode']='spline';p['tracks'][0]['keySplines']=[[.4,0,.2,1]]*3
        good=compile_svg(SKELETON,p);self.assertTrue(validate(good)['ok'])
        self.assertFalse(validate(good.replace('.4 0 .2 1','2 0 0 1').replace('0.4 0 0.2 1','2 0 0 1'))['ok'])

    def test_empty_sibling_animation_and_same_layer_transform(self):
        animation='<animateTransform attributeName="transform" type="scale" values="1;2;1" keyTimes="0;.5;1" begin="0s" dur="4s" repeatCount="indefinite"/>'
        for body in [f'<text x="20" y="30">label</text><g>{animation}</g>',f'<g transform="translate(30 40)"><circle r="10"/>{animation}</g>']:
            self.assertFalse(validate(f'<svg xmlns="{SVG}" viewBox="0 0 100 100">{body}</svg>')['ok'])
        skeleton=f'<svg xmlns="{SVG}" viewBox="0 0 100 100"><g data-cue="empty"/></svg>'
        with self.assertRaises(Invalid):compile_svg(skeleton,{'duration':4,'tracks':[{'target':'empty','attribute':'opacity','keyframes':[[0,0],[4,1]]}]})

    def test_input_contract_faults(self):
        for mutate in [lambda p:p.update(typo=True),lambda p:p.update(duration=True),lambda p:p.update(duration=float('nan')),lambda p:p.update(duration=2.9),lambda p:p.update(duration=5.1),lambda p:p['tracks'][0].update(target='missing'),lambda p:p['tracks'][0].update(calcMode='linar'),lambda p:p['tracks'][0].update(keyframes=[[0,0],[2,1],[1,0],[5,0]]),lambda p:p['tracks'].append(copy.deepcopy(p['tracks'][0]))]:
            p=copy.deepcopy(PLAN);mutate(p)
            with self.assertRaises(Invalid):compile_svg(SKELETON,p)
        bad=SKELETON.replace('data-cue="busy"','data-cue="idle"')
        with self.assertRaises(Invalid):compile_svg(bad,PLAN)

    def test_resource_reference_and_xml_faults(self):
        for body in ['<image href="https://example.test/image.png"/>','<use href="data:image/svg+xml,x"/>','<rect fill="url(https://example.test/p)"/>','<rect fill="url(#missing)"/>','<g id="x"/><g id="x"/>','<use id="a" href="#a"/>','<g style="opacity:1;animation:spin 2s"/>','<script>alert(1)</script>','<rect onclick="x()"/>','<g xmlns="urn:unsupported"/>']:
            self.assertFalse(validate(f'<svg xmlns="{SVG}" viewBox="0 0 100 100">{body}</svg>')['ok'],body)
        self.assertFalse(validate('<!DOCTYPE svg [<!ENTITY x "x">]>'+SKELETON)['ok'])
        self.assertFalse(validate('<svg>')['ok'])
        self.assertTrue(validate(ROOT.joinpath('assets/layouts.svg').read_text())['ok'])
        self.assertTrue(validate(ROOT.joinpath('assets/animations.smil').read_text())['ok'])

    def test_css_escaped_presentation_resources(self):
        for attribute in ['fill', 'stroke']:
            for value in [r'u\72l(#missing)', r'u\72l(https://example.invalid/p.svg#paint)', r'\75rl(#missing)']:
                with self.subTest(attribute=attribute, value=value):
                    source = f'<svg xmlns="{SVG}" viewBox="0 0 100 100"><rect width="10" height="10" {attribute}="{value}"/></svg>'
                    self.assertFalse(validate(source)['ok'])
        source = f'<svg xmlns="{SVG}" viewBox="0 0 100 100"><defs><linearGradient id="paint"><stop offset="0" stop-color="#123456"/></linearGradient></defs><rect width="10" height="10" fill="url(#paint)" stroke="#123456"/></svg>'
        self.assertTrue(validate(source)['ok'])

    def test_unicode_cues_and_single_run(self):
        p={'duration':4,'loop':False,'tracks':[{'target':'提示','attribute':'opacity','keyframes':[[0,1],[4,0]]}]}
        s=f'<svg xmlns="{SVG}" viewBox="0 0 100 100"><text data-cue="提示" x="10" y="30">中文 and English</text></svg>'
        out=compile_svg(s,p)
        self.assertTrue(validate(out)['ok']);self.assertIn('repeatCount="1"',out)

    def test_cli_never_clobbers_inputs_or_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'s.svg').write_text(SKELETON);(d/'t.json').write_text(json.dumps(PLAN));(d/'out.svg').write_text('keep')
            command=[sys.executable,str(HERE/'svg_motion.py'),'compile',str(d/'s.svg'),str(d/'t.json'),'-o',str(d/'out.svg')]
            r=subprocess.run(command,capture_output=True,text=True);self.assertEqual(r.returncode,1);self.assertEqual((d/'out.svg').read_text(),'keep')
            r=subprocess.run(command+['--force'],capture_output=True,text=True);self.assertEqual(r.returncode,0);self.assertTrue(validate((d/'out.svg').read_text())['ok'])
            command[-1]=str(d/'s.svg');r=subprocess.run(command+['--force'],capture_output=True,text=True);self.assertEqual(r.returncode,1);self.assertEqual((d/'s.svg').read_text(),SKELETON)
            (d/'t.json').write_text('{"duration":6,"duration":7,"tracks":[]}');command[-1]=str(d/'bad.svg');r=subprocess.run(command,capture_output=True,text=True);self.assertEqual(r.returncode,1);self.assertFalse((d/'bad.svg').exists())

    def test_publish_preserves_native_svg_and_removes_only_metadata(self):
        # Add a real reference to exercise ID preservation in animated output.
        skeleton = SKELETON.replace('<rect width="600"', '<defs><linearGradient id="publish-paint"><stop offset="0" stop-color="#123456"/></linearGradient></defs><rect fill="url(#publish-paint)" width="600"', 1).replace(' fill="#edf3f8"', '', 1)
        compiled = compile_svg(skeleton, PLAN)
        output = publish_svg(compiled)
        before, after = ET.fromstring(compiled), ET.fromstring(output)
        def semantic_tree(root, strip_metadata=False):
            return [(e.tag, {k:v for k,v in e.attrib.items() if not (strip_metadata and k.startswith('data-'))}, e.text, e.tail) for e in root.iter()]
        self.assertEqual(semantic_tree(before, True), semantic_tree(after))
        self.assertFalse(any(k.startswith('data-') for e in after.iter() for k in e.attrib))
        animations = lambda root: [(e.tag, dict(e.attrib)) for e in root.iter() if e.tag in {f'{{{SVG}}}animate', f'{{{SVG}}}animateTransform'}]
        self.assertEqual(animations(before), animations(after))
        self.assertEqual(len(animations(after)), 4)
        self.assertEqual(after.get('viewBox'), before.get('viewBox'))
        self.assertTrue(any(e.get('id') == 'publish-paint' for e in after.iter()))
        self.assertTrue(validate(output)['ok'])
        self.assertEqual(publish_svg(output), output)
        self.assertTrue(validate(publish_svg(ROOT.joinpath('assets/layouts.svg').read_text()))['ok'])

    def test_publish_cli_protection_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); source = d/'compiled.svg'; target = d/'published.svg'
            compiled = compile_svg(SKELETON, PLAN); source.write_text(compiled)
            command = [sys.executable, str(HERE/'svg_motion.py'), 'publish', str(source), '-o', str(target)]
            run = lambda args: subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(run(command).returncode, 0)
            expected = target.read_text(); self.assertTrue(validate(expected)['ok'])
            target.write_text('keep'); self.assertEqual(run(command).returncode, 1); self.assertEqual(target.read_text(), 'keep')
            self.assertEqual(run(command+['--force']).returncode, 0); self.assertEqual(target.read_text(), expected)
            same_input = command[:-1]+[str(source),'--force']
            self.assertEqual(run(same_input).returncode, 1); self.assertEqual(source.read_text(), compiled)
            for invalid in [compiled.replace('keyTimes="0;', 'keyTimes="0.9;', 1), '<svg>', compiled.replace('<title', '<script', 1).replace('</title>', '</script>', 1), compiled.replace('fill="#fff"', 'fill="url(https://example.invalid/paint)"', 1), compiled.replace('fill="#fff"', r'fill="u\72l(#missing)"', 1)]:
                source.write_text(invalid); target.unlink()
                self.assertEqual(run(command).returncode, 1)
                self.assertFalse(target.exists())
                target.write_text('protected'); self.assertEqual(run(command+['--force']).returncode, 1); self.assertEqual(target.read_text(), 'protected')
            source.write_text(compiled); self.assertEqual(source.read_text(), compiled)

    def test_preview_contains_controls_but_svg_has_no_script(self):
        out=compile_svg(SKELETON,PLAN)
        self.assertFalse(any(e.tag.endswith('}script') for e in ET.fromstring(out).iter()))
        html=preview(out)
        for control in ['scrub','play','pause','reset','width','measure']:
            self.assertIn(f'id="{control}"',html)
        self.assertNotIn('<!-- SVG -->',html)
        self.assertNotIn('/* MEASURE */',html)
        self.assertIn('duration=5',html)

    def test_duration_contract_accepts_three_to_five_and_rejects_outside(self):
        skeleton=f'<svg xmlns="{SVG}" viewBox="0 0 100 100"><g data-cue="state"><rect width="20" height="20"/></g></svg>'
        for duration in (3,4,5):
            p={'duration':duration,'tracks':[{'target':'state','attribute':'opacity','keyframes':[[0,0],[duration/2,1],[duration,0]]}]}
            out=compile_svg(skeleton,p)
            self.assertEqual(validate(out)['duration'],f'{duration}s')
        for duration in (2.9,5.1):
            p={'duration':duration,'tracks':[{'target':'state','attribute':'opacity','keyframes':[[0,0],[duration/2,1],[duration,0]]}]}
            with self.assertRaises(Invalid):compile_svg(skeleton,p)
            manual=f'<svg xmlns="{SVG}" viewBox="0 0 100 100"><g><rect width="20" height="20"/><animate attributeName="opacity" values="0;1;0" keyTimes="0;.5;1" begin="0s" dur="{duration}s" repeatCount="indefinite"/></g></svg>'
            self.assertFalse(validate(manual)['ok'])


def browser_fixture(directory):
    directory.mkdir(parents=True,exist_ok=False)
    s=f'''<svg xmlns="{SVG}" viewBox="0 0 600 360">
    <rect width="600" height="360" fill="#eef3f7" data-layout-id="bg" data-layout-role="background"/>
    <g data-cue="relative" transform="translate(100 120)"><rect width="16" height="16" fill="#17609a"/></g>
    <g data-cue="absolute"><rect width="16" height="16" fill="#3a8a60"/></g>
    <g data-cue="double" transform="translate(100 120)"><rect width="16" height="16" fill="#b33a38"/></g>
    <text x="24" y="40" font-size="24">蓝：相对位移；绿：绝对坐标；红：重复定位反例</text>
    </svg>'''
    p={'duration':4,'tracks':[
    {'target':'relative','attribute':'transform','type':'translate','keyframes':[[0,'0 0'],[2,'10 20'],[4,'0 0']]},
    {'target':'absolute','attribute':'transform','type':'translate','keyframes':[[0,'100 120'],[2,'110 140'],[4,'100 120']]},
    {'target':'double','attribute':'transform','type':'translate','keyframes':[[0,'100 120'],[2,'110 140'],[4,'100 120']]}]}
    out=compile_svg(s,p)
    (directory/'skeleton.svg').write_text(s);(directory/'timeline.json').write_text(json.dumps(p));(directory/'compiled.svg').write_text(out)
    checks=HERE.joinpath('browser_checks.js').read_text()
    (directory/'preview.html').write_text(preview(out).replace('</html>','<script>'+checks+'</script></html>'))
    print(json.dumps({'fixture':str(directory/'preview.html')}))

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--browser-fixture':browser_fixture(Path(sys.argv[2]))
    else:unittest.main()
