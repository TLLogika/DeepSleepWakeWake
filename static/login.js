const $ = (selector) => document.querySelector(selector);

function message(text) {
  $('#message').textContent = text;
  $('#message').hidden = false;
}

async function post(path, data) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Wakeboard-Request': '1' },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Nie udało się zalogować.');
  location.replace('/');
}

async function load() {
  try {
    const response = await fetch('/api/auth/status');
    const status = await response.json();
    if (status.authenticated) return location.replace('/');
    const setup = !status.configured;
    $('#title').textContent = setup ? 'Ustaw hasło admina' : 'Zaloguj się';
    $('#intro').textContent = setup
      ? 'To pierwsze uruchomienie. Podaj kod z serwera i ustaw stałe hasło do konta admin.'
      : 'Wpisz hasło konta admin, aby otworzyć panel.';
    $(setup ? '#setup-form' : '#login-form').hidden = false;
  } catch {
    message('Nie można połączyć się z serwerem.');
  }
}

$('#setup-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#message').hidden = true;
  const password = $('#setup-password').value;
  if (password !== $('#setup-confirm').value) return message('Hasła nie są takie same.');
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    await post('/api/auth/setup', { code: $('#setup-code').value.trim(), password });
  } catch (error) {
    message(error.message);
    button.disabled = false;
  }
});

$('#login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#message').hidden = true;
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    await post('/api/auth/login', { username: 'admin', password: $('#password').value });
  } catch (error) {
    message(error.message);
    button.disabled = false;
  }
});

load();
