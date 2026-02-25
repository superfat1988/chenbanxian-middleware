#!/usr/bin/env node
import { astro } from 'iztro';

function usage() {
  console.error('Usage: node scripts/iztro_chart.mjs --date YYYY-M-D --hour 0-23 --gender 男|女 [--lang zh-CN] [--fixLeap true|false]');
  process.exit(2);
}

function parseArg(name, fallback = undefined) {
  const i = process.argv.indexOf(name);
  if (i === -1 || i + 1 >= process.argv.length) return fallback;
  return process.argv[i + 1];
}

const date = parseArg('--date');
const hourRaw = parseArg('--hour');
const gender = parseArg('--gender', '男');
const lang = parseArg('--lang', 'zh-CN');
const fixLeapRaw = parseArg('--fixLeap', 'true');

if (!date || hourRaw == null) usage();
const hour = Number(hourRaw);
if (!Number.isInteger(hour) || hour < 0 || hour > 23) usage();

const fixLeap = String(fixLeapRaw).toLowerCase() !== 'false';

function toIztroTimeIndex(h) {
  // iztro examples: 2 => 寅时; 0 => 子时, each branch spans 2 hours
  // Map 24h to index 0..11
  // 子时: 23,0 ; 丑:1,2 ; ... 亥:21,22
  if (h === 23 || h === 0) return 0;
  return Math.floor((h + 1) / 2);
}

function normalizeGender(g) {
  if (g === '男' || g.toLowerCase() === 'male' || g === 'm') return '男';
  if (g === '女' || g.toLowerCase() === 'female' || g === 'f') return '女';
  return '男';
}

function simplifyStars(stars = []) {
  return (stars || []).map((s) => ({
    name: s?.name ?? s,
    type: s?.type ?? null,
    brightness: s?.brightness ?? null,
    mutagen: s?.mutagen ?? null,
    scope: s?.scope ?? null,
  }));
}

try {
  const timeIndex = toIztroTimeIndex(hour);
  const g = normalizeGender(gender);
  const astrolabe = astro.bySolar(date, timeIndex, g, fixLeap, lang);

  const basic = {
    solarDate: astrolabe.solarDate,
    lunarDate: astrolabe.lunarDate,
    chineseDate: astrolabe.chineseDate,
    time: astrolabe.time,
    sign: astrolabe.sign,
    zodiac: astrolabe.zodiac,
    soul: astrolabe.soul,
    body: astrolabe.body,
    earthlyBranchOfSoulPalace: astrolabe.earthlyBranchOfSoulPalace,
    earthlyBranchOfBodyPalace: astrolabe.earthlyBranchOfBodyPalace,
    fiveElementsClass: astrolabe.fiveElementsClass,
  };

  const palacesRaw = astrolabe.palaces || [];
  const palaces = palacesRaw.map((p) => ({
    name: p.name,
    heavenlyStem: p.heavenlyStem,
    earthlyBranch: p.earthlyBranch,
    isBodyPalace: !!p.isBodyPalace,
    isOriginalPalace: !!p.isOriginalPalace,
    majorStars: simplifyStars(p.majorStars),
    minorStars: simplifyStars(p.minorStars),
    adjectiveStars: simplifyStars(p.adjectiveStars),
    changsheng12: p.changsheng12 ?? null,
    doctor: p.doctor ?? null,
    jiangqian12: p.jiangqian12 ?? null,
    suiqian12: p.suiqian12 ?? null,
  }));

  const out = {
    ok: true,
    engine: 'iztro',
    engineVersion: '2.x',
    input: { date, hour24: hour, timeIndex, gender: g, fixLeap, lang },
    basic,
    palaces,
  };

  process.stdout.write(JSON.stringify(out));
} catch (e) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e?.message || e) }));
  process.exit(1);
}
