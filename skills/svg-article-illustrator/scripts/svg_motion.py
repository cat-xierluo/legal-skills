#!/usr/bin/env python3
"""Compile seconds to SMIL, validate a conservative SVG profile, build offline preview, strip authoring metadata for local handoff.
Python standard library only. See references/timeline-tools.md for the contract.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', XLINK)
ANIM = {'animate', 'animateTransform'}
MOTION_MIN_DURATION = 3
MOTION_MAX_DURATION = 5
DRAW = {'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'path', 'text', 'use'}
TAGS = DRAW | ANIM | {'svg', 'g', 'defs', 'title', 'desc', 'tspan', 'textPath', 'clipPath', 'mask', 'marker', 'linearGradient', 'radialGradient', 'stop', 'symbol'}
ATTRS = set('pointer-events id viewBox width height x y x1 y1 x2 y2 cx cy r rx ry dx dy d points transform fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-dasharray stroke-dashoffset stroke-miterlimit opacity font-family font-size font-weight font-style text-anchor dominant-baseline alignment-baseline letter-spacing word-spacing textLength lengthAdjust pathLength preserveAspectRatio vector-effect clip-path clip-rule mask marker-start marker-mid marker-end markerWidth markerHeight markerUnits refX refY orient gradientUnits gradientTransform spreadMethod offset stop-color stop-opacity fx fy fr href role focusable style display visibility color overflow clipPathUnits maskUnits maskContentUnits startOffset attributeName values keyTimes keySplines calcMode begin dur repeatCount fill type additive'.split())
CSS = set('pointer-events display width height max-width overflow fill fill-opacity stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-dasharray stroke-dashoffset opacity font-family font-size font-weight font-style text-anchor dominant-baseline letter-spacing word-spacing visibility color'.split())
ID = re.compile(r'^[A-Za-z_][A-Za-z0-9_.:-]*$')
NUM = re.compile(r'^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$')
URL = re.compile(r'url\(\s*([\'\"]?)(#[A-Za-z_][A-Za-z0-9_.:-]*)\1\s*\)', re.I)

class Invalid(ValueError):
    pass

def require(ok, msg):
    if not ok:
        raise Invalid(msg)

def number(v):
    require(not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v), f'Expected finite number, got {v!r}')
    return float(v)

def nums(v):
    require(isinstance(v, str), 'Expected numeric string')
    p = re.split(r'[\s,]+', v.strip())
    require(p and all(NUM.fullmatch(x) for x in p), f'Invalid numeric list: {v!r}')
    return [number(float(x)) for x in p]

def fmt(n):
    return format(n, '.15g')

def tag(e):
    return e.tag.rsplit('}', 1)[-1]

def parse_svg(source):
    require(not re.search(r'<!DOCTYPE|<!ENTITY|<\?xml-stylesheet', source, re.I), 'DTD, entities and stylesheet processing instructions are unsupported')
    try:
        root = ET.fromstring(source)
    except ET.ParseError as e:
        raise Invalid(f'XML: {e}') from e
    require(root.tag == f'{{{SVG}}}svg', 'Root must be <svg xmlns="http://www.w3.org/2000/svg">')
    return root

def visible_content(e):
    if tag(e) in DRAW:
        return tag(e) != 'text' or bool(''.join(e.itertext()).strip())
    if tag(e) in {'defs', 'clipPath', 'mask', 'marker', 'symbol'}:
        return False
    return any(visible_content(c) for c in e if tag(c) not in ANIM)

def validate(source):
    errors, warnings = [], []
    try:
        root = parse_svg(source)
    except Invalid as e:
        return {'ok': False, 'errors': [str(e)], 'warnings': [], 'bytes': len(source.encode()), 'sha256': hashlib.sha256(source.encode()).hexdigest(), 'animations': 0, 'scope': 'conservative SVG/SMIL profile; no layout or platform certification'}
    ids, cues, refs, animations = {}, {}, [], []
    parents = {c: p for p in root.iter() for c in p}
    for e in root.iter():
        name = tag(e)
        label = e.get('data-cue') or e.get('id') or name
        try:
            require(e.tag.startswith('{'+SVG+'}') and name in TAGS, f'Unsupported element: {e.tag}')
            for a, value in e.attrib.items():
                local = a.rsplit('}', 1)[-1]
                require(not a.startswith('{') or a == f'{{{XLINK}}}href' or a == '{http://www.w3.org/XML/1998/namespace}space', f'Unsupported namespaced attribute: {a}')
                require(local in ATTRS or local == 'space' or local.startswith(('data-', 'aria-')), f'Unsupported attribute: {local}')
                require(not local.lower().startswith('on'), 'Event handler attributes forbidden')
                if local.startswith(('data-', 'aria-')):
                    continue
                require('\\' not in value, 'Escaped attribute/CSS values unsupported; use literal values and local #id references')
                if local == 'style':
                    require(not any(x in value for x in ('\\', '@', '/*', '*/', '<', '>')), 'Unsupported CSS syntax')
                    for declaration in value.split(';'):
                        if declaration.strip():
                            key, sep, val = declaration.partition(':')
                            require(sep and key.strip().lower() in CSS and val.strip(), f'Unsupported CSS declaration: {declaration}')
                if local == 'href':
                    require(re.fullmatch(r'#[A-Za-z_][A-Za-z0-9_.:-]*', value) is not None, 'Only local #id references allowed; external/data/file resources forbidden')
                    require(name not in ANIM, 'Animation href targeting unsupported; nest animation in its target')
                    refs.append((label, value[1:]))
                if 'url' in value.lower():
                    matches = list(URL.finditer(value))
                    require(matches and 'url' not in URL.sub('', value).lower(), f'Unsupported/external URL in {local}')
                    refs.extend((label, m.group(2)[1:]) for m in matches)
            for attr, collection in [('id', ids), ('data-cue', cues)]:
                if attr in e.attrib:
                    val = e.get(attr)
                    require(bool(val.strip()) and (attr == 'data-cue' or ID.fullmatch(val) is not None) and val not in collection, f'Invalid or duplicate {attr}: {val}')
                    collection[val] = e
            if name in ANIM:
                animations.append(e)
                p = parents.get(e)
                require(p is not None and visible_content(p), 'Empty/non-rendering animation target')
                require(not any(tag(a) in {'defs', 'clipPath', 'mask', 'marker', 'symbol'} for a in ancestors(p, parents)), 'Animation inside definitions unsupported')
                allowed = {'id', 'attributeName', 'values', 'keyTimes', 'keySplines', 'calcMode', 'begin', 'dur', 'repeatCount', 'fill', 'type', 'additive'}
                require(set(e.attrib) <= allowed, 'Unsupported animation attribute')
                require(e.get('begin') == '0s', 'Only begin="0s" supported')
                require(e.get('repeatCount') in {'1', 'indefinite'}, 'repeatCount must be 1 or indefinite')
                require(e.get('fill', 'freeze') == 'freeze', 'Only fill="freeze" supported')
                dur = e.get('dur', '')
                require(dur.endswith('s'), 'dur must use seconds')
                seconds = number_text(dur[:-1])
                require(MOTION_MIN_DURATION <= seconds <= MOTION_MAX_DURATION, f'dur must be {MOTION_MIN_DURATION}-{MOTION_MAX_DURATION} seconds for article SVG')
                mode = e.get('calcMode', 'linear')
                require(mode in {'linear', 'discrete', 'spline'}, 'Unsupported calcMode')
                values = e.get('values', '').split(';')
                times = [number_text(v) for v in e.get('keyTimes', '').split(';')]
                require(len(values) >= 2 and len(values) == len(times), 'values/keyTimes count mismatch')
                require(times[0] == 0 and times[-1] == 1 and all(0 <= x <= 1 for x in times) and all(a < b for a, b in zip(times, times[1:])), 'keyTimes must strictly increase from 0 to 1 in this profile')
                if mode == 'spline':
                    splines = e.get('keySplines', '').split(';')
                    require(len(splines) == len(values)-1, 'keySplines count mismatch')
                    for s in splines:
                        ns = nums(s)
                        require(len(ns) == 4 and all(0 <= v <= 1 for v in ns), 'keySplines must be four numbers in [0,1]')
                else:
                    require('keySplines' not in e.attrib, 'keySplines requires spline mode')
                if name == 'animate':
                    require(e.get('attributeName') == 'opacity' and 'type' not in e.attrib and 'additive' not in e.attrib, 'Only opacity attribute animation supported')
                    require(all(0 <= number_text(v) <= 1 for v in values), 'opacity outside [0,1]')
                else:
                    typ = e.get('type')
                    require(e.get('attributeName') == 'transform' and typ in {'translate', 'scale'}, 'Only translate/scale transform supported')
                    require(tag(p) == 'g' and not p.get('transform'), 'Use separate <g> layers for static transform and animation')
                    require(e.get('additive', 'replace') == 'replace', 'Additive transforms unsupported; use nested layers')
                    vectors = [nums(v) for v in values]
                    require(all(len(v) == 2 if typ == 'translate' else len(v) in {1, 2} for v in vectors), 'Invalid transform vector dimensions')
                    require(len({len(v) for v in vectors}) == 1, 'Transform dimensions must agree')
                    if typ == 'scale':
                        require(all(x > 0 for v in vectors for x in v), 'Scale must stay positive')
                if values[0].strip() != values[-1].strip() and e.get('repeatCount') == 'indefinite':
                    warnings.append(f'{label}: loop seam differs; observe reset or hide the jump intentionally')
        except (Invalid, ValueError) as exc:
            errors.append(f'{label}: {exc}')
    for origin, ref in refs:
        if ref not in ids:
            errors.append(f'{origin}: missing reference #{ref}')
    # Local <use> recursion is unsafe for a preview and invalid as an illustration.
    def walk_use(e, stack):
        require(e not in stack, 'Recursive local <use> reference')
        stack = stack | {e}
        for c in e:
            if tag(c) not in ANIM:
                walk_use(c, stack)
        if tag(e) == 'use':
            target = ids.get((e.get('href') or e.get(f'{{{XLINK}}}href') or '')[1:])
            if target is not None:
                walk_use(target, stack)
    try:
        walk_use(root, set())
        vb = nums(root.get('viewBox', ''))
        require(len(vb) == 4 and vb[2] > 0 and vb[3] > 0, 'viewBox must have four finite numbers with positive width/height')
        for p in root.iter():
            attrs = [c.get('attributeName') for c in p if tag(c) in ANIM]
            require(len(attrs) == len(set(attrs)), 'Competing animations on one target/attribute; separate layers')
        require(len({a.get('dur') for a in animations}) <= 1 and len({a.get('repeatCount') for a in animations}) <= 1, 'All animation tracks must share duration/repeatCount')
    except (Invalid, RecursionError) as e:
        errors.append(str(e))
    durations = sorted({e.get('dur') for e in animations})
    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'bytes': len(source.encode()), 'sha256': hashlib.sha256(source.encode()).hexdigest(), 'animations': len(animations), 'duration': durations[0] if len(durations) == 1 else durations, 'scope': 'conservative SVG/SMIL profile; layout, fonts, clipping and WeChat NOT_VERIFIED'}

def ancestors(e, parents):
    while e is not None:
        yield e
        e = parents.get(e)

def number_text(v):
    require(isinstance(v, str) and NUM.fullmatch(v.strip()) is not None, f'Invalid number: {v!r}')
    return number(float(v))

def checked(source):
    report = validate(source)
    require(report['ok'], '\n'.join(report['errors']))
    return parse_svg(source)

def compile_svg(source, plan):
    root = checked(source)
    require(not any(tag(e) in ANIM for e in root.iter()), 'Compiler expects a static skeleton; use the original skeleton, not prior output')
    require(isinstance(plan, dict) and set(plan) <= {'duration', 'loop', 'tracks'}, 'Unknown timeline fields')
    duration = number(plan.get('duration'))
    require(MOTION_MIN_DURATION <= duration <= MOTION_MAX_DURATION, f'duration must be {MOTION_MIN_DURATION}-{MOTION_MAX_DURATION} seconds for article SVG')
    loop = plan.get('loop', True)
    require(isinstance(loop, bool), 'loop must be boolean')
    tracks = plan.get('tracks')
    require(isinstance(tracks, list) and tracks, 'tracks must be nonempty')
    targets = {e.get('data-cue'): e for e in root.iter() if e.get('data-cue')}
    seen, inner = set(), {}
    # Validate each track before emitting the final document. Output is written only after validation.
    for track in tracks:
        require(isinstance(track, dict) and set(track) <= {'target', 'attribute', 'type', 'keyframes', 'calcMode', 'keySplines'}, 'Unknown track fields')
        cue, attr, typ = track.get('target'), track.get('attribute'), track.get('type')
        require(isinstance(cue, str) and cue in targets, f'Unknown target: {cue!r}')
        target = targets[cue]
        require(visible_content(target), f'Empty target: {cue}')
        require(attr == 'opacity' and typ is None or attr == 'transform' and typ in {'translate', 'scale'}, 'Supported: opacity, transform/translate, transform/scale')
        identity = (cue, attr, typ)
        require(identity not in seen, f'Duplicate track: {identity}')
        seen.add(identity)
        frames = track.get('keyframes')
        require(isinstance(frames, list) and len(frames) >= 2 and all(isinstance(p, list) and len(p) == 2 for p in frames), 'keyframes must contain at least two [seconds,value] pairs')
        times = [number(p[0]) for p in frames]
        require(times[0] == 0 and times[-1] == duration and all(a < b for a, b in zip(times, times[1:])), 'keyframe seconds must strictly increase from 0 to duration')
        mode = track.get('calcMode', 'linear')
        require(mode in {'linear', 'discrete', 'spline'}, 'Unsupported calcMode')
        values = []
        for _, value in frames:
            if attr == 'opacity':
                v = number(value)
                require(0 <= v <= 1, 'opacity outside [0,1]')
                values.append(fmt(v))
            else:
                vs = nums(value) if isinstance(value, str) else [number(v) for v in value] if isinstance(value, list) else [number(value)]
                require(len(vs) == 2 if typ == 'translate' else len(vs) in {1, 2}, 'Invalid transform value dimensions')
                require(typ != 'scale' or all(v > 0 for v in vs), 'scale must be positive')
                values.append(' '.join(fmt(v) for v in vs))
        attrs = {'attributeName': attr, 'begin': '0s', 'dur': fmt(duration)+'s', 'repeatCount': 'indefinite' if loop else '1', 'fill': 'freeze', 'calcMode': mode, 'values': ';'.join(values), 'keyTimes': ';'.join(fmt(t/duration) for t in times)}
        if mode == 'spline':
            splines = track.get('keySplines')
            require(isinstance(splines, list) and len(splines) == len(frames)-1, 'Supply one keySplines entry per interval')
            attrs['keySplines'] = ';'.join(s if isinstance(s, str) else ' '.join(fmt(number(v)) for v in s) for s in splines)
        else:
            require('keySplines' not in track, 'keySplines requires spline mode')
        if attr == 'transform':
            require(tag(target) == 'g', 'Transform target must be a nonempty <g>')
            host = inner.get(cue, target)
            layer = ET.Element('{'+SVG+'}g', {'data-motion-layer': typ})
            for child in list(host):
                if tag(child) not in ANIM:
                    host.remove(child)
                    layer.append(child)
            host.append(layer)
            inner[cue] = layer
            host = layer
            attrs['type'] = typ
        else:
            host = target
            target.set('opacity', values[0])
        ET.SubElement(host, '{'+SVG+'}'+('animateTransform' if attr == 'transform' else 'animate'), attrs)
        if attr == 'transform':
            host.set('data-initial-transform', f'{typ}({values[0]})')
    out = ET.tostring(root, encoding='unicode')+'\n'
    checked(out)
    return out

def publish_svg(source):
    """Create a validated standalone SVG; local serialization only, no platform write."""
    root = checked(source)
    for element in root.iter():
        for attribute in list(element.attrib):
            if attribute.startswith('data-'):
                del element.attrib[attribute]
    output = ET.tostring(root, encoding='unicode')+'\n'
    checked(output)
    return output

def write_new(path, content, force=False):
    with Path(path).open('w' if force else 'x', encoding='utf-8') as f:
        f.write(content)

def preview(source):
    root = checked(source)
    duration = max((number_text(e.get('dur')[:-1]) for e in root.iter() if tag(e) in ANIM), default=1)
    script = Path(__file__).with_name('measure_layout.js').read_text(encoding='utf-8')
    template = Path(__file__).parent.parent.joinpath('assets', 'preview.html').read_text(encoding='utf-8')
    return template.replace('<!-- SVG -->', ET.tostring(root, encoding='unicode')).replace('/* MEASURE */', script).replace('/* DURATION */ 1', fmt(duration))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='cmd', required=True)
    for cmd in ('compile', 'validate', 'preview', 'publish'):
        p = subs.add_parser(cmd)
        p.add_argument('svg', type=Path)
        if cmd == 'compile':
            p.add_argument('timeline', type=Path)
        if cmd != 'validate':
            p.add_argument('-o', '--output', type=Path, required=True)
            p.add_argument('--force', action='store_true', help='Explicitly allow replacing output')
    args = parser.parse_args()
    try:
        source = args.svg.read_text(encoding='utf-8')
        if args.cmd == 'validate':
            report = validate(source)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 1
        require(args.output.resolve() != args.svg.resolve(), 'Output must differ from input SVG')
        if args.cmd == 'compile':
            require(args.output.resolve() != args.timeline.resolve(), 'Output must differ from timeline')
            def pairs(items):
                d = {}
                for k,v in items:
                    require(k not in d, f'Duplicate JSON key: {k}')
                    d[k] = v
                return d
            plan = json.loads(args.timeline.read_text(encoding='utf-8'), object_pairs_hook=pairs)
            output = compile_svg(source, plan)
        elif args.cmd == 'publish':
            output = publish_svg(source)
        else:
            output = preview(source)
        write_new(args.output, output, args.force)
        print(json.dumps({'ok': True, 'output': str(args.output), 'bytes': len(output.encode())}, ensure_ascii=False))
        return 0
    except (Invalid, OSError, ValueError, TypeError, OverflowError, RecursionError) as e:
        print(json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
