/* 브리핑 화면과 내려받기 HTML 이 같이 쓰는 문구 조각 */
import {esc, mins, glyph} from './format.js';

// 후보 지점은 체크 번호(1, 2, 3…)와 헷갈리지 않게 문자로 부른다
export var LETTERS = 'ABCDEFGH';

export function distLabel(m){ return m >= 1000 ? (m / 1000) + 'km' : m + 'm'; }

function placeOf(B, idx){
  if (idx === -1) return B.trip.origin;
  if (idx === null || idx === undefined) return B.trip.goal;
  var it = B.items[idx];
  if (it.type === 'hazard') return (idx + 1) + '번 사고 이력 지점';
  return (idx + 1) + '번 ' + (it.place || it.label);
}

// 받침 있으면 a, 없으면 b (을/를, 이에요/예요)
export function josa(word, a, b){
  var ch = String(word || '').replace(/[’')\s]+$/, '').slice(-1);
  if (ch >= '가' && ch <= '힣') return (ch.charCodeAt(0) - 0xAC00) % 28 ? a : b;
  return /[LMNR0136]/i.test(ch) ? a : b;
}

function roadsText(roads){
  return roads.map(function(r){ return esc(r.name) + ' <span class="muted">' + r.km + 'km</span>'; }).join(' → ');
}

// 체크 지점 사이 구간: "어디서 출발해 어떤 도로를 얼마나 가면 다음 지점이 나오는지"
export function segHtml(sg, B, k, interactive){
  var from = placeOf(B, sg.from), to = placeOf(B, sg.to);
  var first = sg.from === -1, last = sg.to === null;
  var nxt = last ? null : B.items[sg.to];
  var short = sg.km < 1;
  var lead;
  if (short && !first){
    lead = '<b>' + esc(from) + '</b>' + josa(from, '을', '를') + ' 지나자마자 <b>' + sg.km + 'km</b> 만에 '
      + (last ? '<b>' + esc(to) + '</b>에 도착해요.' : '<b>' + esc(to) + '</b>' + josa(to, '이', '가') + ' 이어져요. 미리 같이 준비해 두세요.');
  } else {
    lead = (first ? '<b>' + esc(from) + '</b>에서 출발해 ' : '<b>' + esc(from) + '</b>' + josa(from, '을', '를') + ' 지나면 ')
      + (sg.roads.length ? roadsText(sg.roads) + ' 순서로 ' : '')
      + '약 <b>' + esc(mins(sg.min)) + '</b>(' + sg.km + 'km) 가요. '
      + (last ? '그러면 <b>' + esc(to) + '</b>에 도착해요.'
              : '그 다음이 <b>' + esc(to) + '</b>' + josa(to, '이에요', '예요') + ' (출발 후 ' + nxt.km + 'km).');
  }
  var notes = [];
  if (sg.prep_m) notes.push('📍 ' + esc(to) + ' <b>' + esc(distLabel(sg.prep_m)) + ' 앞</b>부터 준비를 시작해요'
    + (nxt.target ? ' — 표지판에서 ‘' + esc(nxt.target) + '’ 방면' : '') + '.');
  if (sg.cameras) notes.push('단속카메라 ' + sg.cameras + '곳');
  if (sg.zones) notes.push('보호구역 ' + sg.zones + '곳 (30km/h)');
  var steps = '';
  if (sg.steps.length){
    var li = sg.steps.map(function(st){
      return '<li><span class="gl" aria-hidden="true">' + glyph(null, st.text) + '</span><span>' + esc(st.text)
        + ' <span class="muted">' + st.km + 'km</span></span></li>';
    }).join('');
    steps = sg.steps.length > 4
      ? '<details class="seg-steps"><summary>가는 동안 안내 ' + sg.steps.length + '번 보기</summary><ol>' + li + '</ol></details>'
      : '<ol class="seg-steps-list">' + li + '</ol>';
  }
  return '<div class="seg-card">'
    + '<div class="seg-head"><span class="seg-ic" aria-hidden="true">' + (first ? '●' : last ? '◎' : '│') + '</span>'
    + '<span class="seg-ttl">' + esc(from) + ' → ' + esc(to) + '</span>'
    + '<span class="seg-len">' + sg.from_km + '–' + sg.to_km + 'km</span></div>'
    + '<p class="seg-lead">' + lead + '</p>'
    + (notes.length ? '<p class="seg-notes">' + notes.join(' · ') + '</p>' : '')
    + steps
    + (interactive ? '<button class="link seg-map" data-seg="' + k + '">지도에서 이 구간 보기</button>' : '')
    + '</div>';
}
