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
