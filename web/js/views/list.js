/* 경로 목록 — 카드 한 장에 '고를 때 필요한 것'만: 시간, 거리, 비용, 차별점, 혼잡 비율.
   구간별 도로 이름·혼잡 상세는 상세 화면으로 옮겼다. */
import {esc, mins, minsHtml, won, CONG} from '../format.js';

// 카드마다 다른 경로와 비교한 '이 경로만의 장점' 최대 2개
function traits(routes, ev){
  var n = routes.length;
  var out = routes.map(function(){ return []; });
  if (n < 2) return out;
  function best(get, label, lowIsGood){
    var vals = routes.map(get);
    var target = lowIsGood === false ? Math.max.apply(null, vals) : Math.min.apply(null, vals);
    var winners = vals.map(function(v, i){ return v === target ? i : -1; }).filter(function(i){ return i >= 0; });
    if (winners.length === n) return;                  // 모두 같으면 장점이 아니다
    winners.forEach(function(i){ out[i].push(label); });
  }
  best(function(r){ return r.duration_min; }, '가장 빠름');
  best(function(r){ return r.distance_km; }, '가장 짧음');
  if (routes.some(function(r){ return r.toll_fare; }))
    routes.forEach(function(r, i){ if (!r.toll_fare) out[i].push('통행료 무료'); });
  best(function(r){ return (r.toll_fare || 0) + (r.fuel_price || 0); }, '비용 최저');
  if (ev){
    var byId = {}; ev.routes.forEach(function(x){ byId[x.id] = x; });
    best(function(r){ var e = byId[r.option]; return e ? e.comfort.rank : 99; }, '운전 가장 편함');
    best(function(r){ var e = byId[r.option]; return e ? e.metrics.uturn_count : 99; }, '유턴 적음');
  }
  return out.map(function(t){ return t.slice(0, 2); });
}

// 혼잡 비율 막대: section 이 덮지 않는 나머지는 '정보없음'
function congestionBar(r){
  var total = r.distance_km * 1000 || 1, by = [0, 0, 0, 0];
  r.sections.forEach(function(s){ by[s.congestion || 0] += s.distance; });
  by[0] += Math.max(0, total - by[0] - by[1] - by[2] - by[3]);
  var parts = [1, 2, 3, 0].filter(function(c){ return by[c] / total >= 0.01; });
  var label = parts.map(function(c){ return CONG[c].name + ' ' + Math.round(by[c] / total * 100) + '%'; }).join(', ');
  return '<div class="cbar" role="img" aria-label="교통 상황: ' + label + '">'
    + parts.map(function(c){
        return '<i style="flex:' + by[c].toFixed(0) + ';background:' + CONG[c].color + '"></i>';
      }).join('') + '</div>';
}

// 가장 긴 도로 2개를 경로 순서대로
function mainRoads(r){
  var top = r.sections.slice().sort(function(a, b){ return b.distance - a.distance; }).slice(0, 2);
  top.sort(function(a, b){ return a.pointIndex - b.pointIndex; });
  return top.map(function(s){ return esc(s.name); }).join(' → ');
}

export function renderList(host, s, act){
  if (s.routeStatus === 'idle'){
    host.innerHTML = '<div class="empty">출발지와 도착지를 입력하세요.</div>';
    return;
  }
  if (s.routeStatus === 'loading'){
    host.innerHTML = '<ul class="cards" aria-busy="true">'
      + [0, 1].map(function(){ return '<li class="card skel"><span></span><span></span><span></span></li>'; }).join('')
      + '</ul>';
    return;
  }
  if (s.routeStatus === 'error'){
    host.innerHTML = '<div class="empty err"><b>' + esc(s.routeError) + '</b>'
      + '<button class="btn" data-act="retry">다시 시도</button></div>';
    host.querySelector('[data-act=retry]').onclick = act.retry;
    return;
  }

  var ev = s.cmp.key === s.routeKey && s.cmp.data ? s.cmp.data.evaluation : null;
  var tr = traits(s.routes, ev);
  var merged = s.routes.some(function(r){ return (r.options || []).length > 1; });

  host.innerHTML = '<ul class="cards" role="list">' + s.routes.map(function(r, i){
    var cost = (r.toll_fare ? '통행료 ' + won(r.toll_fare) : '통행료 무료') + ' · 연료비 ' + won(r.fuel_price);
    return '<li><button class="card' + (i === s.sel ? ' on' : '') + '" data-i="' + i + '" aria-pressed="' + (i === s.sel) + '"'
      + ' aria-label="' + esc((i+1) + '번 ' + r.label + ', ' + mins(r.duration_min) + ', ' + r.distance_km + '킬로미터, 상세 보기') + '">'
      + '<span class="hd"><span class="num">' + (i+1) + '</span><span class="lb">' + esc(r.label) + '</span>'
      + tr[i].map(function(t){ return '<span class="trait">' + esc(t) + '</span>'; }).join('') + '</span>'
      + '<span class="big"><span class="t">' + minsHtml(r.duration_min) + '</span><span class="d">' + r.distance_km + 'km</span></span>'
      + '<span class="fees">' + cost + '</span>'
      + (r.sections.length ? congestionBar(r) + '<span class="roads">' + mainRoads(r) + '</span>'
                           : '<span class="roads muted">실시간 도로 정보 없음</span>')
      + '<span class="go-detail" aria-hidden="true">상세 ›</span>'
      + '</button></li>';
  }).join('') + '</ul>'
  + (merged ? '<p class="note">같은 길로 나온 옵션은 한 장으로 합쳤어요.</p>' : '')
  + (s.routes.length >= 2
      ? '<div class="sticky-cta"><button class="btn primary wide" data-act="compare">⚖ 어느 길이 나을까? 경로 비교</button></div>'
      : '');

  host.querySelectorAll('.card').forEach(function(b){
    var i = +b.dataset.i;
    b.onclick = function(){ act.openDetail(i); };
    b.onmouseenter = b.onfocus = function(){ act.hover(i); };
    b.onmouseleave = b.onblur = function(){ act.hover(null); };
  });
  var c = host.querySelector('[data-act=compare]');
  if (c) c.onclick = act.openCompare;
}
