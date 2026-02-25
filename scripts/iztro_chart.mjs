#!/usr/bin/env node
import { astro } from 'iztro';

function usage() {
  console.error('Usage: node scripts/iztro_chart.mjs --date YYYY-M-D --hour 0-23 --gender 男|女 [--lang zh-CN] [--fixLeap true|false] [--includeHoroscope true|false] [--targetDate YYYY-M-D] [--targetHour 0-23]');
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
const includeHoroscopeRaw = parseArg('--includeHoroscope', 'false');
const targetDateArg = parseArg('--targetDate', '');
const targetHourRaw = parseArg('--targetHour', '');

if (!date || hourRaw == null) usage();
const hour = Number(hourRaw);
if (!Number.isInteger(hour) || hour < 0 || hour > 23) usage();

const fixLeap = String(fixLeapRaw).toLowerCase() !== 'false';
const includeHoroscope = String(includeHoroscopeRaw).toLowerCase() === 'true';

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

function simplifyHoroscopeNode(node = null) {
  if (!node || typeof node !== 'object') return null;
  return {
    index: node.index ?? null,
    name: node.name ?? null,
    heavenlyStem: node.heavenlyStem ?? null,
    earthlyBranch: node.earthlyBranch ?? null,
    palaceNames: Array.isArray(node.palaceNames) ? node.palaceNames : [],
    mutagen: Array.isArray(node.mutagen) ? node.mutagen : [],
    yearlyDecStar: Array.isArray(node.yearlyDecStar) ? node.yearlyDecStar : [],
    starsByPalace: Array.isArray(node.stars)
      ? node.stars.map((palaceStars = []) => simplifyStars(palaceStars))
      : [],
  };
}

function toTargetDateTime(targetDateStr, targetHour24) {
  const safeDate = (targetDateStr || '').trim();
  if (!safeDate) return new Date();
  if (targetHour24 == null) {
    return new Date(`${safeDate}T12:00:00`);
  }
  return new Date(`${safeDate}T${String(targetHour24).padStart(2, '0')}:00:00`);
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

  if (includeHoroscope) {
    const targetHour = targetHourRaw === '' ? null : Number(targetHourRaw);
    if (targetHour != null && (!Number.isInteger(targetHour) || targetHour < 0 || targetHour > 23)) {
      throw new Error('targetHour must be 0-23');
    }

    const targetTimeIndex = targetHour == null ? undefined : toIztroTimeIndex(targetHour);
    const targetDate = toTargetDateTime(targetDateArg, targetHour);
    const hz = astrolabe.horoscope(targetDate, targetTimeIndex);

    out.horoscope = {
      solarDate: hz?.solarDate ?? null,
      lunarDate: hz?.lunarDate ?? null,
      decadal: simplifyHoroscopeNode(hz?.decadal),
      age: {
        index: hz?.age?.index ?? null,
        nominalAge: hz?.age?.nominalAge ?? null,
        name: hz?.age?.name ?? null,
        heavenlyStem: hz?.age?.heavenlyStem ?? null,
        earthlyBranch: hz?.age?.earthlyBranch ?? null,
        palaceNames: Array.isArray(hz?.age?.palaceNames) ? hz.age.palaceNames : [],
        mutagen: Array.isArray(hz?.age?.mutagen) ? hz.age.mutagen : [],
      },
      yearly: simplifyHoroscopeNode(hz?.yearly),
      monthly: simplifyHoroscopeNode(hz?.monthly),
      daily: simplifyHoroscopeNode(hz?.daily),
      hourly: simplifyHoroscopeNode(hz?.hourly),
    };
  }

  process.stdout.write(JSON.stringify(out));
} catch (e) {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e?.message || e) }));
  process.exit(1);
}
