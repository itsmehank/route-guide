/* 출발 전 브리핑 — 체크리스트를 한 항목씩 펼쳐 '멀리서 가까이' 준비 지점 로드뷰를 넘겨 본다.
   데이터는 /api/briefing (LLM 을 새로 부르지 않는다. 이미 만든 AI 설명이 있으면 곁들인다). */
import {esc, mins, won, CONG, hzInfo} from './format.js';
import {LETTERS, distLabel, segHtml} from './briefing-text.js';
import {exportBriefing} from './briefing-export.js';

var $ = function(s, el){ return (el || document).querySelector(s); };
var params = new URLSearchParams(location.search);
var B = null, map = null, active = 0, cand = {}, done = {}, pano = null, panoBox = null;
var itemMarks = [], candMarks = [];
var storeKey = 'brief:' + location.search;

function ll(p){ return new naver.maps.LatLng(p[1], p[0]); }
function announce(t){ var el = $('#status'); el.textContent = ''; setTimeout(function(){ el.textContent = t; }, 30); }

try { done = JSON.parse(localStorage.getItem(storeKey) || '{}') || {}; } catch (e) { done = {}; }
function save(){ try { localStorage.setItem(storeKey, JSON.stringify(done)); } catch (e) {} }

/* ---------------- 그리기 ---------------- */
var SIDE = {left: ['↰', '왼쪽 차로'], right: ['↱', '오른쪽 차로']};

function itemTitle(it){
  return it.type === 'hazard' ? hzInfo(it.kind).label : it.label;
}

function headHtml(it, i){
  var meta = '출발 후 ' + it.km + 'km · 약 ' + it.min + '분';
  var ins = it.type === 'hazard' ? (it.text || '').replace(/^[^—]*—\s*/, '') : it.instruction;
  return '<button class="it-head" aria-expanded="' + (i === active) + '">'
    + '<span class="it-no">' + (done[i] ? '✓' : (i + 1)) + '</span>'
    + '<span class="it-title"><span class="meta">' + esc(meta) + '</span><span class="ins">' + esc(ins) + '</span></span>'
    + '<span class="it-badge">' + esc(itemTitle(it)) + '</span></button>';
}

function bodyHtml(it, i){
  var h = '';
  if (it.type === 'maneuver'){
    var clues = '';
    if (it.target) clues += '<span class="clue sign">' + esc(it.target) + ' <small>표지판에서 찾을 방면</small></span>';
    if (it.side) clues += '<span class="clue lane"><b>' + SIDE[it.side][0] + '</b>' + SIDE[it.side][1] + '로 준비</span>';
    if (it.place) clues += '<span class="clue">📍 ' + esc(it.place) + '</span>';
    h += clues ? '<div class="clues">' + clues + '</div>' : '';
    var c = cand[i] || 0;
    h += '<ol class="cands" aria-label="미리 볼 지점: 멀리서 가까이">' + it.candidates.map(function(x, k){
      var dist = x.dist_m >= 1000 ? (x.dist_m / 1000) + 'km' : x.dist_m + 'm';
      return '<li><button data-c="' + k + '" aria-current="' + (k === c) + '" aria-label="' + LETTERS[k] + ' 지점, ' + esc(dist) + ' 앞">'
        + '<span class="dot">' + LETTERS[k] + '</span><span class="lb">' + esc(dist) + ' 앞</span></button></li>';
    }).join('') + '</ol>';
    var x = it.candidates[c];
    h += '<div class="bview loading"><div class="pano-slot"></div><div class="cap">' + esc(LETTERS[c] + ' · ' + x.title + (x.seconds ? ' · 약 ' + x.seconds + '초 전' : '')) + '</div>'
      + '<button class="full" aria-label="로드뷰 크게 보기">⤢</button></div>';
    h += '<p class="say"><b>' + LETTERS[c] + ' · ' + esc(x.title) + '</b>' + esc(x.say) + '</p>';
    if (it.ai_notes.length || it.ai_pick)
      h += '<p class="ainote"><span class="ai-badge">AI</span>' + esc(it.ai_notes.concat(it.ai_pick ? [it.ai_pick] : []).join(' ')) + '</p>';
  } else {
    h += '<div class="clues"><span class="clue">' + esc(it.detail || '') + '</span><span class="clue">경로에서 ' + it.distance_m + 'm</span></div>';
    h += '<div class="bview loading"><div class="pano-slot"></div><div class="cap">이 지점 60m 앞에서 본 모습</div>'
      + '<button class="full" aria-label="로드뷰 크게 보기">⤢</button></div>';
    h += '<p class="say"><b>사고가 반복된 곳</b>' + esc(it.text) + '. 이 근처에서는 속도를 줄이고 보행자·옆 차로를 한 번 더 살펴.</p>';
  }
  h += '<div class="it-actions">'
    + (i > 0 ? '<button class="btn" data-act="prev">‹ 이전</button>' : '')
    + '<button class="btn primary" data-act="ok">' + (done[i] ? '확인함 · 다음 ›' : '확인했어요 · 다음 ›') + '</button></div>';
  return h;
}

