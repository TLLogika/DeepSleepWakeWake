const $ = (selector) => document.querySelector(selector);
const state = { saved: [], found: [], network: null, scanning: false, scanned: false };
let toastTimer;

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const toggle = $('#theme-toggle');
  const label = theme === 'dark' ? 'Włącz jasny motyw' : 'Włącz ciemny motyw';
  toggle.textContent = theme === 'dark' ? '☀' : '☾';
  toggle.setAttribute('aria-label', label);
  toggle.title = label;
}

try {
  setTheme(localStorage.getItem('wakeboard-theme') === 'light' ? 'light' : 'dark');
} catch {
  setTheme('dark');
}

$('#theme-toggle').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  setTheme(next);
  try { localStorage.setItem('wakeboard-theme', next); } catch { /* Storage may be disabled. */ }
});

function toast(message, error = false) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.toggle('error', error);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4500);
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: options.body ? { 'Content-Type': 'application/json' } : {},
    });
  } catch {
    throw new Error('Brak połączenia z lokalnym serwerem.');
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Nie udało się wykonać operacji.');
  return result;
}

function renderNetwork() {
  if (!state.network) return;
  $('#network-status').textContent = state.network.scan_range;
  $('#network-description').textContent = `Interfejs ${state.network.interface} · adres ${state.network.address}`;
}

function networkChoice() {
  return {
    interface: $('#network-interface').value,
    subnet: $('#network-subnet').value.trim(),
  };
}

function saveNetworkChoice() {
  try { localStorage.setItem('wakeboard-network', JSON.stringify(networkChoice())); } catch { /* Storage may be disabled. */ }
}

function showNetworkChoices(networks) {
  const select = $('#network-interface');
  const seen = new Set();
  for (const network of networks) {
    if (seen.has(network.interface)) continue;
    seen.add(network.interface);
    const option = document.createElement('option');
    option.value = network.interface;
    option.textContent = `${network.interface} · ${network.cidr}`;
    select.append(option);
  }
  try {
    const saved = JSON.parse(localStorage.getItem('wakeboard-network') || '{}');
    if (typeof saved.interface === 'string' && seen.has(saved.interface)) select.value = saved.interface;
    if (typeof saved.subnet === 'string') $('#network-subnet').value = saved.subnet;
  } catch { /* Storage may be disabled or contain invalid data. */ }
}

function renderSaved() {
  $('#saved-count').textContent = state.saved.length;
  const list = $('#saved-list');
  list.replaceChildren();
  $('#saved-empty').hidden = state.saved.length > 0;
  for (const device of state.saved) {
    const row = document.createElement('div');
    row.className = 'saved-row';
    const identity = document.createElement('div');
    identity.className = 'saved-identity';
    const name = document.createElement('strong');
    name.className = 'saved-name';
    name.textContent = device.name;
    const meta = document.createElement('span');
    meta.className = 'saved-meta';
    meta.textContent = `${device.ip || 'Brak IP'} · ${device.mac}`;
    identity.append(name, meta);

    const actions = document.createElement('div');
    actions.className = 'saved-actions';
    const wakeButton = document.createElement('button');
    wakeButton.className = 'wake-button';
    wakeButton.type = 'button';
    wakeButton.textContent = 'Wybudź';
    wakeButton.addEventListener('click', () => wakeDevice(device, wakeButton));
    const remove = document.createElement('button');
    remove.className = 'remove-button';
    remove.type = 'button';
    remove.title = 'Usuń urządzenie';
    remove.setAttribute('aria-label', `Usuń ${device.name}`);
    remove.textContent = '×';
    remove.addEventListener('click', () => removeDevice(device));
    actions.append(wakeButton, remove);
    row.append(identity, actions);
    list.append(row);
  }
  renderFound();
}

function renderFound() {
  const body = $('#scan-results');
  body.replaceChildren();
  $('#found-count').textContent = state.scanning ? '…' : (state.scanned ? state.found.length : '—');
  if (!state.found.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 3;
    cell.className = 'table-empty';
    cell.textContent = state.scanning
      ? 'Skanowanie trwa. To może potrwać kilka sekund…'
      : 'Nie znaleziono urządzeń. Spróbuj skanować lub dodaj adres MAC ręcznie.';
    row.append(cell);
    body.append(row);
    return;
  }
  for (const device of state.found) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = device.hostname || 'Urządzenie sieciowe';
    const ip = document.createElement('td');
    ip.textContent = device.ip;
    const action = document.createElement('td');
    action.className = 'action-cell';
    const button = document.createElement('button');
    const saved = device.mac && state.saved.some((item) => item.mac === device.mac);
    button.className = `table-button${saved ? ' saved' : ''}`;
    button.textContent = saved ? 'Zapisane' : (device.mac ? '+ Dodaj' : 'Dodaj ręcznie');
    button.disabled = saved;
    if (!saved) button.addEventListener('click', () => openDialog(device));
    action.append(button);
    row.append(name, ip, action);
    body.append(row);
  }
}

