/* 경로 비교 — 정보 순서: 결론 한 줄 → 핵심 4지표 → 상황별 비교 → 경로별(총평 · 출발 전 체크리스트 · 위험 지점)
   비교표·위험 지점은 /api/evaluate 로 바로 그리고, AI 설명은 스트리밍으로 도착하는 대로 채운다. */
import {esc, mins, won, hzInfo, hzIcon, HZ_ORDER} from '../format.js';
import {vias} from '../store.js';

var built = null, ticker = null;

function sent(x){
  if (!x || !x.text) return '';
  var cls = 's' + (x.general_knowledge ? ' gk' : '') + (x.unverified ? ' unv' : '');
  var badge = x.general_knowledge ? '<i class="bdg gk">일반 요령</i>'
            : (x.unverified ? '<i class="bdg unv">근거 미확인</i>' : '');
  return '<span class="' + cls + '" title="근거: ' + esc((x.basis || []).join(', ') || '없음') + '">' + esc(x.text) + badge + '</span> ';
}

// 동률은 모두 강조하고, 모두 같으면 아무것도 강조하지 않는다 (첫 칸만 칠하면 없는 우열이 생긴다)
function row(label, vals, fmt, best, tip){
  var target = best === 'max' ? Math.max.apply(null, vals) : Math.min.apply(null, vals);
  var allSame = vals.every(function(v){ return v === vals[0]; });
  return '<tr><th scope="row"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + label + (tip ? ' <i class="tip">ⓘ</i>' : '') + '</th>'
    + vals.map(function(v, i){
        var on = !allSame && best && v === target;
        return '<td' + (on ? ' class="best"' : '') + '>' + fmt(v, i) + '</td>';
      }).join('') + '</tr>';
}

function tableHtml(ev, s){
  var routes = ev.routes;
  var idx = {}; s.routes.forEach(function(r, i){ idx[r.option] = i; });
  var head = '<tr><td></td>' + routes.map(function(r){
    return '<th scope="col"><span class="num">' + ((idx[r.id] ?? 0) + 1) + '</span>' + esc(r.label.split(' · ')[0]) + '</th>';
  }).join('') + '</tr>';
  var core = row('시간', routes.map(function(r){ return r.summary.duration_min; }), function(v){ return esc(mins(v)); }, 'min')
    + row('거리', routes.map(function(r){ return r.summary.distance_km; }), function(v){ return v + 'km'; }, 'min')
    + row('비용', routes.map(function(r){ return r.summary.toll_fare + r.summary.fuel_price; }), function(v, i){
        var sm = routes[i].summary;
        return won(v) + '<small>' + (sm.toll_fare ? '통행료 ' + won(sm.toll_fare) : '통행료 무료') + '</small>';
      }, 'min', '통행료 + 연료비(1종 휘발유 기준)')
    + row('운전 편의', routes.map(function(r){ return r.comfort.rank; }), function(v, i){
        return (routes[i].comfort.tied ? '공동 ' : '') + v + '위';
      }, 'min', '분기·합류·유턴·저속 구간을 점수로 매긴 순위. 낮을수록 초보에게 편하다');
  var more = row('분기점', routes.map(function(r){ return r.metrics.maneuver_total; }), function(v){ return v + '개'; }, 'min')
    + row('합류·분기', routes.map(function(r){ return r.metrics.lane_shift_count; }), function(v){ return v + '번'; }, 'min',
          '차선을 옮길 일이 생기는 합류·분기·출구·고가/지하 진입 횟수 (차선 수 자체는 데이터에 없음)')
    + row('유턴', routes.map(function(r){ return r.metrics.uturn_count; }), function(v){ return v + '번'; }, 'min')
    + row('고속화 비율', routes.map(function(r){ return r.metrics.highway_ratio; }), function(v){ return Math.round(v*100) + '%↑'; }, 'max',
          '교통정보가 있는 구간만 집계한 하한값')
    + row('위험 지점', routes.map(function(r){ return (r.hazards || []).length; }), function(v){ return v + '곳'; }, 'min');
  return '<table class="cmp">' + head + core + '</table>'
    + '<details class="more"><summary>운전 난이도 자세히</summary><table class="cmp">' + head + more + '</table></details>';
}