function render(){
  var r = B.route, t = B.trip, s = B.summary;
  var total = B.legs.reduce(function(a, l){ return a + l.km; }, 0) || 1;
  var html = '<header class="b-top"><h1>출발 전 브리핑</h1>'
    + '<div class="trip">' + esc(t.origin) + (t.via ? ' → ' + esc(t.via) : '') + ' → ' + esc(t.goal) + ' · ' + esc(r.label) + '</div>'
    + '<div class="b-prog"><span class="bar"><i></i></span><span class="cnt"></span>'
    + '<button class="btn small" data-nav="prev" aria-label="이전 항목">‹</button><button class="btn small" data-nav="next" aria-label="다음 항목">›</button>'
    + '<button class="btn small" data-act="export" title="이 브리핑을 HTML 파일로 저장">⬇ 저장</button></div></header>';

  // 1) 한눈에
  html += '<section class="b-sec"><h2>한눈에 보기</h2><div class="b-facts">'
    + '<span><b>' + esc(mins(r.duration_min)) + '</b> 예상</span><span><b>' + r.distance_km + 'km</b></span>'
    + '<span>' + (r.toll_fare ? '통행료 ' + won(r.toll_fare) : '통행료 없음') + '</span>'
    + '<span>체크 지점 <b>' + B.items.length + '</b>곳</span>'
    + (s.cameras ? '<span>단속카메라 ' + s.cameras + '</span>' : '')
    + (s.zones ? '<span>보호구역 ' + s.zones + '</span>' : '') + '</div>'
    + (B.ai.headline || B.ai.verdict ? '<div class="b-ai"><span class="ai-badge">AI 요약</span><p>' + esc(B.ai.verdict || B.ai.headline) + '</p></div>' : '')
    + '</section>';

  // 2) 길 이해하기
  html += '<section class="b-sec"><h2>길 이해하기 — 어떤 도로를 타나</h2>'
    + (B.ai.overview.length ? '<p class="lead">' + esc(B.ai.overview.join(' ')) + '</p>' : '')
    + '<div class="legs" aria-hidden="true">' + B.legs.map(function(l){
        return '<i style="flex:' + l.km + ';background:' + (l.name === '일반도로' ? '#c3cad3' : (CONG[l.congestion] || CONG[0]).color) + '"></i>'; }).join('') + '</div>'
    + '<ol class="leglist">' + B.legs.map(function(l){
        return '<li><span class="km0">' + l.from_km + 'km</span><span class="nm">' + esc(l.name) + '</span><span class="len">' + l.km + 'km</span></li>'; }).join('') + '</ol>'
    + '</section>';

  // 3) 체크리스트
  html += '<section class="b-sec"><h2>체크리스트 — 가는 순서대로</h2>'
    + '<p class="lead">출발부터 도착까지 순서대로 읽으면 돼요. 회색 카드는 <b>그냥 따라가는 구간</b>, 번호 카드는 <b>미리 준비할 지점</b>이에요. '
    + '번호 카드의 A·B·C는 <b>멀리서 가까이</b> 미리 볼 곳 — 표지판이 보이는 곳 → 차로를 옮길 곳 → 진입 직전. 로드뷰로 실제 시야를 확인하세요.</p>'
    + '<ol class="chk">' + B.items.map(function(it, i){
        return '<li class="seg">' + segHtml(B.segments[i], B, i, true) + '</li>'
          + '<li class="it' + (it.type === 'hazard' ? ' hz' : '') + (done[i] ? ' done' : '') + '" id="it-' + i + '" data-i="' + i + '">'
          + headHtml(it, i) + '<div class="it-body"></div></li>';
      }).join('')
    + '<li class="seg">' + segHtml(B.segments[B.items.length], B, B.items.length, true) + '</li>'
    + '</ol></section>';

  if (B.minor_hazards.length){
    var cams = B.minor_hazards.filter(function(h){ return h.type === 'speed_camera'; });
    var zones = B.minor_hazards.filter(function(h){ return h.type !== 'speed_camera'; });
    html += '<section class="b-sec b-minor"><h2>지나가며 속도만 지키면 되는 곳</h2>'
      + (cams.length ? '<p>단속카메라 ' + cams.length + '곳: ' + cams.slice(0, 6).map(function(h){ return h.km + 'km(' + esc(h.text.replace(/^.*제한속도\s*/, '').replace('km/h', '')) + ')'; }).join(', ') + (cams.length > 6 ? ' 외' : '') + '</p>' : '')
      + (zones.length ? '<p>보호구역 ' + zones.length + '곳 — 대부분 제한속도 30km/h. 학교·복지시설 앞에서는 미리 속도를 줄여.</p>' : '')
      + '</section>';
  }
  html += '<footer class="b-foot">표지판 위치는 고속도로 예고 표지의 일반 배치(2km·1km·500m)와 교차로 앞 거리로 고른 후보예요. 실제 표지 위치는 로드뷰로 확인하세요. '
    + '위험 지점은 공공데이터(사고다발·단속·보호구역) 기준이에요. 실시간 교통과 공사는 반영되지 않아요.</footer>';

  var rep = $('#report');
  rep.innerHTML = html;
  rep.removeAttribute('aria-busy');

  rep.addEventListener('click', function(e){
    var b = e.target.closest('button'); if (!b) return;
    var li = b.closest('.it');
    if (b.dataset.nav) return go(active + (b.dataset.nav === 'next' ? 1 : -1));
    if (b.classList.contains('it-head')) return go(+li.dataset.i);
    if (b.dataset.c !== undefined){ cand[active] = +b.dataset.c; return refreshActive(); }
    if (b.dataset.act === 'ok'){ done[active] = true; save(); return go(active + 1, true); }
    if (b.dataset.act === 'prev') return go(active - 1);
    if (b.dataset.act === 'export') return exportBriefing(B, done, b);
    if (b.dataset.seg !== undefined) return showSegment(+b.dataset.seg);
    if (b.classList.contains('full')){
      var v = b.closest('.bview'); var on = !v.classList.contains('full-on');
      v.classList.toggle('full-on', on); b.textContent = on ? '✕' : '⤢';
      setTimeout(resizePano, 30);
    }
  });
  document.addEventListener('keydown', function(e){
    if (e.target.closest('input, textarea')) return;
    if (e.key === 'Escape'){ var f = $('.bview.full-on'); if (f){ f.classList.remove('full-on'); setTimeout(resizePano, 30); } }
    if (e.key === 'j' || e.key === 'ArrowDown' && e.altKey) go(active + 1);
    if (e.key === 'k' || e.key === 'ArrowUp' && e.altKey) go(active - 1);
    var it = B.items[active];
    if (it && it.type === 'maneuver' && (e.key === 'ArrowRight' || e.key === 'ArrowLeft') && !e.target.closest('.cands') ){
      var n = (cand[active] || 0) + (e.key === 'ArrowRight' ? 1 : -1);
      if (n >= 0 && n < it.candidates.length){ cand[active] = n; refreshActive(); }
    }
  });
}

