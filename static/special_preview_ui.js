(() => {
  if (window.__AVD_SPECIAL_PREVIEW_UI__) return;
  window.__AVD_SPECIAL_PREVIEW_UI__ = true;
  const getUrl=()=>document.getElementById('url')?.value?.trim()||'';
  const special=u=>{try{const h=new URL(u).hostname.toLowerCase().replace(/^www\./,'');return h==='tiktok.com'||h.endsWith('.tiktok.com')||h==='pinterest.com'||h.endsWith('.pinterest.com')||h==='pin.it'}catch(_){return false}};
  const addThumb=async()=>{
    const result=document.getElementById('result');if(!result||!special(getUrl()))return;
    if(result.querySelector('.avd-special-thumb'))return;
    try{
      const response=await fetch('/api/media-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:getUrl()})});
      const data=await response.json();
      if(!response.ok||!data.thumbnail)return;
      const img=document.createElement('img');img.className='avd-special-thumb';img.src=data.thumbnail;img.alt='Media preview';img.loading='eager';img.style.cssText='display:block;width:min(100%,520px);max-height:360px;object-fit:cover;border-radius:12px;margin:0 0 12px;border:1px solid rgba(255,255,255,.1)';
      const gallery=result.querySelector('.social-gallery');
      const title=result.querySelector('.result-title');
      if(gallery)gallery.insertBefore(img,gallery.firstChild);else if(title)result.insertBefore(img,title);
    }catch(_){ }
  };
  const boot=()=>{const result=document.getElementById('result');if(!result)return;if(window.MutationObserver)new MutationObserver(()=>setTimeout(addThumb,80)).observe(result,{childList:true,subtree:true});setTimeout(addThumb,150)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