function aiHtml(n){
  var nd = n.data;
  var head = nd && nd.comparison && nd.comparison.headline;
  var streaming = n.status === 'streaming';
  var stage = n.stage === 'writing' ? '설명을 쓰는 중' : (n.stage === 'retry' ? '다시 시도하는 중' : '경로를 살펴보는 중');
  var html = '';
  if (head && head.text){
    html += '<p class="headline">' + sent(head) + '</p>';
  } else if (streaming){
    html += '<div class="skel-line"></div><div class="skel-line short"></div>';
  }
  if (streaming){
    html += '<div class="progress" role="status"><span class="dots" aria-hidden="true"></span>AI가 ' + stage
      + ' · <span class="elapsed">0초</span><button class="btn small" data-act="stop">중지</button></div>';
  } else if (n.status === 'error'){
    html += '<div class="notice">AI 설명을 만들지 못했어요. 비교표와 위험 지점은 그대로 볼 수 있어요.'
      + '<br><small>' + esc(n.error || '') + '</small> <button class="btn small" data-act="regen">다시 시도</button></div>';
  } else if (n.status === 'stopped'){
    html += '<div class="notice">설명 생성을 멈췄어요. <button class="btn small" data-act="regen">다시 생성</button></div>';
  }
  if (head && head.text || streaming)
    html = '<span class="ai-badge">AI 추천</span>' + html;
  return html;
}

function summaryHtml(n){
  var sm = n.data && n.data.comparison && n.data.comparison.summary;
  if (!sm || !sm.length) return '';
  return '<h4>상황별로 고르면</h4><p>' + sm.map(sent).join('') + '</p>';
}

function hazardsHtml(er, ri){
  var list = er.hazards || [];
  if (!list.length) return '<h4>위험 지점</h4><p class="muted">이 경로에서 공공데이터로 확인된 위험 지점이 없어요.</p>';
  var groups = {};
  list.forEach(function(h, idx){ (groups[h.type] = groups[h.type] || []).push([h, idx]); });
  var types = HZ_ORDER.filter(function(t){ return groups[t]; })
    .concat(Object.keys(groups).filter(function(t){ return HZ_ORDER.indexOf(t) < 0; }));
  var chips = types.map(function(t){
    var info = hzInfo(t);
    return '<span class="hzchip tone-' + info.tone + '">' + hzIcon(t, groups[t][0][0].text) + esc(info.label) + ' ' + groups[t].length + '</span>';
  }).join('');
  var body = types.map(function(t){
    var info = hzInfo(t), g = groups[t];
    var open = info.tone === 'acc' || info.tone === 'ice';
    return '<details class="hzgroup"' + (open ? ' open' : '') + ' data-k="hz-' + ri + '-' + t + '">'
      + '<summary><span class="hzchip tone-' + info.tone + '">' + hzIcon(t, g[0][0].text) + esc(info.label) + '</span> ' + g.length + '곳</summary><ul>'
      + g.map(function(p){
          var h = p[0];
          return '<li><button class="hzitem" data-hz="' + p[1] + '" data-r="' + esc(er.id) + '">'
            + esc((h.text || '').replace(/^[^—]*—\s*/, ''))
            + '<small>' + esc(h.detail || '') + (h.detail ? ' · ' : '') + '경로에서 ' + h.distance_m + 'm</small></button></li>';
        }).join('') + '</ul></details>';
  }).join('');
  return '<h4>위험 지점 <span class="muted">공공데이터 ' + list.length + '곳 · 누르면 지도에서 보여줘요</span></h4>'
    + '<div class="hzchips">' + chips + '</div>' + body;
}

