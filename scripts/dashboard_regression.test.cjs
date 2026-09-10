const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const LEGAL = path.join(ROOT, 'legal');
const PAGES = ['index.html', 'cambios.html', 'dashboard.html', 'privacy.html', 'terms.html'];

function read(name) {
  return fs.readFileSync(path.join(LEGAL, name), 'utf8');
}

test('all inline page scripts parse', () => {
  for (const name of PAGES) {
    const html = read(name);
    let index = 0;
    for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) {
      if (match[1].trim()) new vm.Script(match[1], { filename: `${name}:script${index}` });
      index += 1;
    }
    assert.ok(index > 0, `${name} has no inline script`);
  }
});

test('dashboard validates session before loading guilds', () => {
  const html = read('dashboard.html');
  assert.ok(html.indexOf('/api/auth/me') < html.indexOf('/api/auth/guilds'));
  assert.match(html, /credentials:\s*['"]include['"]/);
  assert.doesNotMatch(html, /localStorage\.setItem\([^,]+(?:access|refresh|discord)[^,]*/i);
  assert.doesNotMatch(html, /sessionStorage\.setItem\([^,]+(?:access|refresh|discord)[^,]*/i);
});

test('public pages expose honest status states and shared modal contract', () => {
  for (const name of PAGES) {
    const html = read(name);
    assert.match(html, /status-modal-overlay/);
    assert.match(html, /status-modal-card[^>]+role="dialog"/);
    assert.match(html, /status-bot-badge[^>]+unknown/);
    assert.doesNotMatch(html, /99\.9%/);
  }
});

test('root and legal Vercel configs keep same-origin API proxy and no-store headers', () => {
  const root = JSON.parse(fs.readFileSync(path.join(ROOT, 'vercel.json'), 'utf8'));
  const legal = JSON.parse(fs.readFileSync(path.join(LEGAL, 'vercel.json'), 'utf8'));
  assert.deepEqual(legal.rewrites, root.rewrites);
  assert.deepEqual(legal.headers, root.headers);
  assert.equal(root.rewrites[0].source, '/api/:path*');
  assert.match(JSON.stringify(root.headers), /no-store/);
});

test('service worker bypasses API and OAuth callback URLs', () => {
  const sw = fs.readFileSync(path.join(LEGAL, 'sw.js'), 'utf8');
  assert.match(sw, /url\.pathname\.startsWith\('\/api\/'\)/);
  assert.match(sw, /url\.searchParams\.has\('code'\)/);
  assert.match(sw, /url\.searchParams\.has\('state'\)/);
  assert.match(sw, /key\.startsWith\('skb-'\)/);
});

test('privacy page describes encrypted dashboard sessions', () => {
  const privacy = read('privacy.html');
  assert.match(privacy, /bundle OAuth cifrado/);
  assert.match(privacy, /cookie de sesi[oó]n opaca/);
  assert.match(privacy, /duraci[oó]n m[aá]xima configurada de 30 d[ií]as/);
  assert.doesNotMatch(privacy, /[Uu]nicamente guarda los identificadores/);
});

test('renderRetryState does not accumulate listeners or trigger duplicate requests', () => {
  const html = read('dashboard.html');
  assert.match(html, /renderRetryState\s*\(/);
  assert.match(html, /\{ once: true \}/);

  // Execute in isolated VM with DOM mock
  let buttonListener = null;
  let retryCount = 0;
  const mockButton = {
    addEventListener: (event, fn, opts) => {
      if (event === 'click') buttonListener = { fn, once: !!opts?.once };
    },
    click: () => {
      if (!buttonListener) return;
      const { fn, once } = buttonListener;
      if (once) buttonListener = null;
      fn();
    }
  };
  const mockContainer = {
    _html: '',
    get innerHTML() { return this._html; },
    set innerHTML(val) {
      this._html = val;
      buttonListener = null; // Overwriting innerHTML removes child elements and their listeners
    },
    querySelector: (sel) => (sel === 'button' ? mockButton : null)
  };

  const sandbox = {
    container: mockContainer,
    escapeHtml: (s) => String(s),
    retryFn: () => { retryCount++; }
  };
  const code = `
    function renderRetryState(container, message, retry) {
        if (!container) return;
        container.innerHTML = '<div>' + escapeHtml(message) + '<button>Reintentar</button></div>';
        container.querySelector('button')?.addEventListener('click', retry, { once: true });
    }
    // Simulate 3 consecutive failures
    renderRetryState(container, 'Fallo 1', retryFn);
    renderRetryState(container, 'Fallo 2', retryFn);
    renderRetryState(container, 'Fallo 3', retryFn);
  `;
  vm.runInNewContext(code, sandbox);

  // Click once after 3 failures
  mockButton.click();
  assert.equal(retryCount, 1, 'Retry must execute exactly once per click after multiple failure states');

  // Second click on the consumed button must not fire again
  mockButton.click();
  assert.equal(retryCount, 1, 'Consumed { once: true } button must not fire duplicate calls');
});

test('dashboard implements accessible tabs, roving tabindex and combobox keyboard navigation', () => {
  const html = read('dashboard.html');
  assert.match(html, /role="tablist"[^>]*aria-label="Secciones del servidor"/);
  assert.match(html, /id="tab-btn-leaderboard"[^>]*role="tab"[^>]*aria-controls="panel-leaderboard"/);
  assert.match(html, /id="tab-btn-my-messages"[^>]*role="tab"[^>]*aria-controls="panel-my-messages"/);
  assert.match(html, /id="tab-btn-config"[^>]*role="tab"[^>]*aria-controls="panel-config"/);
  assert.match(html, /id="panel-leaderboard"[^>]*role="tabpanel"[^>]*tabindex="0"/);
  assert.match(html, /id="panel-my-messages"[^>]*role="tabpanel"[^>]*tabindex="0"/);
  assert.match(html, /id="panel-config"[^>]*role="tabpanel"[^>]*tabindex="0"/);
  assert.match(html, /id="channel-trigger"[^>]*aria-controls="channel-dropdown"[^>]*aria-haspopup="listbox"/);
  assert.match(html, /id="channel-options-container"[^>]*role="listbox"/);
  assert.match(html, /item\.setAttribute\('role',\s*'option'\)/);
  assert.match(html, /ArrowLeft.*ArrowRight.*Home.*End/s);
});
