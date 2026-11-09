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
photoInput?.addEventListener('change', async () => { if (!photoInput.files.length) return; const data = new FormData(); for (const file of photoInput.files) data.append('files', file); photoInput.disabled = true; $('#upload-status').textContent = 'Import et analyse des visages en cours…'; try { const results = await api('/api/photos', {method:'POST', body:data}); const errors = results.filter(r => r.error); const ok = results.filter(r => !r.error); $('#upload-status').textContent = `${ok.length} photo(s) analysée(s), ${ok.reduce((n,r) => n+r.faces,0)} visage(s) détecté(s).` + (errors.length ? ` Erreurs : ${errors.map(e => `${e.name} : ${e.error}`).join(' ; ')}` : ''); await refresh(); } catch(e) { $('#upload-status').textContent = e.message; } finally { photoInput.disabled = false; photoInput.value = ''; } });
selfieInput?.addEventListener('change', async () => { if (!selfieInput.files.length) return; const data = new FormData(); data.append('file', selfieInput.files[0]); selfieInput.disabled = true; $('#search-status').textContent = 'Recherche en cours…'; $('#results-section').hidden = true; try { const results = await api('/api/search', {method:'POST', body:data}); $('#search-status').textContent = results.length ? 'Recherche terminée.' : 'Aucune photo correspondante. Essayez un autre selfie bien éclairé.'; $('#results').replaceChildren(...results.map(p => card(p, true))); $('#result-count').textContent = `${results.length} photo${results.length === 1 ? '' : 's'}`; $('#results-section').hidden = false; } catch(e) { $('#search-status').textContent = e.message; } finally { selfieInput.disabled = false; selfieInput.value = ''; } });
$('#clear')?.addEventListener('click', async () => { if (!confirm('Supprimer toutes les photos et leurs données de reconnaissance ?')) return; try { await api('/api/photos', {method:'DELETE'}); $('#results-section').hidden = true; $('#upload-status').textContent = 'Photos supprimées.'; await refresh(); } catch(e) { $('#upload-status').textContent = e.message; } });
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