function hazardNotesHtml(nr, ri){
  var hn = nr && nr.hazard_notes ? nr.hazard_notes.filter(function(x){ return x.text; }) : [];
  if (!hn.length) return '';
  return '<h4>AI 주의 안내</h4><p>' + hn.slice(0, 2).map(sent).join('') + '</p>'
    + (hn.length > 2 ? '<details class="more" data-k="hn-' + ri + '"><summary>' + (hn.length - 2) + '개 더 보기</summary><p>'
       + hn.slice(2).map(sent).join('') + '</p></details>' : '');
}

function checklistHtml(er, nr, ri, s){
  var items = [];
  var r = s.routes[ri];
  if (nr){
    nr.cautions.forEach(function(c){ items.push({html: sent(c), step: c.step}); });
    nr.roadview_picks.forEach(function(pk){
      var same = items.find(function(it){ return it.step === pk.step; });
      var g = r && r.guides[pk.step];
      if (same){ same.html += '<small>로드뷰로 볼 것: ' + esc(pk.reason) + '</small>'; return; }
      items.push({html: '<b>' + esc(g ? g.instructions : '') + '</b><small>' + esc(pk.reason) + '</small>', step: pk.step});
    });
  } else {
    // 서술이 없어도 복잡 분기는 엔진이 알고 있다
    er.metrics.complex_points.forEach(function(cp){
      items.push({html: '<b>' + esc(cp.label) + '</b> — ' + esc(cp.instruction), step: cp.step});
    });
  }
  if (!items.length) return '';
  return '<h4>출발 전 체크리스트</h4><ul class="check">' + items.map(function(it){
    var go = it.step !== null && it.step !== undefined;
    return '<li><span class="ck" aria-hidden="true">✓</span><div>' + it.html + '</div>'
      + (go ? '<button class="btn small" data-step="' + it.step + '" data-r="' + ri + '">로드뷰</button>' : '') + '</li>';
  }).join('') + '</ul>';
}

// 패널 구역 [키, html]. 순서 = 화면 순서. AI 와 무관한 구역(위험 지점 목록·근거 사실)은 내용이 그대로라 다시 그려지지 않는다
function paneSections(s){
  var ev = s.cmp.data.evaluation, nd = s.cmp.narr.data;
  var r = s.routes[s.sel]; if (!r) return [];
  var er = ev.routes.find(function(x){ return x.id === r.option; }); if (!er) return [];
  var nr = nd && nd.routes ? nd.routes.find(function(x){ return x.id === er.id; }) : null;
  var done = s.cmp.narr.status === 'done';
  return [
    ['brief', '<a class="btn primary wide brief-link" target="_blank" rel="noopener" href="' + esc(briefingUrl(s)) + '">📋 이 경로로 출발 전 브리핑 보기 ↗</a>'],
    ['verdict', nr && (nr.verdict.text || nr.comfort_note.text) ? '<p class="verdict">' + sent(nr.verdict) + sent(nr.comfort_note) + '</p>' : ''],
    ['check', checklistHtml(er, done ? nr : null, s.sel, s)],
    ['hazards', hazardsHtml(er, s.sel)],
    ['hznotes', hazardNotesHtml(nr, s.sel)],
    ['overview', nr && nr.overview.length
      ? '<details class="more" data-k="ov-' + s.sel + '"><summary>이 길의 큰 줄기</summary><p>' + nr.overview.map(sent).join('') + '</p></details>' : ''],
    ['facts', '<details class="more facts" data-k="ft-' + s.sel + '"><summary>근거 사실 ' + er.facts.length + '개 (AI 설명의 출처)</summary><table class="ft">'
      + er.facts.map(function(f){ return '<tr><td>' + esc(f.id) + '</td><td>' + esc(f.text) + '</td></tr>'; }).join('') + '</table></details>']
  ];
}

