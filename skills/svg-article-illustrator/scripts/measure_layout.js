/* Browser-only measurement helper. Embedded in preview HTML, never in published SVG. */
async function measureSvgLayout(svg, options = {}) {
  const waitMs = options.waitTimeoutMs ?? 2000;
  if(!Number.isFinite(waitMs) || waitMs <= 0 || waitMs > 2000) throw Error('NOT_VERIFIED: waitTimeoutMs must be within (0,2000]');
  if(document.hidden) throw Error('NOT_VERIFIED: document hidden; bring the page to front and remeasure');
  await new Promise((resolve,reject) => {
    let first,second,done=false;
    const finish = error => {
      if(done)return;done=true;clearTimeout(timer);
      cancelAnimationFrame(first);cancelAnimationFrame(second);
      document.removeEventListener('visibilitychange',onVisibility);
      error ? reject(error) : resolve();
    };
    const onVisibility = () => {if(document.hidden)finish(Error('NOT_VERIFIED: document became hidden during paint wait'));};
    const timer=setTimeout(()=>finish(Error('NOT_VERIFIED: fonts/paint wait timed out; no measurement produced')),waitMs);
    document.addEventListener('visibilitychange',onVisibility);
    Promise.resolve(document.fonts.ready).then(()=>{
      if(done)return;
      if(document.hidden){onVisibility();return;}
      first=requestAnimationFrame(()=>{
        if(document.hidden){onVisibility();return;}
        second=requestAnimationFrame(()=>{
          if(document.hidden){onVisibility();return;}
          finish();
        });
      });
    }).catch(error=>finish(Error('NOT_VERIFIED: font wait failed: '+error.message)));
  });
  if(document.hidden) throw Error('NOT_VERIFIED: document hidden after paint wait');
  const threshold = options.opacityThreshold ?? 0.001;
  const tolerance = options.tolerance ?? 0.5; // CSS px
  const minTextPx = options.minTextPx ?? 12;
  const box = e => { const r = e.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}; };
  const contains = (a,b) => a.x <= b.x+tolerance && a.y <= b.y+tolerance && a.right >= b.right-tolerance && a.bottom >= b.bottom-tolerance;
  const overlap = (a,b) => Math.min(a.right,b.right)-Math.max(a.x,b.x)>tolerance && Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>tolerance;
  const visibility = e => {
    let opacity = 1;
    for(let p=e;p && p!==svg.parentElement;p=p.parentElement){
      const s=getComputedStyle(p);
      if(s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse') return {visible:false,opacity:0,reason:'display/visibility'};
      opacity *= Number(s.opacity);
    }
    return {visible:opacity>threshold,opacity,reason:opacity>threshold?'paint candidate':'computed opacity'};
  };
  const nodes = [...svg.querySelectorAll('text,[data-layout-id]')];
  const errors=[], warnings=[], exclusions=[], hidden=[], ids=new Map();
  const records=nodes.map((e,i)=>{
    const id=e.getAttribute('data-layout-id') || e.id || `text-${i}`;
    if(ids.has(id)) errors.push({kind:'duplicate-layout-id',id});
    ids.set(id,e);
    const stateHost=e.closest('[data-state-group]');
    return {e,id,rect:box(e),role:e.getAttribute('data-layout-role') || 'object',within:e.closest('[data-layout-within]')?.getAttribute('data-layout-within'),stateGroup:stateHost?.getAttribute('data-state-group'),state:stateHost?.getAttribute('data-state'),...visibility(e)};
  });
  const viewport=box(svg);
  const active=records.filter(r=>{
    if(!r.visible){hidden.push({id:r.id,opacity:r.opacity,reason:r.reason});return false;}
    if(!r.rect.width || !r.rect.height) warnings.push({kind:'zero-bounds',id:r.id});
    return true;
  });
  for(const r of active){
    if(!contains(viewport,r.rect)) errors.push({kind:'outside-viewport',id:r.id,rect:r.rect});
    if(r.within){
      const container=records.find(c=>c.id===r.within);
      if(!container || !container.visible || container.role!=='container') errors.push({kind:'invalid-container',id:r.id,within:r.within});
      else if(!contains(container.rect,r.rect)) errors.push({kind:'outside-container',id:r.id,within:r.within});
    }
    if(r.e.tagName.toLowerCase()==='text'){
      const matrix=r.e.getScreenCTM();
      const px=parseFloat(getComputedStyle(r.e).fontSize)*Math.hypot(matrix.a,matrix.b);
      r.fontPx=px;
      r.textLength=r.e.getComputedTextLength();
      r.fontFamily=getComputedStyle(r.e).fontFamily;
      if(px<minTextPx) errors.push({kind:'small-text',id:r.id,fontPx:px,minimum:minTextPx});
    }
    if(r.e.closest('[clip-path],[mask]')) warnings.push({kind:'clip-or-mask-review-required',id:r.id});
  }
  const containmentPath = (child,containerId) => {
    const path=[child.id],seen=new Set(path);let current=child;
    while(current.within){
      const parent=active.find(c=>c.id===current.within);
      if(!parent || seen.has(parent.id) || parent.role!=='container' || !contains(parent.rect,current.rect))return null;
      path.push(parent.id);seen.add(parent.id);
      current=parent;
    }
    const index=path.indexOf(containerId);
    return index>0?path.slice(0,index+1):null;
  };
  for(let i=0;i<active.length;i++) for(let j=i+1;j<active.length;j++){
    const a=active[i],b=active[j];
    if(!overlap(a.rect,b.rect))continue;
    if(a.stateGroup && a.stateGroup===b.stateGroup && a.state && b.state && a.state!==b.state){
      errors.push({kind:'exclusive-states-both-visible',a:a.id,b:b.id,opacity:[a.opacity,b.opacity]});continue;
    }
    let reason=null,containment=null;
    if(a.role==='background'||b.role==='background') reason='explicit background';
    else if((a.role==='container' && (containment=containmentPath(b,a.id))) || (b.role==='container' && (containment=containmentPath(a,b.id)))) reason='declared and measured containment';
    else if((a.e.contains(b.e)&&contains(a.rect,b.rect)) || (b.e.contains(a.e)&&contains(b.rect,a.rect))) reason='measured composite and its descendant';
    if(reason)exclusions.push({a:a.id,b:b.id,reason,...(containment?{containment}: {})});
    else errors.push({kind:'overlap-candidate',a:a.id,b:b.id});
  }
  const unmeasured=[...svg.querySelectorAll('rect,circle,ellipse,line,path,polyline,polygon,use')].filter(e=>!e.closest('defs,clipPath,mask,marker,symbol') && !e.hasAttribute('data-layout-id') && !e.closest('[data-layout-id]')).length;
  if(unmeasured)warnings.push({kind:'unannotated-graphics',count:unmeasured});
  return {waitTimeoutMs:waitMs,time:svg.getCurrentTime(),width:viewport.width,viewport,threshold,tolerance,minTextPx,errors,warnings,exclusions,hidden,items:active.map(({e,...r})=>r),scope:'actual DOM text and annotated objects; bounding-box candidates, not pixel/collision/font-availability certification; review screenshots, clipping, strokes, markers and swept paths'};
}
if(typeof window!=='undefined')window.measureSvgLayout=measureSvgLayout;
