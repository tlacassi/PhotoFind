const $ = selector => document.querySelector(selector);
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers:{'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Valeurs invalides.');
  return data;
}
const gib = bytes => (bytes / 1024**3).toFixed(2);
const storageSize = bytes => bytes < 1024**2 ? `${(bytes / 1024).toFixed(1)} Kio` : bytes < 1024**3 ? `${(bytes / 1024**2).toFixed(1)} Mio` : `${gib(bytes)} Gio`;
const permissions = {active:'Compte actif', can_create_galleries:'Créer / gérer ses galeries', can_upload:'Importer', can_delete:'Supprimer les photos', can_share:'Partager'};
function status(error) { $('#admin-status').textContent = error.message; }
async function loadAccounts() {
  const users = await api('/api/users'); $('#accounts').replaceChildren();
  for (const user of users) {
    const card = document.createElement('form'); card.className = 'card';
    const title = document.createElement('h2'); title.textContent = user.username; card.append(title);
    const nameLabel = document.createElement('label'); nameLabel.textContent = 'Identifiant';
    const name = document.createElement('input'); name.value = user.username; name.minLength = 3; name.maxLength = 64; name.required = true; nameLabel.append(name); card.append(nameLabel);
    const roleLabel = document.createElement('label'); roleLabel.textContent = 'Rôle';
    const role = document.createElement('select');
    for (const [value, text] of [['photographer','Photographe'],['admin','Administrateur']]) { const option = document.createElement('option'); option.value = value; option.textContent = text; role.append(option); }
    role.value = user.role; roleLabel.append(role); card.append(roleLabel);
    const fields = {}, group = document.createElement('div'); group.className = 'permissions';
    for (const [key, text] of Object.entries(permissions)) {
      const label = document.createElement('label'), input = document.createElement('input'); input.type = 'checkbox'; input.checked = Boolean(user[key]);
      label.append(input, document.createTextNode(text)); group.append(label); fields[key] = input;
    }
    card.append(group);
    const usage = document.createElement('p'); usage.textContent = `Photos : ${storageSize(user.used_bytes)} utilisés / ${user.quota_bytes === null ? 'illimité' : gib(user.quota_bytes) + ' Gio'}`; card.append(usage);
    const quotaLabel = document.createElement('label'); quotaLabel.textContent = 'Quota de photos (Gio, vide = illimité)';
    const quota = document.createElement('input'); quota.type = 'number'; quota.min = 0; quota.step = 'any'; quota.value = user.quota_bytes === null ? '' : user.quota_bytes / 1024**3; quotaLabel.append(quota); card.append(quotaLabel);
    const passwordLabel = document.createElement('label'); passwordLabel.textContent = 'Nouveau mot de passe (facultatif, 8 caractères minimum)';
    const password = document.createElement('input'); password.type = 'password'; password.minLength = 8; password.maxLength = 256; password.autocomplete = 'new-password'; passwordLabel.append(password); card.append(passwordLabel);
    const save = document.createElement('button'); save.className = 'button'; save.textContent = 'Enregistrer'; card.append(save);
    card.addEventListener('submit', async event => {
      event.preventDefault(); save.disabled = true;
      const body = {username:name.value, role:role.value, quota_bytes:quota.value === '' ? null : Math.round(Number(quota.value) * 1024**3)};
      for (const [key, input] of Object.entries(fields)) body[key] = input.checked;
      if (password.value) body.password = password.value;
      try { await api(`/api/users/${user.id}`, 'PATCH', body); $('#admin-status').textContent = 'Compte mis à jour ; sessions révoquées.'; await loadAccounts(); }
      catch (error) { status(error); } finally { save.disabled = false; }
    });
    const revoke = document.createElement('button'); revoke.type = 'button'; revoke.className = 'text-button'; revoke.textContent = 'Déconnecter toutes les sessions';
    revoke.addEventListener('click', async () => {
      try { await api(`/api/users/${user.id}/sessions`, 'DELETE'); $('#admin-status').textContent = 'Sessions révoquées.'; } catch (error) { status(error); }
    }); card.append(revoke); $('#accounts').append(card);
  }
}
$('#create-user').addEventListener('submit', async event => {
  event.preventDefault(); const data = new FormData(event.target);
  try { const body = Object.fromEntries(data); body.quota_bytes = body.quota_gib === '' ? null : Math.round(Number(body.quota_gib) * 1024**3); delete body.quota_gib; await api('/api/users', 'POST', body); event.target.reset(); $('#admin-status').textContent = 'Compte créé.'; await loadAccounts(); }
  catch (error) { status(error); }
});
$('#logout').addEventListener('click', async () => { await api('/api/logout', 'POST'); location.assign('/login'); });
loadAccounts().catch(status);

async function loadInvitations() {
  $('#invitations').replaceChildren();
  for (const invitation of await api('/api/invitations')) {
    const item = document.createElement('li');
    item.textContent = `${gib(invitation.quota_bytes)} Gio · ` + (invitation.used ? 'Utilisée' : invitation.expires * 1000 <= Date.now() ? 'Expirée ou révoquée' : `Expire le ${new Date(invitation.expires * 1000).toLocaleString()} `);
    if (!invitation.used && invitation.expires * 1000 > Date.now()) {
      const revoke = document.createElement('button'); revoke.type = 'button'; revoke.className = 'text-button'; revoke.textContent = 'Révoquer';
      revoke.addEventListener('click', async () => { try { await api(`/api/invitations/${invitation.id}`, 'DELETE'); $('#invitation-result').hidden = true; await loadInvitations(); } catch(error) { status(error); } }); item.append(revoke);
    }
    $('#invitations').append(item);
  }
}
$('#create-invitation').addEventListener('submit', async event => {
  event.preventDefault(); const data = new FormData(event.currentTarget), button = event.currentTarget.querySelector('button'); button.disabled = true;
  try {
    const result = await api('/api/invitations', 'POST', {days:Number(data.get('days')),quota_bytes:Math.round(Number(data.get('quota_gib')) * 1024**3)});
    $('#invitation-link').value = new URL('/invite', location.origin).href + '#' + result.token; $('#invitation-result').hidden = false; await loadInvitations();
  } catch(error) { status(error); } finally { button.disabled = false; }
});
$('#copy-invitation').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#invitation-link').value); $('#admin-status').textContent = 'Invitation copiée.'; }
  catch(error) { $('#invitation-link').select(); $('#admin-status').textContent = 'Copiez le lien sélectionné.'; }
});
loadInvitations().catch(status);