function progress(){
  var n = Object.keys(done).filter(function(k){ return done[k] && B.items[k]; }).length;
  $('.b-prog .bar i').style.width = (B.items.length ? n / B.items.length * 100 : 0) + '%';
  $('.b-prog .cnt').textContent = n + ' / ' + B.items.length + ' 확인';
}

var fitOnFocus = true;

function go(i, fromOk, noScroll){
  if (i < 0) return;
  if (i >= B.items.length){
    active = B.items.length - 1; refreshAll();
    announce('모든 항목을 확인했어요. 안전 운전하세요!');
    return;
  }
  active = i;
  refreshAll();
  var el = document.getElementById('it-' + i);
  if (noScroll) return;                      // 처음 열 때는 맨 위(출발 구간)부터 읽게 둔다
  el.querySelector('.it-head').focus({preventScroll: true});
  // 펼친 카드의 로드뷰가 자리를 잡은 뒤에 스크롤한다 (먼저 하면 레이아웃이 바뀌며 스크롤이 끊긴다)
  setTimeout(function(){
    var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({block: 'start', behavior: fromOk && !reduce && !document.hidden ? 'smooth' : 'auto'});
  }, 60);
}

function refreshAll(){
  document.querySelectorAll('.it').forEach(function(li){
    var i = +li.dataset.i, on = i === active;
    li.classList.toggle('active', on);
    li.classList.toggle('done', !!done[i]);
    li.querySelector('.it-no').textContent = done[i] ? '✓' : (i + 1);
    li.querySelector('.it-head').setAttribute('aria-expanded', String(on));
    li.querySelector('.it-body').innerHTML = on ? bodyHtml(B.items[i], i) : '';
  });
  progress();
  refreshActive(true);
}

