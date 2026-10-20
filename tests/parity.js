/* 用 App 里的同一份 track.js 算一遍，输出 JSON 供 Python 比对。 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const T = require(path.join(root, "app", "track.js"));

const exp = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));

const lessons = fs.readdirSync(path.join(root, "data", "lessons"))
  .filter(f => f.endsWith(".json"))
  .map(f => JSON.parse(fs.readFileSync(path.join(root, "data", "lessons", f), "utf8")))
  .sort((a, b) => (a.order || 999) - (b.order || 999));

const chars = {};
fs.readFileSync(path.join(root, "data", "curriculum.csv"), "utf8")
  .split(/\r?\n/).slice(1).filter(Boolean).forEach(line => {
    const [ch, pinyin, word] = line.split(",");
    if (ch) chars[ch.trim()] = { pinyin, word };
  });

const res = T.stats(lessons, chars, exp.labels || {}, exp.events || []);
process.stdout.write(JSON.stringify(res));
