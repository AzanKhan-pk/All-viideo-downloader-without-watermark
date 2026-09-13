(() => {
  if (window.__AVD_SPECIAL_PREVIEW_UI__) return;
  window.__AVD_SPECIAL_PREVIEW_UI__ = true;
  const getUrl=()=>document.getElementById('url')?.value?.trim()||'';
  const special=u=>{try{const h=new URL(u).hostname.toLowerCase().replace(/^www\./,'');return h==='tiktok.com'||h.endsWith('.tiktok.com')||h==='pinterest.com'||h.endsWith('.pinterest.com')||h==='pin.it'}catch(_){return false}};
  async function addPreview(){
    const result=document.getElementById('result');
    if(!result||!special(getUrl())||result.querySelector('.thumb'))return;
    const title=result.querySelector('.result-title');
    if(!title)return;
    try{
      const response=await fetch('/api/media-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:getUrl()})});
      const data=await response.json();
      if(!response.ok||!data.thumbnail)return;
      const img=document.createElement('img');img.className='thumb';img.src=data.thumbnail;img.alt='Media thumbnail';img.loading='eager';
      result.insertBefore(img,title);
    }catch(_){ }
  }
  const boot=()=>{const result=document.getElementById('result');if(!result)return;if(window.MutationObserver)new MutationObserver(()=>setTimeout(addPreview,30)).observe(result,{childList:true,subtree:true});setTimeout(addPreview,100)};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
