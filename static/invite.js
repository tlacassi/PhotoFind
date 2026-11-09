const form = document.querySelector('#register-form'), status = document.querySelector('#register-status');
const token = location.hash.slice(1); history.replaceState(null, '', location.pathname);
async function request(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const result = await response.json(); if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Valeurs invalides.'); return result;
}
if (token) request('/api/invitations/check', {token}).then(result => {
  document.querySelector('#invite-description').textContent = `Créez votre compte personnel. Quota de photos : ${(result.quota_bytes / 1024**3).toFixed(2)} Gio.`; form.hidden = false;
}).catch(error => { status.textContent = error.message; });
else status.textContent = 'Ouvrez le lien complet fourni par votre administrateur.';
form.addEventListener('submit', async event => {
  event.preventDefault(); const data = new FormData(form), button = form.querySelector('button');
  if (data.get('password') !== data.get('confirmation')) { status.textContent = 'Les mots de passe ne correspondent pas.'; return; }
  button.disabled = true;
  try {
    await request('/api/register', {token,username:data.get('username'),password:data.get('password')}); form.reset(); form.hidden = true;
    status.textContent = 'Compte créé. Vous pouvez maintenant vous connecter.'; document.querySelector('#register-login').hidden = false;
  } catch(error) { status.textContent = error.message; } finally { button.disabled = false; }
});
