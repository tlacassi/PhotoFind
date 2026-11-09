const $ = selector => document.querySelector(selector);
const photoInput = $('#photos'), selfieInput = $('#selfie');
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
function message(error) { $('#gallery-status').textContent = error.message; }
function action(text, handler) {
  const button = document.createElement('button'); button.type = 'button'; button.className = 'text-button'; button.textContent = text;
  button.addEventListener('click', () => Promise.resolve().then(handler).catch(message)); return button;
}
function card(photo, download = false) {
  const wrap = document.createElement('div'); wrap.className = download ? 'result' : 'thumb';
  const image = document.createElement('img'); image.src = download ? `/api/client/photos/${photo.id}/image?gallery_id=${encodeURIComponent(clientGalleryId)}` : `/api/photos/${photo.id}/image`; image.alt = photo.name; image.loading = 'lazy'; wrap.append(image);
  if (download) {
    const details = document.createElement('div'), name = document.createElement('span'), link = document.createElement('a');
    details.className = 'result-details'; name.textContent = photo.name; link.href = image.src;
    link.download = photo.name.replace(/\.[^.]+$/, '') + '.jpg'; link.textContent = 'Télécharger ↓'; details.append(name, link); wrap.append(details);
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
  $('#storage-usage').textContent = `Stockage des photos : ${formatBytes(user.used_bytes)} utilisés / ${user.quota_bytes === null ? 'illimité' : formatBytes(user.quota_bytes)}`;
}
async function refresh() {
  if (!selectedGallery) return;
  const photos = await api(galleryURL('/api/photos'));
  $('#count').textContent = `${photos.length} photo(s) importée(s)`;
  $('#library').replaceChildren(...photos.map(photo => card(photo)));
  $('#clear').hidden = !photos.length || !allowed('can_delete') || Boolean(selectedGallery.archived);
}
async function refreshLinks() {
  $('#links').replaceChildren();
  if (!allowed('can_share')) return;
  const links = await api(galleryURL('/api/client-links'));
  for (const link of links) {
    const item = document.createElement('li'), active = link.expires * 1000 > Date.now();
    const modeLabel = {gallery:'Galerie',search:'Selfie',both:'Galerie et selfie'}[link.mode];
    item.textContent = `${modeLabel} · ` + (active ? `Expire le ${new Date(link.expires * 1000).toLocaleString()} ` : 'Expiré ou révoqué');
    if (active) item.append(action('Révoquer', async () => {
      if (!confirm('Révoquer ce lien et ses sessions clients ?')) return;
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
  if (!selectedGallery) return;
  $('#selected-gallery-name').textContent = selectedGallery.name;
  failedUploads = []; $('#retry-upload').hidden = true; $('#upload-details').replaceChildren();
  $('#upload-status').textContent = ''; $('#share-result').hidden = true; $('#upload-progress').hidden = true;
  const owner = me.role === 'admin' || me.id === selectedGallery.owner_id;
  $('#rename-gallery').hidden = $('#archive-gallery').hidden = !owner || !allowed('can_create_galleries');
  $('#delete-gallery').hidden = !owner || !allowed('can_delete');
  $('#auto-cover').hidden = !owner || !allowed('can_create_galleries');
  $('#auto-cover').disabled = Boolean(selectedGallery.archived);
  $('#archive-gallery').textContent = selectedGallery.archived ? 'Activer la galerie' : 'Désactiver la galerie';
  photoInput.disabled = Boolean(selectedGallery.archived) || !allowed('can_upload');
  $('#generate-link').disabled = Boolean(selectedGallery.archived) || !allowed('can_share');
  $('#collaborators').hidden = !owner || !allowed('can_share');
  $('#add-member').hidden = Boolean(selectedGallery.archived);
  if (selectedGallery.archived) $('#upload-status').textContent = 'Galerie désactivée : photos conservées, import et liens désactivés.';
  await Promise.all([refresh(), refreshLinks(), refreshMembers()]);
}
function renderGalleries() {
  $('#gallery-list').replaceChildren(...galleryList.map(gallery => {
    const item = document.createElement('li'), button = document.createElement('button');
    button.className = 'gallery-row'; button.type = 'button'; button.disabled = uploading;
    if (selectedGallery?.id === gallery.id) button.setAttribute('aria-current', 'true');
    if (gallery.thumbnail_id) {
      const image = document.createElement('img'); image.src = `/api/photos/${gallery.thumbnail_id}/image`; image.alt = ''; image.loading = 'lazy'; button.append(image);
    } else { const empty = document.createElement('span'); empty.className = 'gallery-placeholder'; empty.textContent = '▧'; button.append(empty); }
    const text = document.createElement('span'), title = document.createElement('strong'), detail = document.createElement('small');
    title.textContent = gallery.name; detail.textContent = `${gallery.photo_count} photo(s)` + (gallery.archived ? ' · Désactivée' : ''); text.append(title, detail); button.append(text);
    button.addEventListener('click', async () => { if (uploading) return; try { await selectGallery(gallery.id); renderGalleries(); } catch (error) { message(error); } });
    item.append(button); return item;
  }));
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
    xhr.open('POST', `/api/photos?gallery_id=${encodeURIComponent(galleryId)}`);
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) update('transfer', event.loaded / event.total);
    };
    xhr.upload.onload = () => update('analysis', 1);
    xhr.onerror = () => reject(new Error('Connexion interrompue. Vérifiez la galerie avant de réessayer.'));
    xhr.onload = () => {
      try {
        const result = JSON.parse(xhr.responseText);
        if (xhr.status < 200 || xhr.status >= 300) throw new Error(typeof result.detail === 'string' ? result.detail : 'Import impossible.');
        if (!Array.isArray(result) || !result[0]) throw new Error('Réponse d’import invalide.');
        resolve(result[0]);
      } catch (error) { reject(error); }
    };
    xhr.send(data);
  });
}
function uploadControls(disabled) {
  for (const selector of ['#photos','#open-create-gallery','#clear','#rename-gallery','#archive-gallery','#auto-cover','#delete-gallery']) $(selector).disabled = disabled;
  for (const button of document.querySelectorAll('#library button')) button.disabled = disabled;
  renderGalleries();
}
async function uploadBatch(files) {
  if (!files.length || uploading || !selectedGallery) return;
  const galleryId = selectedGallery.id; uploading = true; stopUpload = false; failedUploads = [];
  uploadControls(true);
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
    const analysis = states.filter(item => item.phase === 'analysis').length;
    const transfer = states.filter(item => item.phase === 'transfer').length;
    $('#upload-progress').value = transferred / total * 100;
    $('#upload-status').textContent = `Transfert ${Math.round(transferred / total * 100)} % · ${transfer} envoi(s) · ${analysis} analyse(s) en cours ou en attente · ${done}/${files.length} terminée(s).` + (stopUpload ? ' Arrêt demandé : fin des photos en cours.' : '');
  }
  async function worker() {
    while (!stopUpload && cursor < states.length) {
      const state = states[cursor++];
      state.phase = 'transfer'; updateProgress();
      try {
        const result = await uploadOne(state.file, galleryId, (phase, fraction) => {
          state.phase = phase; state.fraction = fraction;
          state.row.textContent = `${state.file.name} : ${phase === 'transfer' ? `transfert ${Math.round(fraction * 100)} %` : 'analyse des visages (en cours ou en attente)'}`;
          updateProgress();
        });
        if (result.error) throw new Error(result.error);
        state.phase = 'done'; state.fraction = 1;
        state.row.textContent = `${state.file.name} : ${result.faces} visage(s) — terminé`;
      } catch (error) {
        state.phase = 'error'; state.error = error.message; state.row.textContent = `${state.file.name} : ${error.message}`;
      }
      updateProgress();
    }
  }
  try {
    await Promise.all(Array.from({length:Math.min(UPLOAD_CONCURRENCY, files.length)}, () => worker()));
    failedUploads = states.filter(state => state.phase !== 'done').map(state => state.file);
    for (const state of states.filter(state => state.phase === 'waiting')) state.row.textContent = `${state.file.name} : non envoyée (arrêt demandé)`;
    const completed = states.filter(state => state.phase === 'done').length;
    $('#upload-status').textContent = `${completed}/${files.length} photo(s) importée(s). ${failedUploads.length} restante(s) ou en erreur.` + (stopUpload ? ' Import arrêté après les photos en cours.' : '');
    await refresh(); galleryList = await api('/api/galleries'); await refreshStorage();
  } catch (error) { $('#upload-status').textContent = error.message; }
  finally {
    uploading = false; photoInput.value = ''; uploadControls(false);
    photoInput.disabled = Boolean(selectedGallery.archived) || !allowed('can_upload');
    $('#auto-cover').disabled = Boolean(selectedGallery.archived);
    $('#cancel-upload').hidden = true; $('#retry-upload').hidden = !failedUploads.length;
  }
}
if (photoInput) {
  photoInput.addEventListener('change', () => uploadBatch(Array.from(photoInput.files)));
  $('#cancel-upload').addEventListener('click', () => { stopUpload = true; $('#upload-status').textContent = 'Arrêt demandé : fin des photos déjà en cours.'; });
  $('#retry-upload').addEventListener('click', () => uploadBatch([...failedUploads]));
  $('#open-create-gallery').addEventListener('click', () => { $('#create-gallery-status').textContent = ''; $('#create-gallery-dialog').showModal(); });
  $('#cancel-create-gallery').addEventListener('click', () => $('#create-gallery-dialog').close());
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
      $('#delete-gallery-dialog').close(); await loadGalleries(); await refreshStorage();
      $('#gallery-status').textContent = result.cleanup_pending ? 'Galerie supprimée, mais le nettoyage disque a échoué. Consultez les journaux serveur.' : `Galerie supprimée, ${result.photos_deleted} photo(s) effacée(s).`;
    } catch (error) { $('#delete-gallery-status').textContent = error.message; }
    finally { button.disabled = false; }
  });
  $('#auto-cover').addEventListener('click', async () => {
    if (uploading) return;
    try { await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {cover_photo_id:null})); await loadGalleries(selectedGallery.id); $('#gallery-status').textContent = 'Miniature automatique activée : la dernière photo importée est utilisée.'; } catch (error) { message(error); }
  });
  $('#create-gallery').addEventListener('submit', async event => {
    event.preventDefault(); if (uploading) return;
    const form = event.currentTarget, button = form.querySelector('button[type=submit]'); button.disabled = true;
    try {
      const gallery = await api('/api/galleries', jsonRequest('POST', {name:new FormData(form).get('name')}));
      form.reset(); $('#create-gallery-dialog').close(); $('#gallery-status').textContent = 'Galerie créée.';
      await loadGalleries(gallery.id);
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
    try { await api(galleryURL('/api/photos'), {method:'DELETE'}); await refresh(); await refreshStorage(); } catch (error) { message(error); }
  });
  $('#add-member').addEventListener('submit', async event => {
    event.preventDefault();
    try { await api(`/api/galleries/${selectedGallery.id}/members`, jsonRequest('POST', {username:new FormData(event.target).get('username')})); event.target.reset(); await refreshMembers(); } catch (error) { message(error); }
  });
  $('#generate-link').addEventListener('click', async () => {
    $('#generate-link').disabled = true;
    try {
      const result = await api('/api/client-links', jsonRequest('POST', {gallery_id:selectedGallery.id, days:Number($('#link-days').value), mode:$('#link-mode').value}));
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
    await loadGalleries(); await refreshStorage();
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
    clientGalleryId = session.gallery_id; clientReady = session.mode !== 'gallery';
    $('#client-title').textContent = session.gallery_name;
    $('#client-description').textContent = {gallery:'Consultez et téléchargez les photos de cette galerie.',search:'Prenez ou choisissez un selfie pour retrouver vos photos.',both:'Consultez la galerie ou utilisez un selfie pour retrouver vos photos.'}[session.mode];
    $('#search-section').hidden = !clientReady; selfieInput.disabled = !clientReady;
    $('#client-gallery-title').textContent = session.gallery_name;
    if (session.mode !== 'search') {
      const photos = await api(`/api/client/photos?gallery_id=${encodeURIComponent(clientGalleryId)}`);
      $('#client-gallery').replaceChildren(...photos.map(photo => card(photo, true)));
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
      $('#search-status').textContent = results.length ? 'Recherche terminée.' : 'Aucune photo correspondante. Essayez un selfie bien éclairé.';
      $('#results').replaceChildren(...results.map(photo => card(photo, true))); $('#result-count').textContent = `${results.length} photo(s)`; $('#results-section').hidden = false;
    } catch (error) { $('#search-status').textContent = error.message; }
    finally { selfieInput.disabled = false; selfieInput.value = ''; }
  });
}
