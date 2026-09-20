const $ = (selector) => document.querySelector(selector);
const state = { saved: [], found: [], network: null, scanning: false, scanned: false };
let toastTimer;

function icon() {
  const wrapper = document.createElement('span');
  wrapper.className = 'device-icon';
  wrapper.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>';
  return wrapper;
}

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
  $('#sidebar-network').textContent = state.network.scan_range;
  $('#sidebar-interface').textContent = `${state.network.interface} · ${state.network.address}`;
  $('#network-status').textContent = 'Połączono';
  $('#scan-description').textContent = `Skanowanie obejmuje sieć ${state.network.scan_range} przez ${state.network.interface}.`;
}

function renderSaved() {
  $('#saved-count').textContent = state.saved.length;
  const list = $('#saved-list');
  list.replaceChildren();
  $('#saved-empty').hidden = state.saved.length > 0;
  for (const device of state.saved) {
    const card = document.createElement('article');
    card.className = 'device-card';

    const top = document.createElement('div');
    top.className = 'device-top';
    top.append(icon());
    const remove = document.createElement('button');
    remove.className = 'device-menu';
    remove.type = 'button';
    remove.title = 'Usuń urządzenie';
    remove.setAttribute('aria-label', `Usuń ${device.name}`);
    remove.textContent = '×';
    remove.addEventListener('click', () => removeDevice(device));
    top.append(remove);
    card.append(top);

    const name = document.createElement('h3');
    name.textContent = device.name;
    card.append(name);
    const address = document.createElement('p');
    address.className = 'device-address';
    address.textContent = device.ip || 'Adres IP niepodany';
    card.append(address);

    const bottom = document.createElement('div');
    bottom.className = 'device-bottom';
    const mac = document.createElement('span');
    mac.className = 'mac-small';
    mac.textContent = device.mac;
    const wakeButton = document.createElement('button');
    wakeButton.className = 'wake-button';
    wakeButton.type = 'button';
    wakeButton.textContent = '↗  Wybudź';
    wakeButton.addEventListener('click', () => wakeDevice(device, wakeButton));
    bottom.append(mac, wakeButton);
    card.append(bottom);
    list.append(card);
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
    cell.colSpan = 4;
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
    const mac = document.createElement('td');
    mac.textContent = device.mac;
    const action = document.createElement('td');
    action.className = 'action-cell';
    const button = document.createElement('button');
    const saved = state.saved.some((item) => item.mac === device.mac);
    button.className = `table-button${saved ? ' saved' : ''}`;
    button.textContent = saved ? 'Zapisane' : '+ Dodaj';
    button.disabled = saved;
    if (!saved) button.addEventListener('click', () => openDialog(device));
    action.append(button);
    row.append(name, ip, mac, action);
    body.append(row);
  }
}

async function load() {
  try {
    const result = await api('/api/state');
    state.saved = result.devices;
    state.network = result.network;
    renderNetwork();
    renderSaved();
    scanNetwork();
  } catch (error) {
    $('#network-status').textContent = 'Brak sieci';
    $('#sidebar-network').textContent = 'Brak połączenia';
    $('#sidebar-interface').textContent = 'Sprawdź serwer i sieć';
    $('#saved-empty').hidden = false;
    toast(error.message, true);
  }
}

async function scanNetwork() {
  if (state.scanning) return;
  state.scanning = true;
  state.found = [];
  renderFound();
  for (const button of [$('#scan-hero'), $('#scan-section'), $('#empty-scan')]) button.disabled = true;
  try {
    const result = await api('/api/scan', { method: 'POST' });
    state.found = result.devices;
    state.scanned = true;
    state.network = result.network;
    renderNetwork();
    toast(`Skanowanie zakończone. Znaleziono ${state.found.length} urządzeń.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.scanning = false;
    renderFound();
    for (const button of [$('#scan-hero'), $('#scan-section'), $('#empty-scan')]) button.disabled = false;
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
    await api('/api/wake', { method: 'POST', body: JSON.stringify({ mac: device.mac }) });
    toast(`Wysłano sygnał Wake-on-LAN do „${device.name}”.`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

$('#today').textContent = new Intl.DateTimeFormat('pl-PL', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date());
for (const button of [$('#scan-hero'), $('#scan-section'), $('#empty-scan')]) button.addEventListener('click', scanNetwork);
for (const button of [$('#add-hero'), $('#add-device')]) button.addEventListener('click', () => openDialog());
$('#close-dialog').addEventListener('click', () => $('#add-dialog').close());
$('#cancel-dialog').addEventListener('click', () => $('#add-dialog').close());
$('#add-form').addEventListener('submit', addDevice);
load();
