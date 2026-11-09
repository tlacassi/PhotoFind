const $ = selector => document.querySelector(selector);
const photoInput = $('#photos'), selfieInput = $('#selfie');
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
  const image = document.createElement('img'); image.src = download ? `/api/client/photos/${photo.id}/image` : `/api/photos/${photo.id}/image`; image.alt = photo.name; image.loading = 'lazy'; wrap.append(image);
  if (download) {
    const details = document.createElement('div'), name = document.createElement('span'), link = document.createElement('a');
    details.className = 'result-details'; name.textContent = photo.name; link.href = image.src;
    link.download = photo.name.replace(/\.[^.]+$/, '') + '.jpg'; link.textContent = 'Télécharger ↓'; details.append(name, link); wrap.append(details);
  } else if (allowed('can_delete') && !selectedGallery.archived) {
    const remove = action('×', async () => {
      if (!confirm(`Supprimer définitivement ${photo.name} ?`)) return;
      await api(`/api/photos/${photo.id}`, {method:'DELETE'}); await refresh();
    }); remove.className = 'thumb-remove'; remove.setAttribute('aria-label', `Supprimer ${photo.name}`); wrap.append(remove);
  }
  if (!download && !selectedGallery.archived && allowed('can_create_galleries') && (me.role === 'admin' || me.id === selectedGallery.owner_id)) {
    const cover = action('★', async () => {
      await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {cover_photo_id:photo.id}));
      $('#gallery-status').textContent = 'Miniature mise à jour.';
      await loadGalleries(selectedGallery.id);
    });
    cover.className = 'thumb-cover'; cover.setAttribute('aria-label', `Utiliser ${photo.name} comme miniature`); wrap.append(cover);
  }
  return wrap;
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
    item.textContent = active ? `Expire le ${new Date(link.expires * 1000).toLocaleString()} ` : 'Expiré ou révoqué';
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
  $('#auto-cover').hidden = !owner || !allowed('can_create_galleries');
  $('#auto-cover').disabled = Boolean(selectedGallery.archived);
  $('#archive-gallery').textContent = selectedGallery.archived ? 'Restaurer la galerie' : 'Archiver la galerie';
  photoInput.disabled = Boolean(selectedGallery.archived) || !allowed('can_upload');
  $('#generate-link').disabled = Boolean(selectedGallery.archived) || !allowed('can_share');
  $('#collaborators').hidden = !owner || !allowed('can_share');
  $('#add-member').hidden = Boolean(selectedGallery.archived);
  if (selectedGallery.archived) $('#upload-status').textContent = 'Galerie archivée : photos conservées, import et liens désactivés.';
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
    title.textContent = gallery.name; detail.textContent = `${gallery.photo_count} photo(s)` + (gallery.archived ? ' · Archivée' : ''); text.append(title, detail); button.append(text);
    button.addEventListener('click', async () => { if (uploading) return; try { await selectGallery(gallery.id); renderGalleries(); } catch (error) { message(error); } });
    item.append(button); return item;
  }));
}
async function loadGalleries(preferred) {
  galleryList = await api('/api/galleries');
  if (!galleryList.length) $('#gallery-status').textContent = 'Créez votre première galerie, ou demandez un accès à son propriétaire.';
  await selectGallery(preferred); renderGalleries();
}
function uploadOne(file, index, total, galleryId) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(), data = new FormData(); data.append('files', file);
    xhr.open('POST', `/api/photos?gallery_id=${encodeURIComponent(galleryId)}`);
    xhr.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      $('#upload-progress').value = (index - 1 + event.loaded / event.total) / total * 100;
      $('#upload-status').textContent = `Photo ${index}/${total} : transfert ${Math.round(100 * event.loaded / event.total)} % — ${file.name}`;
    };
    xhr.upload.onload = () => { $('#upload-status').textContent = `Photo ${index}/${total} : analyse des visages — ${file.name}`; };
    xhr.onerror = () => reject(new Error('Connexion interrompue. Vérifiez la galerie avant de réessayer.'));
    xhr.onload = () => {
      try {
        const result = JSON.parse(xhr.responseText);
        if (xhr.status < 200 || xhr.status >= 300) throw new Error(typeof result.detail === 'string' ? result.detail : 'Import impossible.');
        resolve(result[0]);
      } catch (error) { reject(error); }
    };
    xhr.send(data);
  });
}
async function uploadBatch(files) {
  if (!files.length || uploading || !selectedGallery) return;
  const galleryId = selectedGallery.id; uploading = true; stopUpload = false; failedUploads = [];
  for (const selector of ['#photos','#open-create-gallery','#clear','#rename-gallery','#archive-gallery']) $(selector).disabled = true;
  renderGalleries();
  $('#cancel-upload').hidden = false; $('#retry-upload').hidden = true; $('#upload-progress').hidden = false;
  $('#upload-progress').value = 0; $('#upload-details').replaceChildren();
  let completed = 0;
  try {
    for (const [index, file] of files.entries()) {
      if (stopUpload) { failedUploads.push(...files.slice(index)); break; }
      let result;
      try { result = await uploadOne(file, index + 1, files.length, galleryId); }
      catch (error) { result = {name:file.name, error:error.message}; }
      if (result.error) failedUploads.push(file); else completed++;
      const item = document.createElement('li');
      item.textContent = `${file.name} : ${result.error || `${result.faces} visage(s) — terminé`}`; $('#upload-details').append(item);
      $('#upload-progress').value = (index + 1) / files.length * 100;
    }
    $('#upload-status').textContent = `${completed}/${files.length} photo(s) importée(s). ${failedUploads.length} restante(s) ou en erreur.` + (stopUpload ? ' Import arrêté après la photo en cours.' : '');
    await refresh();
    galleryList = await api('/api/galleries');
  } catch (error) { $('#upload-status').textContent = error.message; }
  finally {
    uploading = false; photoInput.value = '';
    for (const selector of ['#photos','#open-create-gallery','#clear','#rename-gallery','#archive-gallery']) $(selector).disabled = false;
    renderGalleries();
    $('#cancel-upload').hidden = true; $('#retry-upload').hidden = !failedUploads.length;
  }
}
if (photoInput) {
  photoInput.addEventListener('change', () => uploadBatch(Array.from(photoInput.files)));
  $('#cancel-upload').addEventListener('click', () => { stopUpload = true; $('#upload-status').textContent = 'Arrêt demandé après la photo en cours.'; });
  $('#retry-upload').addEventListener('click', () => uploadBatch([...failedUploads]));
  $('#open-create-gallery').addEventListener('click', () => { $('#create-gallery-status').textContent = ''; $('#create-gallery-dialog').showModal(); });
  $('#cancel-create-gallery').addEventListener('click', () => $('#create-gallery-dialog').close());
  $('#auto-cover').addEventListener('click', async () => {
    try { await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {cover_photo_id:null})); await loadGalleries(selectedGallery.id); } catch (error) { message(error); }
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
    const name = prompt('Nom de la galerie', selectedGallery.name); if (name === null) return;
    try { await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {name})); await loadGalleries(selectedGallery.id); } catch (error) { message(error); }
  });
  $('#archive-gallery').addEventListener('click', async () => {
    if (!confirm(selectedGallery.archived ? 'Restaurer cette galerie ? Les anciens liens resteront révoqués.' : 'Archiver cette galerie et révoquer ses liens clients ?')) return;
    try { await api(`/api/galleries/${selectedGallery.id}`, jsonRequest('PATCH', {archived:!selectedGallery.archived})); await loadGalleries(selectedGallery.id); } catch (error) { message(error); }
  });
  $('#clear').addEventListener('click', async () => {
    if (!confirm('Supprimer définitivement toutes les photos de cette galerie ?')) return;
    try { await api(galleryURL('/api/photos'), {method:'DELETE'}); await refresh(); } catch (error) { message(error); }
  });
  $('#add-member').addEventListener('submit', async event => {
    event.preventDefault();
    try { await api(`/api/galleries/${selectedGallery.id}/members`, jsonRequest('POST', {username:new FormData(event.target).get('username')})); event.target.reset(); await refreshMembers(); } catch (error) { message(error); }
  });
  $('#generate-link').addEventListener('click', async () => {
    $('#generate-link').disabled = true;
    try {
      const result = await api('/api/client-links', jsonRequest('POST', {gallery_id:selectedGallery.id, days:Number($('#link-days').value)}));
      const link = new URL('/client', location.origin).href + '#' + result.token;
      const qr = await fetch('/api/client-qr', jsonRequest('POST', {token:result.token}));
      if (!qr.ok) throw new Error('Impossible de générer le QR code.');
      if ($('#client-qr').src.startsWith('blob:')) URL.revokeObjectURL($('#client-qr').src);
      $('#client-link').value = link; $('#test-link').href = link; $('#client-qr').src = URL.createObjectURL(await qr.blob());
      $('#share-note').textContent = `Lien privé valable ${result.expires_in_days} jour(s). Toute personne qui le possède peut rechercher dans cette galerie.`;
      $('#share-result').hidden = false; await refreshLinks();
    } catch (error) { message(error); } finally { $('#generate-link').disabled = false; }
  });
  $('#copy-link').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('#client-link').value); $('#copy-status').textContent = 'Lien copié.'; }
    catch (error) { $('#client-link').select(); $('#copy-status').textContent = 'Copiez le lien sélectionné.'; }
  });
  api('/api/me').then(async user => {
    me = user; $('#admin-link').hidden = user.role !== 'admin'; $('#open-create-gallery').hidden = !allowed('can_create_galleries');
    await loadGalleries();
  }).catch(message);
}
$('#logout')?.addEventListener('click', async () => { await api('/api/logout', {method:'POST'}); location.assign('/login'); });
if (selfieInput) {
  let clientReady = false;
  const token = location.hash.slice(1); history.replaceState(null, '', location.pathname);
  selfieInput.disabled = true;
  const ready = token ? api('/api/client/redeem', jsonRequest('POST', {token})) : api('/api/client/session');
  ready.then(() => { clientReady = true; selfieInput.disabled = false; }).catch(error => { $('#search-status').textContent = error.message + ' Demandez un nouveau lien au photographe.'; });
  selfieInput.addEventListener('change', async () => {
    if (!clientReady || !selfieInput.files.length) return;
    const data = new FormData(); data.append('file', selfieInput.files[0]); selfieInput.disabled = true;
    $('#search-status').textContent = 'Recherche en cours…'; $('#results-section').hidden = true;
    try {
      const results = await api('/api/search', {method:'POST', body:data});
      $('#search-status').textContent = results.length ? 'Recherche terminée.' : 'Aucune photo correspondante. Essayez un selfie bien éclairé.';
      $('#results').replaceChildren(...results.map(photo => card(photo, true))); $('#result-count').textContent = `${results.length} photo(s)`; $('#results-section').hidden = false;
    } catch (error) { $('#search-status').textContent = error.message; }
    finally { selfieInput.disabled = false; selfieInput.value = ''; }
  });
}