function overview(){ if (segLine){ segLine.setMap(null); segLine = null; } fitAll(); }

/* 펼친 항목의 로드뷰·지도만 갱신 */
function refreshActive(rebuilt){
  var it = B.items[active]; if (!it) return;
  var li = document.getElementById('it-' + active);
  if (!rebuilt) li.querySelector('.it-body').innerHTML = bodyHtml(it, active);
  var view = li.querySelector('.bview'), slot = li.querySelector('.pano-slot');
  var spot = it.type === 'maneuver' ? it.candidates[cand[active] || 0] : {coord: it.view, bearing: it.bearing};
  showPano(view, slot, spot);
  drawFocus(it, !fitOnFocus);
  fitOnFocus = true;
}

/* ---------------- 로드뷰: 뷰어 하나를 펼친 항목으로 옮겨 다니며 쓴다 ---------------- */
function showPano(view, slot, spot){
  if (!naver.maps.Panorama){ view.classList.remove('loading'); view.classList.add('none'); return; }
  if (!panoBox){
    panoBox = document.createElement('div'); panoBox.className = 'pano';
  }
  slot.replaceWith(panoBox);
  var pov = {pan: spot.bearing, tilt: 2, fov: 90};      // 표지판이 보이도록 살짝 위로
  var mark = function(st){ view.classList.remove('loading'); view.classList.toggle('none', st !== 'ok'); };
  try {
    if (!pano){
      pano = new naver.maps.Panorama(panoBox, {position: ll(spot.coord), pov: pov,
        flightSpot: false, aroundControl: false, zoomControl: false, logoControl: false});
      naver.maps.Event.addListener(pano, 'pano_status', function(st){
        var v = panoBox.closest('.bview'); if (!v) return;
        v.classList.remove('loading'); v.classList.toggle('none', st === naver.maps.PanoramaStatus.ERROR);
      });
    } else {
      pano.setPosition(ll(spot.coord)); pano.setPov(pov);
      setTimeout(resizePano, 0);
      mark('ok');
    }
  } catch (e) { mark('none'); }
}
function resizePano(){
  if (pano && panoBox) try { pano.setSize(new naver.maps.Size(panoBox.clientWidth, panoBox.clientHeight)); } catch (e) {}
}

/* ---------------- 지도 ---------------- */
function initMap(){
  map = new naver.maps.Map('bmap', {
    zoomControl: true, zoomControlOptions: {position: naver.maps.Position.RIGHT_CENTER, style: naver.maps.ZoomControlStyle.SMALL},
    mapTypeControl: true, logoControlOptions: {position: naver.maps.Position.BOTTOM_RIGHT}
  });
  var path = B.path.map(ll);
  new naver.maps.Polyline({map: map, path: path, strokeColor: '#ffffff', strokeWeight: 11, strokeOpacity: .95, zIndex: 10});
  new naver.maps.Polyline({map: map, path: path, strokeColor: '#2e6ff2', strokeWeight: 6, zIndex: 11});
  [['#2e6ff2', B.path[0]], ['#e8452c', B.path[B.path.length - 1]]].forEach(function(e){
    new naver.maps.Marker({position: ll(e[1]), map: map, zIndex: 50,
      icon: {content: '<div class="pin-se" style="--c:' + e[0] + '"></div>', anchor: new naver.maps.Point(0, 0)}});
  });
  B.items.forEach(function(it, i){
    var m = new naver.maps.Marker({position: ll(it.coord), map: map, zIndex: 100 + i, title: itemTitle(it),
      icon: {content: '<b class="mk' + (it.type === 'hazard' ? ' hz' : '') + '">' + (i + 1) + '</b>', anchor: new naver.maps.Point(0, 0)}});
    naver.maps.Event.addListener(m, 'click', function(){ go(i); });
    itemMarks.push(m);
  });
  fitAll();
}