function renderPane(pane, sections){
  sections.forEach(function(sec){
    var el = pane.querySelector(':scope > [data-sec="' + sec[0] + '"]');
    if (!el){ el = document.createElement('div'); el.dataset.sec = sec[0]; pane.appendChild(el); }
    keepOpen(el, sec[1]);
    el.hidden = !sec[1];
  });
}

/* 스크롤 고정: 위쪽 내용이 늘거나 줄어도, 보고 있던 요소가 화면의 같은 자리에 머물게 한다.
   (측정: 스트리밍 85초 동안 위험 지점 목록이 7번, 최대 804px 밀렸다)
   기준 요소 = 스크롤 영역 위쪽에 걸친 첫 구역·항목. 갱신 전후 그 요소의 위치 차이만큼 스크롤을 보정한다. */
function keepScroll(scroller, update){
  if (!scroller){ update(); return; }
  var top = scroller.getBoundingClientRect().top, marks = [];
  if (scroller.scrollTop > 0){
    // 고정(sticky) 경로 탭은 늘 같은 자리라 기준이 될 수 없다. 화면에 보이는 '항목'들을 기준 후보로 적어 둔다.
    // 갱신 때 통째로 바뀌는 항목(예: 완료 시 AI 체크리스트로 교체)도 있어서, 하나가 아니라 여러 개를 적고
    // 갱신 뒤에도 남아 있는 첫 후보로 보정한다. 구역 껍데기는 마지막 수단.
    var cands = scroller.querySelectorAll('.pane .hzitem, .pane .check li, .pane h4, .pane .hzgroup > summary, .pane .brief-link');
    for (var i = 0; i < cands.length && marks.length < 12; i++){
      var rc = cands[i].getBoundingClientRect();
      if (rc.height && rc.top >= top - 1) marks.push([cands[i], rc.top]);
    }
    scroller.querySelectorAll('.pane > [data-sec]').forEach(function(el){
      var rc = el.getBoundingClientRect();
      if (rc.height && rc.bottom > top) marks.push([el, rc.top]);
    });
  }
  update();
  for (var k = 0; k < marks.length; k++){
    if (!marks[k][0].isConnected) continue;
    var d = marks[k][0].getBoundingClientRect().top - marks[k][1];
    if (Math.abs(d) >= 1) scroller.scrollTop += d;
    return;
  }
}

export function briefingUrl(s){
  var r = s.routes[s.sel];
  var q = new URLSearchParams({start: s.origin.coord.join(','), goal: s.goal.coord.join(','),
                               o: s.origin.title, g: s.goal.title, route: r ? r.option : ''});
  var v = vias(s);
  if (v.length){
    q.set('waypoints', v.map(function(p){ return p.coord.join(','); }).join('|'));
    q.set('v', v.map(function(p){ return p.title; }).join(', '));
  }
  return '/briefing.html?' + q.toString();
}

function tabsHtml(s){
  return s.routes.map(function(r, i){
    return '<button role="tab" aria-selected="' + (i === s.sel) + '" data-i="' + i + '">' + (i+1) + ' · ' + esc(r.label.split(' · ')[0]) + '</button>';
  }).join('');
}

// innerHTML 을 갈아끼워도 사용자가 펼친 <details> 는 그대로 둔다
function keepOpen(el, html){
  if (el._html === html) return;                   // 바뀐 게 없으면 DOM 을 건드리지 않는다 (누르던 버튼이 사라지지 않게)
  el._html = html;
  var open = {};
  el.querySelectorAll('details[data-k]').forEach(function(d){ open[d.dataset.k] = d.open; });
  el.innerHTML = html;
  el.querySelectorAll('details[data-k]').forEach(function(d){ if (d.dataset.k in open) d.open = open[d.dataset.k]; });
}

