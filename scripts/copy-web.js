// Copies the shared web app into the Android app's www folder.
const fs = require("fs"), path = require("path");
const src = path.join(__dirname, "..", "web"), dst = path.join(__dirname, "..", "app", "www");
const keep = new Set(["srd", "config.json"]);
fs.mkdirSync(dst, { recursive: true });
for (const f of fs.readdirSync(dst)) if (!keep.has(f)) fs.rmSync(path.join(dst, f), { recursive: true, force: true });
fs.cpSync(src, dst, { recursive: true });
console.log("Copied web app into app/www");