async function load() {
  try {
    const result = await api('/api/state');
    state.saved = result.devices;
    state.network = result.network;
    showNetworkChoices(result.networks || [result.network]);
    renderNetwork();
    renderSaved();
    scanNetwork(true);
  } catch (error) {
    $('#network-status').textContent = 'Brak sieci';
    $('#network-description').textContent = 'Sprawdź połączenie sieciowe i serwer.';
    $('#saved-empty').hidden = false;
    toast(error.message, true);
  }
}

async function scanNetwork(silent = false) {
  if (state.scanning) return;
  const choice = networkChoice();
  saveNetworkChoice();
  state.scanning = true;
  state.found = [];
  renderFound();
  const scanButton = $('#scan-button');
  scanButton.disabled = true;
  scanButton.querySelector('span').textContent = 'Skanowanie...';
  $('#empty-scan').disabled = true;
  $('#network-interface').disabled = true;
  $('#network-subnet').disabled = true;
  $('#reset-network').disabled = true;
  try {
    const result = await api('/api/scan', { method: 'POST', body: JSON.stringify(choice) });
    state.found = result.devices;
    state.scanned = true;
    state.network = result.network;
    renderNetwork();
    if (!silent) toast(`Skanowanie zakończone. Znaleziono ${state.found.length} urządzeń.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.scanning = false;
    renderFound();
    scanButton.disabled = false;
    scanButton.querySelector('span').textContent = 'Skanuj sieć';
    $('#empty-scan').disabled = false;
    $('#network-interface').disabled = false;
    $('#network-subnet').disabled = false;
    $('#reset-network').disabled = false;
  }
}

function openDialog(device = null) {
  $('#add-form').reset();
  if (device) {
    $('#device-name').value = device.hostname || '';
    $('#device-ip').value = device.ip || '';
    $('#device-mac').value = device.mac || '';
  }
  $('#add-dialog').showModal();
  $('#device-name').focus();
}

async function addDevice(event) {
  event.preventDefault();
  const save = $('#save-device');
  save.disabled = true;
  try {
    const result = await api('/api/devices', {
      method: 'POST',
      body: JSON.stringify({
        name: $('#device-name').value,
        ip: $('#device-ip').value,
        mac: $('#device-mac').value,
        ...networkChoice(),
      }),
    });
    state.saved.push(result.device);
    renderSaved();
    $('#add-dialog').close();
    toast('Urządzenie zostało zapisane.');
  } catch (error) {
    toast(error.message, true);
  } finally {
    save.disabled = false;
  }
}

async function removeDevice(device) {
  if (!confirm(`Usunąć „${device.name}” z zapisanych urządzeń?`)) return;
  try {
    await api(`/api/devices/${device.id}`, { method: 'DELETE' });
    state.saved = state.saved.filter((item) => item.id !== device.id);
    renderSaved();
    toast('Urządzenie zostało usunięte.');
  } catch (error) {
    toast(error.message, true);
  }
}

async function wakeDevice(device, button) {
  button.disabled = true;
  try {
    await api('/api/wake', { method: 'POST', body: JSON.stringify({ mac: device.mac, ...networkChoice() }) });
    toast(`Wysłano sygnał Wake-on-LAN do „${device.name}”.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

for (const button of [$('#scan-button'), $('#empty-scan')]) button.addEventListener('click', () => scanNetwork());
for (const control of [$('#network-interface'), $('#network-subnet')]) control.addEventListener('change', saveNetworkChoice);
$('#reset-network').addEventListener('click', () => {
  $('#network-interface').value = '';
  $('#network-subnet').value = '';
  saveNetworkChoice();
  scanNetwork();
});
$('#add-button').addEventListener('click', () => openDialog());
$('#close-dialog').addEventListener('click', () => $('#add-dialog').close());
$('#cancel-dialog').addEventListener('click', () => $('#add-dialog').close());
$('#add-form').addEventListener('submit', addDevice);
load();