export function renderCompare(host, s, act){
  var c = s.cmp;
  var key = s.routeKey;
  if (built !== key || !host.querySelector('.cmp-wrap')){
    host.innerHTML = '<div class="vhead"><button class="back" data-act="back" aria-label="경로 목록으로">‹</button>'
      + '<div class="vtitle">경로 비교<small>' + esc((s.origin ? s.origin.title : '') + ' → ' + (s.goal ? s.goal.title : '')
      + (vias(s).length ? ' (경유 ' + vias(s).map(function(p){ return p.title; }).join(', ') + ')' : '')) + '</small></div></div>'
      + '<div class="cmp-wrap"><section class="ai card-box" aria-live="off"></section>'
      + '<section class="tbl card-box"></section><section class="sum"></section>'
      + '<div class="tabs" role="tablist"></div><section class="pane"></section>'
      + '<p class="caveat">AI 설명은 경로 데이터와 공공데이터만 근거로 써요. 문장에 마우스를 올리면 근거 ID가 보여요.</p></div>';
    host.querySelector('[data-act=back]').onclick = act.back;
    host.onclick = function(e){
      var b = e.target.closest('button'); if (!b || !host.contains(b)) return;
      if (b.dataset.act === 'stop') return act.stopNarration();
      if (b.dataset.act === 'regen') return act.startNarration(true);
      if (b.getAttribute('role') === 'tab') return act.selectRoute(+b.dataset.i);
      if (b.dataset.hz !== undefined) return act.hazard(b.dataset.r, +b.dataset.hz);
      if (b.dataset.step !== undefined) return act.roadview(+b.dataset.r, +b.dataset.step);
    };
    built = key;
  }
  var ai = host.querySelector('.ai'), tbl = host.querySelector('.tbl'), sum = host.querySelector('.sum');
  var tabs = host.querySelector('.tabs'), pane = host.querySelector('.pane');

  if (c.status === 'loading' || c.status === 'idle'){
    tbl.innerHTML = '<div class="skel-line"></div><div class="skel-line"></div><div class="skel-line short"></div>'
      + '<p class="muted">비교표와 위험 지점을 계산하는 중…</p>';
    ai.hidden = true; sum.innerHTML = ''; tabs.innerHTML = ''; pane.innerHTML = '';
    return;
  }
  if (c.status === 'error'){
    tbl.innerHTML = '<div class="notice">비교를 계산하지 못했어요. <button class="btn small" data-act="regen">다시 시도</button></div>';
    ai.hidden = true;
    return;
  }

  keepScroll(host.closest('.pbody'), function(){
    var tsig = c.key + '|' + s.routes.length;
    if (tbl.dataset.sig !== tsig){ tbl.innerHTML = '<h4>한눈에 비교</h4>' + tableHtml(c.data.evaluation, s); tbl.dataset.sig = tsig; }

    ai.hidden = false;
    var aisig = c.narr.status + '|' + c.narr.stage + '|' + JSON.stringify(c.narr.data && c.narr.data.comparison && c.narr.data.comparison.headline);
    if (ai.dataset.sig !== aisig){ ai.innerHTML = aiHtml(c.narr); ai.dataset.sig = aisig; }
    keepOpen(sum, summaryHtml(c.narr));
    keepOpen(tabs, tabsHtml(s));
    renderPane(pane, paneSections(s));
  });
  pane.querySelectorAll('.hzitem').forEach(function(b){
    var on = !!(s.hazard && s.hazard.id === b.dataset.r && s.hazard.idx === +b.dataset.hz);
    b.classList.toggle('on', on);
    if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
  });

  clearInterval(ticker);
  if (c.narr.status === 'streaming'){
    var tick = function(){
      var el = host.querySelector('.elapsed');
      if (el) el.textContent = Math.round((Date.now() - c.narr.startedAt) / 1000) + '초';
    };
    tick(); ticker = setInterval(tick, 1000);
  }
}

export function leaveCompare(){ built = null; clearInterval(ticker); }
