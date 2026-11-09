const $ = selector => document.querySelector(selector);
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers:{'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Valeurs invalides.');
  return data;
}
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
    const passwordLabel = document.createElement('label'); passwordLabel.textContent = 'Nouveau mot de passe (facultatif, 8 caractères minimum)';
    const password = document.createElement('input'); password.type = 'password'; password.minLength = 8; password.maxLength = 256; password.autocomplete = 'new-password'; passwordLabel.append(password); card.append(passwordLabel);
    const save = document.createElement('button'); save.className = 'button'; save.textContent = 'Enregistrer'; card.append(save);
    card.addEventListener('submit', async event => {
      event.preventDefault(); save.disabled = true;
      const body = {username:name.value, role:role.value};
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
  try { await api('/api/users', 'POST', Object.fromEntries(data)); event.target.reset(); $('#admin-status').textContent = 'Compte créé.'; await loadAccounts(); }
  catch (error) { status(error); }
});
$('#logout').addEventListener('click', async () => { await api('/api/logout', 'POST'); location.assign('/login'); });
loadAccounts().catch(status);
