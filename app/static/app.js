const $ = (id) => document.getElementById(id);
const input = $('product-json');
let currentResult = null;
let selectedExample = null;
let busy = false;
let toastTimer;

function showError(message) {
  $('error-box').textContent = message;
  $('error-box').hidden = false;
}

function resetResult() {
  currentResult = null;
  $('result-content').hidden = true;
  $('result-status').hidden = true;
  $('empty-state').hidden = false;
  $('error-box').hidden = true;
}

function setBusy(value) {
  busy = value;
  input.disabled = value;
  $('generate-button').disabled = value;
  $('json-file').disabled = value;
  $('upload-button').disabled = value;
  $('preview-button').disabled = value || !selectedExample;
  document.querySelectorAll('[data-example]').forEach((button) => { button.disabled = value; });
  document.querySelector('.result-panel').setAttribute('aria-busy', String(value));
  $('spinner').hidden = !value;
  $('generate-arrow').hidden = value;
  $('generate-label').textContent = value ? 'Готовим карточку…' : 'Подготовить карточку';
  $('loading-state').hidden = !value;
  if (value) {
    $('empty-state').hidden = true;
    $('result-content').hidden = true;
    $('result-status').hidden = true;
  }
}

function showToast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3500);
}

async function readResponse(response) {
  let data;
  try { data = await response.json(); }
  catch { throw new Error('Сервис вернул непонятный ответ. Повтори попытку.'); }
  if (!response.ok) {
    const fields = (data.errors || []).map((item) => `${item.field}: ${item.message}`).join('; ');
    throw new Error(`${data.detail || 'Не удалось выполнить запрос.'}${fields ? ' ' + fields : ''}`);
  }
  return data;
}

function fillList(container, values) {
  container.replaceChildren();
  for (const value of values) {
    const li = document.createElement('li');
    li.textContent = value;
    container.append(li);
  }
}

function showResult(result, isSample = false) {
  currentResult = result;
  $('empty-state').hidden = true;
  $('result-content').hidden = false;
  $('sample-notice').hidden = !isSample;
  const needsReview = result.status !== 'ready';
  $('result-status').textContent = isSample ? 'Образец' : needsReview ? 'Нужно уточнить' : 'Формат проверен';
  $('result-status').className = 'status' + (needsReview ? ' review' : '');
  $('result-status').hidden = false;
  $('warnings-box').replaceChildren();
  $('warnings-box').hidden = !result.warnings.length;
  if (result.warnings.length) {
    const list = document.createElement('ul');
    fillList(list, result.warnings);
    $('warnings-box').append(list);
  }
  $('missing-box').replaceChildren();
  $('missing-box').hidden = !result.missing_fields.length;
  if (result.missing_fields.length) {
    const heading = document.createElement('strong');
    heading.textContent = 'Нужно уточнить';
    const list = document.createElement('ul');
    fillList(list, result.missing_fields);
    $('missing-box').append(heading, list);
  }
  $('card-content').hidden = !result.card;
  if (!result.card) return;
  const card = result.card;
  $('seo-title').textContent = card.seo_title;
  $('seo-description').textContent = card.seo_description;
  $('commercial-block').textContent = card.commercial_block;
  $('title-count').textContent = `${result.checks.title_length} / 70`;
  $('description-count').textContent = `${result.checks.description_length} / 800–1200`;
  $('queries-count').textContent = `${result.checks.query_count} запроса`;
  $('characteristics').replaceChildren();
  const characteristics = card.characteristics.length ? card.characteristics : [{ name: 'Характеристики', value: 'данных нет' }];
  for (const item of characteristics) {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    const value = document.createElement('td');
    name.textContent = item.name;
    value.textContent = item.value;
    if (item.value === 'данных нет') value.className = 'no-data';
    row.append(name, value);
    $('characteristics').append(row);
  }
  fillList($('search-queries'), card.search_queries);
  $('result-json').textContent = JSON.stringify(result, null, 2);
  switchTab('card');
}

function switchTab(tab) {
  for (const name of ['card', 'json']) {
    const active = name === tab;
    $(`${name}-tab`).setAttribute('aria-selected', String(active));
    $(`${name}-tab`).tabIndex = active ? 0 : -1;
    $(`${name}-view`).hidden = !active;
  }
}

for (const tab of ['card', 'json']) {
  $(`${tab}-tab`).addEventListener('click', () => switchTab(tab));
  $(`${tab}-tab`).addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const next = event.key === 'Home' ? 'card' : event.key === 'End' ? 'json' : tab === 'card' ? 'json' : 'card';
      switchTab(next);
      $(`${next}-tab`).focus();
    }
  });
}

input.addEventListener('input', () => {
  resetResult();
  selectedExample = null;
  $('demo-note').hidden = true;
  $('preview-button').disabled = true;
  document.querySelectorAll('[data-example]').forEach((button) => button.classList.remove('active'));
});

document.querySelectorAll('[data-example]').forEach((button) => {
  button.addEventListener('click', async () => {
    if (busy) return;
    resetResult();
    try {
      const response = await fetch(`/api/examples/${button.dataset.example}`);
      const product = await readResponse(response);
      input.value = JSON.stringify(product, null, 2);
      selectedExample = button.dataset.example;
      $('demo-note').hidden = false;
      $('preview-button').disabled = false;
      document.querySelectorAll('[data-example]').forEach((item) => item.classList.toggle('active', item === button));
    } catch (error) { showError(error.message); }
  });
});

$('upload-button').addEventListener('click', () => $('json-file').click());

$('json-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  resetResult();
  if (file.size > 64 * 1024) { showError('Файл слишком большой. Максимум — 64 КБ.'); event.target.value = ''; return; }
  try {
    const text = await file.text();
    JSON.parse(text);
    input.value = text;
    input.dispatchEvent(new Event('input'));
  } catch { showError('Не удалось прочитать JSON. Проверь формат файла.'); }
  event.target.value = '';
});

$('product-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  resetResult();
  let product;
  try { product = JSON.parse(input.value); }
  catch { showError('Некорректный JSON. Проверь кавычки, запятые и скобки.'); return; }
  setBusy(true);
  try {
    const response = await fetch('/api/cards', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(product), signal: AbortSignal.timeout(135000),
    });
    showResult(await readResponse(response));
  } catch (error) {
    $('empty-state').hidden = false;
    showError(['TimeoutError', 'AbortError'].includes(error.name) ? 'Время ожидания истекло. Повтори попытку позже.' : error.message);
  } finally { setBusy(false); }
});

$('preview-button').addEventListener('click', async () => {
  if (!selectedExample || busy) return;
  resetResult();
  try {
    const response = await fetch(`/api/examples/${selectedExample}/result`);
    showResult(await readResponse(response), true);
  } catch (error) { showError(error.message); }
});

async function exportCard(format) {
  if (!currentResult?.card) throw new Error('Сначала подготовь карточку.');
  const response = await fetch(`/api/export/${format}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ card: currentResult.card, missing_fields: currentResult.missing_fields, warnings: currentResult.warnings }),
  });
  if (!response.ok) await readResponse(response);
  return response;
}

$('copy-button').addEventListener('click', async () => {
  try {
    const response = await exportCard('markdown');
    await navigator.clipboard.writeText(await response.text());
    showToast('Markdown скопирован');
  } catch { showToast('Не удалось скопировать. Можно выделить текст карточки вручную.'); }
});

$('download-button').addEventListener('click', async () => {
  try {
    const response = await exportCard('json');
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = 'product-card.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showToast(error.message); }
});
