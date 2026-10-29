/* Execute in the HTML produced by test_svg_motion.py --browser-fixture DIR. */
async function runSvgMotionBrowserChecks(options={}){
  const svg=document.querySelector('#stage>svg'),results=[];
  function assert(condition,name,details){if(!condition)throw Error(JSON.stringify({name,details}));results.push({name,details});}
  if(options.phase==='wait'){
    const descriptor=Object.getOwnPropertyDescriptor(document,'hidden');
    let hiddenRejected=false;
    try{
      Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
      try{await measureSvgLayout(svg);}catch(e){hiddenRejected=e.message.includes('NOT_VERIFIED');}
    }finally{if(descriptor)Object.defineProperty(document,'hidden',descriptor);else delete document.hidden;}
    assert(hiddenRejected,'hidden document rejects instead of measuring',{});
    const original=requestAnimationFrame;let timedOut=false;const start=performance.now();
    try{
      window.requestAnimationFrame=()=>0;
      try{await measureSvgLayout(svg,{waitTimeoutMs:60});}catch(e){timedOut=e.message.includes('timed out');}
    }finally{window.requestAnimationFrame=original;}
    assert(timedOut && performance.now()-start<1000,'bounded paint wait rejects without a measurement',{elapsed:performance.now()-start});
    return {ok:true,checks:results.length,results};
  }
  const near=(a,b)=>Math.abs(a-b)<.1;
  function point(cue){const e=svg.querySelector(`[data-cue="${cue}"] rect`);return new DOMPoint(0,0).matrixTransform(e.getScreenCTM()).matrixTransform(svg.getScreenCTM().inverse());}
  async function frame(t){svg.pauseAnimations();svg.setCurrentTime(t);await measureSvgLayout(svg);}
  if(options.phase!=='layout') for(const width of (options.widths || [600,375])){
    document.querySelector('#stage').style.width=width+'px';
    for(const [t,x,y] of [[0,100,120],[1,105,130],[2,110,140],[3.999,100.005,120.01],[4.001,100.005,120.01],[8.001,100.005,120.01]].filter(row=>!options.times || options.times.includes(row[0]))){
      window.svgTestProgress={phase:'geometry',width,t};
      await frame(t);const a=point('relative'),b=point('absolute'),bad=point('double');
      assert(near(a.x,x)&&near(a.y,y),'relative position',{width,t,actual:[a.x,a.y],expected:[x,y]});
      assert(near(a.x,b.x)&&near(a.y,b.y),'absolute agrees with relative',{width,t,absolute:[b.x,b.y]});
      assert(near(bad.x,a.x+100)&&near(bad.y,a.y+120),'duplicate static origin produces observed double offset',{width,t,actual:[bad.x,bad.y]});
    }
  }
  if(options.phase==='geometry')return {ok:true,checks:results.length,results};
  window.svgTestProgress={phase:'layout'};
  const host=document.createElement('div');document.body.append(host);
  host.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 240" style="display:block;width:600px;height:auto"><rect x="30" y="20" width="300" height="160" fill="#ddd" data-layout-id="panel" data-layout-role="container"/><g data-layout-within="panel"><text x="48" y="50" font-size="24" data-layout-id="label">短标签</text></g><g opacity="0" data-state-group="s" data-state="a"><text x="48" y="140" font-size="24" data-layout-id="old">旧状态</text></g><g data-state-group="s" data-state="b"><text x="48" y="140" font-size="24" data-layout-id="new" data-layout-within="panel">新状态</text></g></svg>';
  const fixture=host.querySelector('svg'),label=fixture.querySelector('[data-layout-id="label"]');
  for(const width of (options.widths || [600,375])){
    window.svgTestProgress={phase:'layout',width};
    fixture.style.width=width+'px';let report=await measureSvgLayout(fixture);
    assert(report.errors.length===0,'legal containment and hidden state',{width,report});
    label.textContent='这是一段需要测量的长中文 mixed English WWW iii 123456789，不能按字符估算宽度';
    report=await measureSvgLayout(fixture);
    assert(report.errors.some(e=>e.kind==='outside-container'&&e.id==='label'),'long mixed text overflow detected',{width,errors:report.errors});
    label.textContent='';
    for(const [i,line] of ['这是一段长中文 mixed','English WWW iii 123','分行后保留原义'].entries()){
      const span=document.createElementNS('http://www.w3.org/2000/svg','tspan');span.setAttribute('x','48');span.setAttribute('dy',i?'28':'0');span.textContent=line;label.append(span);
    }
    report=await measureSvgLayout(fixture);
    assert(report.errors.length===0,'multiline legal near-positive',{width,errors:report.errors});
    fixture.querySelector('[data-state="a"]').setAttribute('opacity','1');
    report=await measureSvgLayout(fixture);
    assert(report.errors.some(e=>e.kind==='exclusive-states-both-visible'),'state annotation cannot hide visible collision',{width,errors:report.errors});
    fixture.querySelector('[data-state="a"]').setAttribute('opacity','0');label.textContent='短标签';
  }
  fixture.innerHTML='<rect x="10" y="10" width="560" height="210" data-layout-id="outer" data-layout-role="container"/><rect x="30" y="30" width="300" height="120" data-layout-id="inner" data-layout-role="container" data-layout-within="outer"/><text x="50" y="80" font-size="26" data-layout-id="nested-label" data-layout-within="inner">嵌套容器</text>';
  let nested=await measureSvgLayout(fixture);
  assert(nested.errors.length===0 && nested.exclusions.some(e=>e.containment?.join('>')==='nested-label>inner>outer'),'nested declared measured containment',{errors:nested.errors,exclusions:nested.exclusions});
  fixture.querySelector('[data-layout-id="outer"]').setAttribute('data-layout-within','inner');
  const cyclic=await measureSvgLayout(fixture);
  assert(cyclic.errors.some(e=>e.kind==='overlap-candidate'),'cyclic containment is not excluded',{errors:cyclic.errors});
  fixture.querySelector('[data-layout-id="outer"]').removeAttribute('data-layout-within');
  fixture.querySelector('[data-layout-id="inner"]').setAttribute('width','40');nested=await measureSvgLayout(fixture);
  assert(nested.errors.some(e=>e.kind==='outside-container'&&e.id==='nested-label'),'broken containment cannot be excluded',{errors:nested.errors});
  host.remove();await frame(0);
  return {ok:true,checks:results.length,results};
}
window.runSvgMotionBrowserChecks=runSvgMotionBrowserChecks;
