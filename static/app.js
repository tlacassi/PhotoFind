const $ = s => document.querySelector(s);
const photoInput = $('#photos'), selfieInput = $('#selfie');
async function api(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Une erreur est survenue.'); return data; }
function card(photo, download = false) {
  const wrap = document.createElement('div'); wrap.className = download ? 'result' : 'thumb';
  const image = document.createElement('img'); image.src = download ? `/api/client/photos/${photo.id}/image` : `/api/photos/${photo.id}/image`; image.alt = photo.name; image.loading = 'lazy'; wrap.append(image);
  if (download) { const details = document.createElement('div'); details.className = 'result-details'; const name = document.createElement('span'); name.textContent = photo.name; const link = document.createElement('a'); link.href = image.src; link.download = photo.name.replace(/\.[^.]+$/, '') + '.jpg'; link.textContent = 'Télécharger ↓'; details.append(name, link); wrap.append(details); } else { wrap.title = `${photo.name} · ${photo.faces} visage(s)`; const remove = document.createElement('button'); remove.className = 'thumb-remove'; remove.type = 'button'; remove.textContent = '×'; remove.setAttribute('aria-label', `Supprimer ${photo.name}`); remove.addEventListener('click', async () => { if (!confirm(`Supprimer la photo ${photo.name} ?`)) return; try { await api(`/api/photos/${photo.id}`, {method:'DELETE'}); await refresh(); } catch(e) { $('#upload-status').textContent = e.message; } }); wrap.append(remove); }
  return wrap;
}
async function refresh() { const photos = await api('/api/photos'); $('#count').textContent = `${photos.length} photo${photos.length === 1 ? '' : 's'} importée${photos.length === 1 ? '' : 's'}`; $('#library').replaceChildren(...photos.map(p => card(p))); $('#clear').hidden = !photos.length; }
let failedUploads = [], stopUpload = false;
function uploadOne(file, index, total) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest(), data = new FormData();
    data.append('files', file);
    xhr.open('POST', '/api/photos');
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) {
        const percent = Math.round(100 * event.loaded / event.total);
        $('#upload-progress').value = (index - 1 + event.loaded / event.total) / total * 100;
        $('#upload-status').textContent = `Photo ${index}/${total} : transfert ${percent} % — ${file.name}`;
      }
    };
    xhr.upload.onload = () => { $('#upload-status').textContent = `Photo ${index}/${total} : analyse des visages…`; };
    xhr.onerror = () => reject(new Error('Échec du transfert.'));
    xhr.onload = () => {
      try {
        const response = JSON.parse(xhr.responseText);
        if (xhr.status < 200 || xhr.status >= 300) throw new Error(response.detail || 'Import impossible.');
        resolve(response[0]);
      } catch (error) { reject(error); }
    };
    xhr.send(data);
  });
}
async function uploadBatch(files) {
  if (!files.length) return;
  photoInput.disabled = true; stopUpload = false; failedUploads = [];
  $('#cancel-upload').hidden = false; $('#retry-upload').hidden = true;
  $('#upload-progress').hidden = false; $('#upload-progress').value = 0;
  $('#clear').disabled = true;
  const results = [];
  try {
    for (const [index, file] of files.entries()) {
      if (stopUpload) { failedUploads.push(...files.slice(index)); break; }
      let result;
      try { result = await uploadOne(file, index + 1, files.length); }
      catch (error) { result = {name:file.name, error:error.message}; }
      results.push(result);
      if (result.error) failedUploads.push(file);
      $('#upload-progress').value = (index + 1) / files.length * 100;
      await refresh().catch(() => {});
    }
    const errors = results.filter(result => result.error), ok = results.filter(result => !result.error);
    $('#upload-status').textContent = `${ok.length}/${files.length} photo(s) analysée(s), ${ok.reduce((n, result) => n + result.faces, 0)} visage(s) détecté(s).` + (stopUpload ? ' Import arrêté après la photo en cours.' : '') + (errors.length ? ` Erreurs : ${errors.map(error => `${error.name} : ${error.error}`).join(' ; ')}` : '');
  } catch (error) { $('#upload-status').textContent = error.message; }
  finally {
    photoInput.disabled = false; photoInput.value = ''; $('#clear').disabled = false;
    $('#cancel-upload').hidden = true; $('#retry-upload').hidden = !failedUploads.length;
  }
}
photoInput?.addEventListener('change', () => uploadBatch(Array.from(photoInput.files)));
$('#cancel-upload')?.addEventListener('click', () => {
  stopUpload = true;
  $('#upload-status').textContent = 'Arrêt demandé : la photo en cours sera terminée.';
});
$('#retry-upload')?.addEventListener('click', () => uploadBatch([...failedUploads]));
selfieInput?.addEventListener('change', async () => { if (!selfieInput.files.length) return; const data = new FormData(); data.append('file', selfieInput.files[0]); selfieInput.disabled = true; $('#search-status').textContent = 'Recherche en cours…'; $('#results-section').hidden = true; try { const results = await api('/api/search', {method:'POST', body:data}); $('#search-status').textContent = results.length ? 'Recherche terminée.' : 'Aucune photo correspondante. Essayez un autre selfie bien éclairé.'; $('#results').replaceChildren(...results.map(p => card(p, true))); $('#result-count').textContent = `${results.length} photo${results.length === 1 ? '' : 's'}`; $('#results-section').hidden = false; } catch(e) { $('#search-status').textContent = e.message; } finally { selfieInput.disabled = false; selfieInput.value = ''; } });
$('#clear')?.addEventListener('click', async () => { if (!confirm('Supprimer toutes les photos et leurs données de reconnaissance ?')) return; try { await api('/api/photos', {method:'DELETE'}); if ($('#results-section')) $('#results-section').hidden = true; $('#upload-status').textContent = 'Photos supprimées.'; await refresh(); } catch(e) { $('#upload-status').textContent = e.message; } });
if (photoInput) refresh().catch(e => { $('#upload-status').textContent = e.message; });
$('#generate-link')?.addEventListener('click', async () => {
  const button = $('#generate-link'); button.disabled = true;
  try {
    const result = await api('/api/client-links', {method:'POST'});
    const link = new URL('/client', window.location.origin).href + '#' + result.token;
    const qr = await fetch('/api/client-qr', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token:result.token})});
    if (!qr.ok) throw new Error('Impossible de générer le QR code.');
    if ($('#client-qr').src.startsWith('blob:')) URL.revokeObjectURL($('#client-qr').src);
    $('#client-link').value = link; $('#test-link').href = link;
    $('#client-qr').src = URL.createObjectURL(await qr.blob());
    $('#share-note').textContent = 'Lien privé valable 7 jours. Toute personne qui le possède peut effectuer une recherche.';
    $('#share-result').hidden = false;
  } catch(error) { $('#upload-status').textContent = error.message; }
  finally { button.disabled = false; }
});
$('#copy-link')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('#client-link').value);
    $('#copy-status').textContent = 'Lien copié.';
  } catch (e) {
    $('#client-link').select();
    $('#copy-status').textContent = 'Sélectionnez et copiez le lien ci-dessus.';
  }
});

if ($('#logout')) {
  api('/api/me').then(user => { $('#admin-section').hidden = user.role !== 'admin'; }).catch(() => location.assign('/login'));
  $('#logout').addEventListener('click', async () => { await api('/api/logout', {method:'POST'}); location.assign('/login'); });
  $('#create-user').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget, data = new FormData(form), status = $('#user-status');
    try {
      await api('/api/users', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:data.get('username'), password:data.get('password')})});
      status.textContent = 'Compte photographe créé.'; form.reset();
    } catch(error) { status.textContent = error.message; }
  });
}

if (selfieInput) {
  const token = location.hash.slice(1);
  if (token) {
    history.replaceState(null, '', location.pathname);
    selfieInput.disabled = true;
    api('/api/client/redeem', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token})})
      .catch(error => { $('#search-status').textContent = error.message; })
      .finally(() => { selfieInput.disabled = false; });
  }
}
