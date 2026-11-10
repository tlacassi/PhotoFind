const $ = selector => document.querySelector(selector);
const photoInput = $('#photos'), selfieInput = $('#selfie');
const processingFiles = new Map(), pendingThumbnails = new Set();
let backgroundPolling = false, toastDismissed = false;
let clientGalleryId = null;
let me, selectedGallery, galleryList = [], failedUploads = [], stopUpload = false, uploading = false;
async function api(url, options) {
  const response = await fetch(url, options), data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Requête invalide.');
  return data;
}
const jsonRequest = (method, body) => ({method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
const allowed = permission => me?.role === 'admin' || Boolean(me?.[permission]);
const galleryURL = path => `${path}?gallery_id=${encodeURIComponent(selectedGallery.id)}`;
function photographerGalleryPath(gallery) {
  const slug = gallery.name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'galerie';
  return `/galeries/${gallery.id}/${slug}`;
}
function message(error) { $('#gallery-status').textContent = error.message; }
function action(text, handler) {
  const button = document.createElement('button'); button.type = 'button'; button.className = 'text-button'; button.textContent = text;
  button.addEventListener('click', () => Promise.resolve().then(handler).catch(message)); return button;
}
function applyGalleryColors(colors) {
  const valid = color => typeof color === 'string' && /^#[0-9a-f]{6}$/i.test(color);
  const accent = valid(colors?.accent_color) ? colors.accent_color : '#789a78';
  const background = valid(colors?.background_color) ? colors.background_color : '#f8f7f1';
  const brightness = color => .299 * parseInt(color.slice(1,3),16) + .587 * parseInt(color.slice(3,5),16) + .114 * parseInt(color.slice(5,7),16);
  const variables = {'--brand-accent':accent, '--brand-background':background, '--brand-button-ink':brightness(accent)>170 ? '#172015' : '#ffffff', '--brand-ink':brightness(background)>140 ? '#262d29' : '#f5f7f4', '--brand-link':brightness(accent)>200 ? '#465f45' : accent};
  for (const [name,value] of Object.entries(variables)) document.documentElement.style.setProperty(name,value);
  document.body.classList.toggle('gallery-themed',Boolean(colors));
}
let galleryColorDraft = null;
function card(photo, download = false, collection = [photo]) {
  const wrap = document.createElement('div'); wrap.viewerPhotos = collection; wrap.className = download ? 'result' : 'thumb';
  const image = document.createElement('img'); image.src = download ? `/api/client/photos/${photo.id}/thumbnail?gallery_id=${encodeURIComponent(clientGalleryId)}` : `/api/photos/${photo.id}/thumbnail`;
  if (!photo.thumbnail_ready) pendingThumbnails.add(image); image.alt = download ? 'Photo de la galerie' : photo.name; image.loading = 'lazy';
  const open = document.createElement('button'); open.type = 'button'; open.className = 'photo-open'; open.setAttribute('aria-label', 'Ouvrir la photo en grand'); open.append(image);
  open.addEventListener('click', () => openPhotoViewer(wrap.viewerPhotos, wrap.viewerPhotos.findIndex(item => item.id === photo.id), {client:download, galleryId:clientGalleryId})); wrap.append(open);
  if (download) {
    const details = document.createElement('div'), link = document.createElement('a');
    details.className = 'result-details'; link.href = `/api/client/photos/${photo.id}/image?gallery_id=${encodeURIComponent(clientGalleryId)}`;
    link.download = photo.name.replace(/\.[^.]+$/, '') + '.jpg'; link.textContent = 'Télécharger ↓'; details.append(link); wrap.append(details);
  } else if (allowed('can_delete') && !selectedGallery.archived) {
    const remove = action('×', async () => {
      if (!confirm(`Supprimer définitivement ${photo.name} ?`)) return;
      await api(`/api/photos/${photo.id}`, {method:'DELETE'}); await refresh(); await refreshStorage();
    }); remove.className = 'thumb-remove'; remove.setAttribute('aria-label', `Supprimer ${photo.name}`); wrap.append(remove);
  }
  if (!download && !selectedGallery.archived && allowed('can_create_galleries') && (me.role === 'admin' || me.id === selectedGallery.owner_id)) {
    const cover = action('★', async () => {
      if (uploading) return;
      await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {cover_photo_id:photo.id}));
      $('#gallery-status').textContent = 'Miniature mise à jour.';
      await loadGalleries(selectedGallery.id);
    });
    cover.className = 'thumb-cover'; cover.setAttribute('aria-label', `Utiliser ${photo.name} comme miniature`); wrap.append(cover);
  }
  return wrap;
}
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} octets`;
  if (bytes < 1024**2) return `${(bytes / 1024).toFixed(1)} Kio`;
  if (bytes < 1024**3) return `${(bytes / 1024**2).toFixed(1)} Mio`;
  return `${(bytes / 1024**3).toFixed(2)} Gio`;
}
async function refreshStorage() {
  const user = await api('/api/me');
  $('#storage-usage').textContent = `Stockage des photos : ${formatBytes(user.used_bytes)} utilisés / ${user.quota_bytes === null ? 'illimité' : formatBytes(user.quota_bytes)}` + (user.pending_bytes ? ` · ${formatBytes(user.pending_bytes)} en attente` : '');
}
const libraryCards = new Map();
let libraryContext = null;
async function refresh() {
  if (!selectedGallery) return;
  const photos = await api(galleryURL('/api/photos'));
  $('#count').textContent = `${photos.length} photo(s) importée(s)`;
  const list = $('#library'), context = `${selectedGallery.id}:${selectedGallery.archived}:${allowed('can_delete')}:${allowed('can_create_galleries')}`;
  if (context !== libraryContext) { list.replaceChildren(); libraryCards.clear(); libraryContext = context; }
  const present = new Set(photos.map(photo=>photo.id));
  for (const [id,element] of libraryCards) if (!present.has(id)) { element.remove(); libraryCards.delete(id); }
  photos.forEach((photo,index) => {
    let element = libraryCards.get(photo.id);
    if (!element) { element = card(photo,false,photos); libraryCards.set(photo.id,element); }
    element.viewerPhotos = photos;
    if (list.children[index] !== element) list.insertBefore(element,list.children[index] || null);
  });
  $('#clear').hidden = !photos.length || !allowed('can_delete') || Boolean(selectedGallery.archived);
}
async function copyClientLink(link) {
  const url = new URL(link.path, location.origin).href + '#' + link.token;
  try { await navigator.clipboard.writeText(url); $('#gallery-status').textContent = 'Lien copié.'; }
  catch (error) { $('#client-link').value = url; $('#share-result').hidden = false; $('#client-link').select(); $('#gallery-status').textContent = 'Copiez le lien sélectionné.'; }
}
async function refreshLinks() {
  $('#links').replaceChildren();
  if (!allowed('can_share')) return;
  const links = await api(galleryURL('/api/client-links'));
  for (const link of links) {
    const item = document.createElement('li'), active = link.expires * 1000 > Date.now();
    const modeLabel = {gallery:'Galerie',search:'Selfie',both:'Galerie et selfie'}[link.mode];
    item.textContent = `${link.name} · ${modeLabel} · ` + (active ? `Expire le ${new Date(link.expires * 1000).toLocaleString()} ` : 'Expiré ou révoqué ');
    if (active && link.token) {
      item.append(action('Copier', () => copyClientLink(link)));
      item.append(action('QR code', async () => {
        const response = await fetch('/api/client-qr', jsonRequest('POST', {token:link.token}));
        if (!response.ok) throw new Error('Impossible de générer le QR code.');
        const image = $('#link-qr-image');
        if (image.src.startsWith('blob:')) URL.revokeObjectURL(image.src);
        image.src = URL.createObjectURL(await response.blob()); $('#link-qr-title').textContent = link.name; $('#link-qr-dialog').showModal();
      }));
    } else if (active) item.append(document.createTextNode('Ancien lien : recréez-le pour pouvoir le recopier. '));
    item.append(action('Supprimer', async () => {
      if (!confirm('Supprimer ce lien et couper ses accès clients ?')) return;
      await api(`/api/client-links/${link.id}`, {method:'DELETE'}); $('#share-result').hidden = true; await refreshLinks();
    }));
    $('#links').append(item);
  }
}
async function refreshMembers() {
  $('#members').replaceChildren();
  if ($('#collaborators').hidden) return;
  for (const member of await api(`/api/galleries/${selectedGallery.id}/members`)) {
    const item = document.createElement('li'); item.textContent = member.username + ' ';
    item.append(action('Retirer', async () => {
      if (!confirm('Retirer cet accès ? Tous les liens clients de cette galerie seront révoqués.')) return;
      await api(`/api/galleries/${selectedGallery.id}/members/${member.id}`, {method:'DELETE'});
      $('#share-result').hidden = true; await refreshMembers(); await refreshLinks();
    })); $('#members').append(item);
  }
}
async function selectGallery(id) {
  selectedGallery = galleryList.find(gallery => gallery.id === id);
  $('#gallery-workspace').hidden = !selectedGallery;
  $('#rename-gallery').hidden = $('#archive-gallery').hidden = !selectedGallery;
  $('#gallery-branding').hidden = !selectedGallery;
  const palette = galleryColorDraft?.galleryId === selectedGallery?.id ? galleryColorDraft : selectedGallery;
  applyGalleryColors(palette);
  if (!selectedGallery) return;
  $('#selected-gallery-name').textContent = selectedGallery.name;
  if (!processingFiles.size) { failedUploads = []; $('#retry-upload').hidden = true; $('#upload-details').replaceChildren(); }
  $('#upload-status').textContent = ''; $('#share-result').hidden = true; $('#upload-progress').hidden = true;
  const owner = me.role === 'admin' || me.id === selectedGallery.owner_id;
  $('#rename-gallery').hidden = $('#archive-gallery').hidden = !owner || !allowed('can_create_galleries');
  $('#gallery-branding').hidden = !owner || !allowed('can_create_galleries');
  $('#branding-accent').value = palette.accent_color || '#789a78'; $('#branding-background').value = palette.background_color || '#f8f7f1';
  $('#reindex-gallery').hidden = !owner || !allowed('can_upload');
  $('#reindex-gallery').disabled = Boolean(selectedGallery.archived);
  $('#delete-gallery').hidden = !owner || !allowed('can_delete');
  $('#archive-gallery').textContent = selectedGallery.archived ? 'Activer la galerie' : 'Désactiver la galerie';
  photoInput.disabled = Boolean(selectedGallery.archived) || !allowed('can_upload');
  $('#generate-link').disabled = Boolean(selectedGallery.archived) || !allowed('can_share');
  $('#collaborators').hidden = !owner || !allowed('can_share');
  $('#add-member').hidden = Boolean(selectedGallery.archived);
  if (selectedGallery.archived) $('#upload-status').textContent = 'Galerie désactivée : photos conservées, import et liens désactivés.';
  await Promise.all([refresh(), refreshLinks(), refreshMembers()]);
}
const galleryElements = new Map();
function renderGalleries() {
  const list = $('#gallery-list'), present = new Set(galleryList.map(gallery=>gallery.id));
  for (const [id,entry] of galleryElements) {
    if (!present.has(id)) { entry.item.remove(); galleryElements.delete(id); }
  }
  galleryList.forEach((gallery,index) => {
    let entry = galleryElements.get(gallery.id);
    if (!entry) {
      const item = document.createElement('li'), link = document.createElement('a'), text = document.createElement('span'), title = document.createElement('strong'), detail = document.createElement('small');
      link.className = 'gallery-row'; text.append(title,detail); link.append(text); item.append(link);
      link.addEventListener('click',event=>{if(uploading)event.preventDefault();});
      entry = {item,link,title,detail,thumbnailId:undefined,media:null}; galleryElements.set(gallery.id,entry);
    }
    entry.link.href = photographerGalleryPath(gallery); entry.link.setAttribute('aria-disabled',String(uploading));
    entry.link.setAttribute('aria-current',selectedGallery?.id === gallery.id ? 'true' : 'false');
    entry.title.textContent = gallery.name;
    entry.detail.textContent = `${gallery.photo_count} photo(s)` + (gallery.pending_count ? ` · ${gallery.pending_count} à traiter` : '') + (gallery.archived ? ' · Désactivée' : '');
    const thumbnailId = gallery.thumbnail_id || null;
    if (entry.thumbnailId !== thumbnailId) {
      const media = document.createElement(thumbnailId ? 'img' : 'span');
      if (thumbnailId) {
        media.src = `/api/photos/${thumbnailId}/thumbnail`; media.alt=''; media.loading='lazy';
        if (!gallery.thumbnail_ready) pendingThumbnails.add(media);
      } else { media.className='gallery-placeholder'; media.textContent='▧'; }
      if (entry.media) entry.media.replaceWith(media); else entry.link.insertBefore(media,entry.link.firstChild);
      entry.media=media; entry.thumbnailId=thumbnailId;
    }
    if (list.children[index] !== entry.item) list.insertBefore(entry.item,list.children[index] || null);
  });
}
async function loadGalleries(preferred) {
  galleryList = await api('/api/galleries');
  if (!galleryList.length) $('#gallery-status').textContent = 'Créez votre première galerie, ou demandez un accès à son propriétaire.';
  await selectGallery(preferred); renderGalleries();
}
const UPLOAD_CONCURRENCY = 3;
function uploadOne(file, galleryId, update) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(), data = new FormData(); data.append('files', file);
    xhr.open('POST', `/api/photo-jobs?gallery_id=${encodeURIComponent(galleryId)}`);
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) update('transfer', event.loaded / event.total);
    };
    xhr.upload.onload = () => update('saving', 1);
    xhr.onerror = () => reject(new Error('Connexion interrompue. Vérifiez la galerie avant de réessayer.'));
    xhr.onload = () => {
      try {
        const result = JSON.parse(xhr.responseText);
        if (xhr.status < 200 || xhr.status >= 300) throw new Error(typeof result.detail === 'string' ? result.detail : 'Import impossible.');
        if (!result.id) throw new Error('Réponse d’import invalide.');
        resolve(result);
      } catch (error) { reject(error); }
    };
    xhr.send(data);
  });
}
function uploadControls(disabled) {
  for (const selector of ['#photos','#open-create-gallery','#clear','#rename-gallery','#archive-gallery','#delete-gallery','#reindex-gallery']) $(selector).disabled = disabled;
  for (const button of document.querySelectorAll('#library button')) button.disabled = disabled;
  renderGalleries();
}
async function uploadBatch(files) {
  if (!files.length || uploading || !selectedGallery) return;
  const galleryId = selectedGallery.id; uploading = true; stopUpload = false; failedUploads = [];
  uploadControls(true); toastDismissed = false; $('#upload-toast').hidden = false;
  $('#cancel-upload').hidden = false; $('#retry-upload').hidden = true; $('#upload-progress').hidden = false;
  $('#upload-progress').value = 0; $('#upload-details').replaceChildren();
  const states = files.map(file => {
    const row = document.createElement('li'); row.textContent = `${file.name} : en attente`; $('#upload-details').append(row);
    return {file, row, phase:'waiting', fraction:0, error:null};
  });
  let cursor = 0;
  function updateProgress() {
    const transferred = states.reduce((sum, item) => sum + item.fraction * (item.file.size || 1), 0);
    const total = states.reduce((sum, item) => sum + (item.file.size || 1), 0);
    const done = states.filter(item => item.phase === 'done').length;
    const analysis = states.filter(item => item.phase === 'saving').length;
    const transfer = states.filter(item => item.phase === 'transfer').length;
    $('#upload-progress').value = transferred / total * 100;
    $('#upload-status').textContent = `Transfert ${Math.round(transferred / total * 100)} % · ${transfer} envoi(s) · ${analysis} enregistrement(s) sur le serveur · ${done}/${files.length} terminée(s).` + (stopUpload ? ' Arrêt demandé : fin des photos en cours.' : '');
  }
  async function worker() {
    while (!stopUpload && cursor < states.length) {
      const state = states[cursor++];
      state.phase = 'transfer'; updateProgress();
      try {
        const result = await uploadOne(state.file, galleryId, (phase, fraction) => {
          state.phase = phase; state.fraction = fraction;
          state.row.textContent = `${state.file.name} : ${phase === 'transfer' ? `transfert ${Math.round(fraction * 100)} %` : 'enregistrement sur le serveur'}`;
          updateProgress();
        });
        if (result.error) throw new Error(result.error);
        state.phase = 'queued'; state.fraction = 1; state.jobId = result.id;
        processingFiles.set(result.id,state);
        state.row.textContent = `${state.file.name} : en attente de traitement sur le serveur`;
      } catch (error) {
        state.phase = 'error'; state.error = error.message; state.row.textContent = `${state.file.name} : ${error.message}`;
      }
      updateProgress();
    }
  }
  try {
    await Promise.all(Array.from({length:Math.min(UPLOAD_CONCURRENCY, files.length)}, () => worker()));
    failedUploads = states.filter(state => state.phase === 'error' || state.phase === 'waiting').map(state => state.file);
    for (const state of states.filter(state => state.phase === 'waiting')) state.row.textContent = `${state.file.name} : non envoyée (arrêt demandé)`;
    const completed = states.filter(state => state.phase === 'queued').length;
    $('#upload-status').textContent = `${completed}/${files.length} photo(s) envoyée(s). Le traitement continue sur le serveur. ${failedUploads.length} restante(s) ou en erreur.` + (stopUpload ? ' Import arrêté après les photos en cours.' : '');
    await refresh(); galleryList = await api('/api/galleries'); await refreshStorage(); await pollGalleryProcessing();
  } catch (error) { $('#upload-status').textContent = error.message; }
  finally {
    uploading = false; photoInput.value = ''; uploadControls(false);
    photoInput.disabled = Boolean(selectedGallery.archived) || !allowed('can_upload');
      $('#cancel-upload').hidden = true; $('#retry-upload').hidden = !failedUploads.length;
  }
}
async function pollGalleryProcessing() {
  if (backgroundPolling) return;
  backgroundPolling = true;
  try {
    const galleries = await api('/api/galleries');
    const latest = galleries.find(gallery => gallery.id === selectedGallery?.id);
    const changed = latest && latest.photo_count !== selectedGallery.photo_count;
    galleryList = galleries; renderGalleries();
    if (!latest) return;
    Object.assign(selectedGallery,latest);
    const status = await api(galleryURL('/api/photo-jobs'));
    $('#gallery-processing-status').textContent = status.remaining ? `Traitement en cours : ${status.remaining} photo(s) restante(s).` : '';
    const jobs = [...status.jobs];
    const ids = [...processingFiles.keys()];
    for (let index=0; index<ids.length; index+=100) {
      const extra = await api(galleryURL('/api/photo-jobs')+'&ids='+ids.slice(index,index+100).join(',')); jobs.push(...extra.jobs);
    }
    if (!processingFiles.size && !uploading && status.remaining) {
      $('#upload-details').replaceChildren(...status.jobs.filter(job => ['queued','processing'].includes(job.status)).map(job => { const row = document.createElement('li'); row.textContent = `${job.name} : ${job.status === 'processing' ? 'analyse des visages' : 'en attente sur le serveur'}`; return row; }));
    }
    for (const job of jobs) {
      const state = processingFiles.get(job.id);
      if (!state) continue;
      state.phase = job.status;
      state.row.textContent = `${job.name} : ` + ({queued:'en attente sur le serveur',processing:'analyse des visages',done:`${job.faces} visage(s) — terminé`,error:job.error}[job.status]);
      if (job.status === 'error' && state.file && !failedUploads.includes(state.file)) failedUploads.push(state.file);
      if (job.status === 'done' || job.status === 'error') processingFiles.delete(job.id);
    }
    if (!uploading && status.remaining) {
      if (!toastDismissed) $('#upload-toast').hidden = false;
      $('#upload-status').textContent = `Traitement en arrière-plan : ${status.remaining} photo(s) restante(s). Vous pouvez naviguer dans vos galeries.`;
    } else if (!uploading && processingFiles.size === 0 && !$('#upload-toast').hidden) $('#upload-status').textContent = 'Traitement terminé.' + (failedUploads.length ? ` ${failedUploads.length} photo(s) en erreur.` : '');
    $('#retry-upload').hidden = uploading || !failedUploads.length;
    if (changed) { await refresh(); await refreshStorage(); }
  } catch(error) { if (!uploading) $('#gallery-processing-status').textContent = error.message; }
  finally { backgroundPolling = false; }
}
async function refreshThumbnails() {
  for (const image of [...pendingThumbnails].slice(0,20)) {
    pendingThumbnails.delete(image);
    if (!image.isConnected) continue;
    try {
      const response = await fetch(image.src,{method:'HEAD'});
      if (!response.ok) continue;
      if (response.headers.get('X-Thumbnail-Ready') === '1') image.src += (image.src.includes('?') ? '&' : '?')+'small=1';
      else pendingThumbnails.add(image);
    } catch(error) { pendingThumbnails.add(image); }
  }
}
if (photoInput || selfieInput) setInterval(refreshThumbnails,3000);
if (photoInput) {
  let dragDepth = 0;
  const fileDrag = event => Array.from(event.dataTransfer?.types || []).includes('Files');
  document.addEventListener('dragenter', event => { if (!fileDrag(event)) return; event.preventDefault(); dragDepth++; $('#drop-overlay').hidden = false; $('#drop-message').textContent = !selectedGallery ? 'Ouvrez une galerie pour importer vos photos.' : uploading ? 'Un envoi est déjà en cours.' : 'Elles seront importées dans cette galerie.'; });
  document.addEventListener('dragover', event => { if (fileDrag(event)) event.preventDefault(); });
  document.addEventListener('dragleave', event => { if (!fileDrag(event)) return; dragDepth = Math.max(0,dragDepth-1); if (!dragDepth) $('#drop-overlay').hidden = true; });
  document.addEventListener('drop', event => { if (!fileDrag(event)) return; event.preventDefault(); dragDepth = 0; $('#drop-overlay').hidden = true; if (!selectedGallery || photoInput.disabled) { $('#gallery-status').textContent = 'Ouvrez une galerie active avec la permission d’importer.'; return; } uploadBatch(Array.from(event.dataTransfer.files)); });
  window.addEventListener('beforeunload', event => { if (uploading) { event.preventDefault(); event.returnValue = ''; } });
  $('#upload-toast-close').addEventListener('click', () => { toastDismissed = true; $('#upload-toast').hidden = true; });
  setInterval(pollGalleryProcessing,2000);
  const previewColors = () => {
    if (!selectedGallery) return;
    galleryColorDraft = {galleryId:selectedGallery.id, accent_color:$('#branding-accent').value, background_color:$('#branding-background').value};
    applyGalleryColors(galleryColorDraft);
    $('#branding-status').textContent = 'Aperçu en direct. Enregistrez pour appliquer ces couleurs aux liens clients.';
  };
  for (const selector of ['#branding-accent','#branding-background']) {
    $(selector).addEventListener('input',previewColors); $(selector).addEventListener('change',previewColors);
  }
  $('#branding-form').addEventListener('submit', async event => {
    event.preventDefault();
    const id = selectedGallery.id, colors = {accent_color:$('#branding-accent').value, background_color:$('#branding-background').value};
    for (const selector of ['#branding-accent','#branding-background','#branding-save']) $(selector).disabled = true;
    try {
      await api(`/api/galleries/${id}`, jsonRequest('PATCH',colors));
      Object.assign(selectedGallery,colors); galleryColorDraft = null; applyGalleryColors(colors);
      $('#branding-status').textContent = 'Couleurs enregistrées pour cette galerie et ses liens clients.';
    } catch(error) { $('#branding-status').textContent = error.message + ' L’aperçu reste visible, mais n’est pas enregistré.'; }
    finally { for (const selector of ['#branding-accent','#branding-background','#branding-save']) $(selector).disabled = false; }
  });
  $('#branding-logo').addEventListener('change', async event => {
    const file = event.target.files[0]; if (!file) return; const data = new FormData(); data.append('file',file); event.target.disabled = true;
    try { await api(`/api/galleries/${selectedGallery.id}/logo`, {method:'POST',body:data}); $('#branding-status').textContent = 'Logo enregistré.'; await refreshStorage(); } catch(error) { $('#branding-status').textContent = error.message; } finally { event.target.disabled = false; event.target.value = ''; }
  });
  $('#remove-branding-logo').addEventListener('click', async () => {
    try { await api(`/api/galleries/${selectedGallery.id}/logo`, {method:'DELETE'}); $('#branding-status').textContent = 'Logo PhotoFind rétabli.'; await refreshStorage(); } catch(error) { $('#branding-status').textContent = error.message; }
  });
  $('#link-qr-close').addEventListener('click', () => $('#link-qr-dialog').close());
  photoInput.addEventListener('change', () => uploadBatch(Array.from(photoInput.files)));
  $('#cancel-upload').addEventListener('click', () => { stopUpload = true; $('#upload-status').textContent = 'Arrêt demandé : fin des photos déjà en cours.'; });
  $('#retry-upload').addEventListener('click', () => uploadBatch([...failedUploads]));
  $('#open-create-gallery').addEventListener('click', () => { $('#create-gallery-status').textContent = ''; $('#create-gallery-dialog').showModal(); });
  $('#cancel-create-gallery').addEventListener('click', () => $('#create-gallery-dialog').close());
  $('#reindex-gallery').addEventListener('click', async () => {
    if (!selectedGallery || uploading) return;
    const button = $('#reindex-gallery'); button.disabled = true;
    try {
      const result = await api(`/api/galleries/${selectedGallery.id}/reindex`,{method:'POST'});
      $('#gallery-status').textContent = `${result.queued} photo(s) en réanalyse. Les fichiers restent inchangés ; les anciennes empreintes sont conservées si aucun visage supplémentaire n’est trouvé.`;
      toastDismissed = false; await pollGalleryProcessing();
    } catch(error) { message(error); } finally { button.disabled = Boolean(selectedGallery?.archived); }
  });
  $('#delete-gallery').addEventListener('click', () => {
    if (uploading || !selectedGallery) return;
    $('#delete-gallery-description').textContent = `Galerie : ${selectedGallery.name}`;
    $('#delete-gallery-status').textContent = ''; $('#delete-gallery-dialog').showModal();
  });
  $('#cancel-delete-gallery').addEventListener('click', () => $('#delete-gallery-dialog').close());
  $('#delete-gallery-form').addEventListener('submit', async event => {
    event.preventDefault(); if (uploading || !selectedGallery) return;
    const button = event.currentTarget.querySelector('button[type=submit]'); button.disabled = true;
    try {
      const result = await api(`/api/galleries/${selectedGallery.id}`, {method:'DELETE'});
      $('#delete-gallery-dialog').close(); location.assign('/');
      $('#gallery-status').textContent = result.cleanup_pending ? 'Galerie supprimée, mais le nettoyage disque a échoué. Consultez les journaux serveur.' : `Galerie supprimée, ${result.photos_deleted} photo(s) effacée(s).`;
    } catch (error) { $('#delete-gallery-status').textContent = error.message; }
    finally { button.disabled = false; }
  });
  $('#create-gallery').addEventListener('submit', async event => {
    event.preventDefault(); if (uploading) return;
    const form = event.currentTarget, button = form.querySelector('button[type=submit]'); button.disabled = true;
    try {
      const gallery = await api('/api/galleries', jsonRequest('POST', {name:new FormData(form).get('name')}));
      form.reset(); $('#create-gallery-dialog').close(); $('#gallery-status').textContent = 'Galerie créée.';
      location.assign(photographerGalleryPath(gallery));
    } catch (error) { $('#create-gallery-status').textContent = error.message; }
    finally { button.disabled = false; }
  });
  $('#rename-gallery').addEventListener('click', async () => {
    if (uploading) return;
    const name = prompt('Nom de la galerie', selectedGallery.name); if (name === null) return;
    try { await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {name})); await loadGalleries(selectedGallery.id); } catch (error) { message(error); }
  });
  $('#archive-gallery').addEventListener('click', async () => {
    if (uploading) return;
    if (!confirm(selectedGallery.archived ? 'Activer cette galerie ? Les anciens liens resteront révoqués.' : 'Désactiver cette galerie et révoquer ses liens clients ?')) return;
    try { const archived = !selectedGallery.archived; await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {archived})); await loadGalleries(selectedGallery.id); $('#gallery-status').textContent = archived ? 'Galerie désactivée : photos conservées et liens révoqués.' : 'Galerie activée. Générez un nouveau lien client si nécessaire.'; } catch (error) { message(error); }
  });
  $('#clear').addEventListener('click', async () => {
    if (!confirm('Supprimer définitivement toutes les photos de cette galerie ?')) return;
    try { await api(galleryURL('/api/photos'), {method:'DELETE'}); processingFiles.clear(); failedUploads = []; $('#upload-toast').hidden = true; await refresh(); await refreshStorage(); } catch (error) { message(error); }
  });
  $('#add-member').addEventListener('submit', async event => {
    event.preventDefault();
    try { await api(`/api/galleries/${selectedGallery.id}/members`, jsonRequest('POST', {username:new FormData(event.target).get('username')})); event.target.reset(); await refreshMembers(); } catch (error) { message(error); }
  });
  $('#generate-link').addEventListener('click', async () => {
    $('#generate-link').disabled = true;
    try {
      const result = await api('/api/client-links', jsonRequest('POST', {gallery_id:selectedGallery.id, days:Number($('#link-days').value), mode:$('#link-mode').value, name:$('#link-name').value}));
      const link = new URL(result.path, location.origin).href + '#' + result.token;
      const qr = await fetch('/api/client-qr', jsonRequest('POST', {token:result.token}));
      if (!qr.ok) throw new Error('Impossible de générer le QR code.');
      if ($('#client-qr').src.startsWith('blob:')) URL.revokeObjectURL($('#client-qr').src);
      $('#client-link').value = link; $('#test-link').href = link; $('#client-qr').src = URL.createObjectURL(await qr.blob());
      $('#share-note').textContent = `Lien privé valable ${result.expires_in_days} jour(s). Accès : ${{gallery:'galerie simple',search:'recherche par selfie',both:'galerie et selfie'}[result.mode]}. Toute personne qui possède le lien dispose de cet accès.`;
      $('#share-result').hidden = false; await refreshLinks();
    } catch (error) { message(error); } finally { $('#generate-link').disabled = false; }
  });
  $('#copy-link').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('#client-link').value); $('#copy-status').textContent = 'Lien copié.'; }
    catch (error) { $('#client-link').select(); $('#copy-status').textContent = 'Copiez le lien sélectionné.'; }
  });
  api('/api/me').then(async user => {
    me = user; $('#admin-link').hidden = user.role !== 'admin'; $('#open-create-gallery').hidden = !allowed('can_create_galleries');
    const galleryId = (location.pathname || '/').match(/^\/galeries\/([^/]+)/)?.[1];
    $('#gallery-home').hidden = Boolean(galleryId);
    await loadGalleries(galleryId); await refreshStorage(); await pollGalleryProcessing();
  }).catch(message);
}
$('#logout')?.addEventListener('click', async () => { await api('/api/logout', {method:'POST'}); location.assign('/login'); });
if (selfieInput) {
  let clientReady = false;
  const token = location.hash.slice(1); history.replaceState(null, '', location.pathname);
  const galleryInPath = location.pathname.startsWith('/client/') ? decodeURIComponent(location.pathname.slice('/client/'.length)) : null;
  selfieInput.disabled = true;
  const ready = token ? api('/api/client/redeem', jsonRequest('POST', {token, gallery_id:galleryInPath})) : api('/api/client/session' + (galleryInPath ? `?gallery_id=${encodeURIComponent(galleryInPath)}` : ''));
  ready.then(async session => {
    applyGalleryColors(session);
    if (session.logo) { const logo = document.createElement('img'); logo.className = 'gallery-logo'; logo.alt = 'Logo du photographe'; logo.src = `/api/client/logo?gallery_id=${encodeURIComponent(session.gallery_id)}`; $('#client-brand').replaceChildren(logo); }
    clientGalleryId = session.gallery_id; clientReady = session.mode !== 'gallery';
    $('#client-title').textContent = session.gallery_name;
    $('#client-description').textContent = {gallery:'Consultez et téléchargez les photos de cette galerie.',search:'Prenez ou choisissez un selfie pour retrouver vos photos.',both:'Consultez la galerie ou utilisez un selfie pour retrouver vos photos.'}[session.mode];
    $('#search-section').hidden = !clientReady; selfieInput.disabled = !clientReady;
    $('#client-gallery-title').textContent = session.gallery_name;
    if (session.mode !== 'search') {
      const photos = await api(`/api/client/photos?gallery_id=${encodeURIComponent(clientGalleryId)}`);
      $('#client-gallery').replaceChildren(...photos.map(photo => card(photo, true, photos)));
      $('#client-gallery-section').hidden = false;
      $('#client-status').textContent = photos.length ? '' : 'Cette galerie ne contient pas encore de photos.';
    }
  }).catch(error => { $('#client-status').textContent = error.message + ' Demandez un nouveau lien au photographe.'; });
  selfieInput.addEventListener('change', async () => {
    if (!clientReady || !selfieInput.files.length) return;
    const data = new FormData(); data.append('file', selfieInput.files[0]); selfieInput.disabled = true;
    $('#search-status').textContent = 'Recherche en cours…'; $('#results-section').hidden = true;
    try {
      const results = await api(`/api/search?gallery_id=${encodeURIComponent(clientGalleryId)}`, {method:'POST', body:data});
      $('#search-status').textContent = results.length ? 'Recherche terminée.' : 'Votre visage a bien été détecté, mais aucune photo correspondante n’a été trouvée dans cette galerie. Essayez un autre selfie de face si vous savez que vous y apparaissez.';
      $('#results').replaceChildren(...results.map(photo => card(photo, true, results))); $('#result-count').textContent = results.length ? `Hey, ${results.length} photo${results.length > 1 ? 's trouvées' : ' trouvée'} !` : 'Visage détecté, mais aucune photo correspondante.'; $('#results-section').hidden = false;
      $('#result-count').focus({preventScroll:true}); $('#results-section').scrollIntoView({behavior:'smooth', block:'start'});
    } catch (error) { $('#search-status').textContent = error.message; }
    finally { selfieInput.disabled = false; selfieInput.value = ''; }
  });
}
