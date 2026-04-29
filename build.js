/**
 * 정적 HTML 빌드 → docs/index.html
 * 실행: node build.js
 * GitHub Pages: https://zoids901-debug.github.io/inkc-dashboard/
 */
const fs   = require('fs');
const path = require('path');
const { html, loadAllData } = require('./dashboard_server');

const OUT = path.join(__dirname, 'docs', 'ops-only', 'index.html');

const opsDir = path.join(__dirname, 'docs', 'ops-only');
if (!fs.existsSync(opsDir)) fs.mkdirSync(opsDir, {recursive:true});
if (false) {
  fs.mkdirSync(path.join(__dirname, 'docs', 'ops-only'));
}

const data    = loadAllData();
const content = html(data);
fs.writeFileSync(OUT, content, 'utf8');

const kb = Math.round(fs.statSync(OUT).size / 1024);
console.log(`✓ 빌드 완료: docs/index.html (${kb}KB)`);
console.log('  https://zoids901-debug.github.io/inkc-dashboard/');
