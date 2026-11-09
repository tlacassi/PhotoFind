const form = document.querySelector('#login-form');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const status = document.querySelector('#login-status');
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const data = new FormData(form);
    const response = await fetch('/api/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: data.get('username'), password: data.get('password')})});
    if (!response.ok) throw new Error((await response.json()).detail || 'Connexion impossible.');
    window.location.assign('/');
  } catch (error) { status.textContent = error.message; }
  finally { button.disabled = false; }
});