// 구간 카드의 '지도에서 보기': 그 구간만 굵게 강조해 맞춘다
var segLine = null;
function showSegment(k){
  var sg = B.segments[k];
  var a = k === 0 ? 0 : B.items[k - 1].path_index, b = k < B.items.length ? B.items[k].path_index : B.path.length - 1;
  var pts = B.path.slice(a, b + 1);
  if (segLine) segLine.setMap(null);
  segLine = new naver.maps.Polyline({map: map, path: pts.map(ll), strokeColor: '#ffa000', strokeWeight: 9, strokeOpacity: .9, zIndex: 12});
  var bb = new naver.maps.LatLngBounds(ll(pts[0]), ll(pts[0]));
  pts.forEach(function(p){ bb.extend(ll(p)); });
  map.fitBounds(bb, {top: 50, right: 60, bottom: 60, left: 50});
  announce(sg.from_km + 'km부터 ' + sg.to_km + 'km 구간을 지도에 표시했어요.');
}

function fitAll(){
  var b = new naver.maps.LatLngBounds(ll(B.path[0]), ll(B.path[0]));
  B.path.forEach(function(p){ b.extend(ll(p)); });
  map.fitBounds(b, {top: 40, right: 60, bottom: 60, left: 40});
}

function drawFocus(it, keepView){
  candMarks.forEach(function(m){ m.setMap(null); }); candMarks = [];
  itemMarks.forEach(function(m, i){
    var cls = 'mk' + (B.items[i].type === 'hazard' ? ' hz' : '') + (done[i] ? ' done' : '') + (i === active ? ' on' : '');
    m.setIcon({content: '<b class="' + cls + '">' + (done[i] ? '✓' : i + 1) + '</b>', anchor: new naver.maps.Point(0, 0)});
    m.setZIndex(i === active ? 400 : 100 + i);
  });
  var pts = [it.coord];
  if (it.type === 'maneuver'){
    var c = cand[active] || 0;
    it.candidates.forEach(function(x, k){
      var dist = x.dist_m >= 1000 ? (x.dist_m / 1000) + 'km' : x.dist_m + 'm';
      var m = new naver.maps.Marker({position: ll(x.coord), map: map, zIndex: k === c ? 380 : 300,
        icon: {content: '<div class="cmk' + (k === c ? ' on' : '') + '"><i>' + LETTERS[k] + '</i><span>' + esc(dist) + ' 앞</span></div>', anchor: new naver.maps.Point(0, 0)}});
      naver.maps.Event.addListener(m, 'click', function(){ cand[active] = k; refreshActive(); });
      candMarks.push(m);
      pts.push(x.coord);
    });
  } else pts.push(it.view);
  if (keepView) return;
  var b = new naver.maps.LatLngBounds(ll(pts[0]), ll(pts[0]));
  pts.forEach(function(p){ b.extend(ll(p)); });
  map.fitBounds(b, {top: 70, right: 70, bottom: 70, left: 70});
  if (map.getZoom() > 17) map.setZoom(17);
}

/* ---------------- 부팅 ---------------- */
function boot(){
  if (!params.get('start') || !params.get('goal')){
    $('#report').innerHTML = '<div class="b-loading">경로 정보가 없어요. 길찾기 화면에서 ‘출발 전 브리핑’을 눌러 열어 주세요.</div>';
    return;
  }
  fetch('/api/briefing?' + params.toString()).then(function(r){ return r.json(); }).then(function(d){
    if (d.error) throw new Error(d.error);
    B = d;
    document.title = '출발 전 브리핑 · ' + d.trip.origin + ' → ' + d.trip.goal;
    render();
    initMap();
    var first = B.items.findIndex(function(_, i){ return !done[i]; });
    fitOnFocus = false;                      // 처음엔 전체 경로를 보여준다
    go(first < 0 ? 0 : first, false, true);
    window.scrollTo(0, 0);
    document.getElementById('fitall').onclick = overview;
    announce('체크 지점 ' + B.items.length + '곳을 순서대로 확인할 수 있어요.');
  }).catch(function(e){
    console.warn('[briefing]', e);
    $('#report').innerHTML = '<div class="b-loading">브리핑을 만들지 못했어요. 길찾기 화면에서 다시 열어 주세요.<br><small>' + esc(e.message) + '</small></div>';
  });
}

boot();
