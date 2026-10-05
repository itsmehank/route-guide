/* 상세 경로 — 위: 진입 직전 로드뷰(16:9, 크게 보기 가능), 아래: 안내 단계 목록.
   로드뷰를 지도 말풍선에서 꺼내 패널로 옮겼다. 말풍선이 분기점 주변 도로를 가리지 않는다. */
import {esc, km, mins, glyph, CONG, END} from '../format.js';
import * as rv from '../roadview.js';
import {briefingUrl} from './compare.js';

var built = null;      // 지금 그려진 경로 시그니처 — 같으면 목록을 다시 만들지 않는다(스크롤 유지)

function sectionsHtml(r){
  if (!r.sections.length) return '';
  return '<details class="secs"><summary>구간별 교통 정보 ' + r.sections.length + '곳</summary><ul>'
    + r.sections.map(function(s){
        var c = CONG[s.congestion] || CONG[0];
        return '<li><span class="tag" style="background:' + c.color + '">' + c.name + '</span>'
          + esc(s.name) + ' <span class="muted">' + (s.distance/1000).toFixed(1) + 'km'
          + (s.speed ? ' · 평균 ' + s.speed + 'km/h' : '') + '</span></li>';
      }).join('') + '</ul></details>';
}

function build(host, s, act){
  var r = s.routes[s.sel];
  host.innerHTML =
      '<div class="vhead">'
    +   '<button class="back" data-act="back" aria-label="경로 목록으로">‹</button>'
    +   '<div class="vtitle"><span class="num">' + (s.sel+1) + '</span>' + esc(r.label)
    +     ' · <b>' + esc(mins(r.duration_min)) + '</b> <span class="muted">' + r.distance_km + 'km</span></div>'
    + '</div>'
    + '<a class="btn wide brief-link" target="_blank" rel="noopener" href="' + esc(briefingUrl(s)) + '">📋 출발 전 브리핑 — 체크 지점을 순서대로 미리 보기 ↗</a>'
    + '<section class="rv" hidden aria-label="진입 직전 로드뷰">'
    +   '<div class="rv-media">'
    +     '<div class="rv-pano"></div>'
    +     '<div class="rv-cap"></div>'
    +     '<button class="rv-expand" data-act="expand" aria-label="로드뷰 크게 보기">⤢</button>'
    +   '</div>'
    +   '<div class="rv-bar">'
    +     '<button data-act="far">‹ 더 멀리</button><span class="rv-info"></span><button data-act="near">더 가까이 ›</button>'
    +   '</div>'
    +   '<div class="rv-step"><span class="gl" aria-hidden="true"></span><b></b></div>'
    +   '<div class="rv-nav">'
    +     '<button data-act="prev">‹ 이전 단계</button><span class="rv-count"></span><button data-act="next">다음 단계 ›</button>'
    +   '</div>'
    + '</section>'
    + '<p class="hint" id="rvhint">단계를 누르면 그 분기점 <b>진입 직전</b> 로드뷰를 볼 수 있어요. 노면 화살표로 차선을 미리 익혀 두세요.</p>'
    + sectionsHtml(r)
    + '<ol class="steps">'
    +   '<li><div class="step end"><span class="gl" style="color:' + END.origin.color + '">●</span>'
    +     '<span class="tx"><small>출발</small>' + esc(s.origin ? s.origin.title : '출발지') + '</span></div></li>'
    +   r.guides.map(function(g, i){
          var last = i === r.guides.length - 1;
          return '<li><button class="step" data-i="' + i + '">'
            + '<span class="gl" aria-hidden="true"' + (last ? ' style="color:' + END.goal.color + '"' : '') + '>'
            + (last ? '●' : glyph(g.type, g.instructions)) + '</span>'
            + '<span class="tx"><small>' + km(g.distance) + ' 이동 후</small>' + esc(g.instructions) + '</span>'
            + '</button></li>';
        }).join('')
    + '</ol>';

  host.querySelector('[data-act=back]').onclick = act.back;
  host.querySelectorAll('.step[data-i]').forEach(function(b){
    b.onclick = function(){ act.focusStep(+b.dataset.i); };
  });
  var q = function(a){ return host.querySelector('[data-act=' + a + ']'); };
  q('far').onclick  = function(){ act.nudge(+rv.NUDGE_M); };
  q('near').onclick = function(){ act.nudge(-rv.NUDGE_M); };
  q('prev').onclick = function(){ act.focusStep(Math.max(0, s.step - 1)); };
  q('next').onclick = function(){ act.focusStep(Math.min(r.guides.length - 1, s.step + 1)); };
  q('expand').onclick = function(){ toggleFull(host); };
}

function toggleFull(host, force){
  var media = host.querySelector('.rv-media'); if (!media) return;
  var on = force === undefined ? !media.classList.contains('full') : force;
  media.classList.toggle('full', on);
  var b = media.querySelector('.rv-expand');
  b.textContent = on ? '✕' : '⤢';
  b.setAttribute('aria-label', on ? '로드뷰 작게 보기' : '로드뷰 크게 보기');
  setTimeout(rv.resize, 30);
}

export function renderDetail(host, s, act){
  var r = s.routes[s.sel];
  if (!r) return;
  var key = s.routeKey + '|' + s.sel;
  if (built !== key || !host.querySelector('.rv')){ rv.destroy(); build(host, s, act); built = key; }

  var section = host.querySelector('.rv');
  host.querySelectorAll('.step[data-i]').forEach(function(b){
    var on = +b.dataset.i === s.step;
    b.classList.toggle('on', on);
    if (on) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
  });

  if (s.step === null){
    section.hidden = true;
    host.querySelector('#rvhint').hidden = false;
    rv.destroy(); rv.stopPreheat();
    return;
  }

  var g = r.guides[s.step];
  var v = rv.approachVantage(r, s.step, s.nudge);
  section.hidden = false;
  host.querySelector('#rvhint').hidden = true;
  section.querySelector('.rv-cap').textContent = '진입 직전 로드뷰 · ' + rv.vantageText(v);
  section.querySelector('.rv-info').textContent = km(Math.round(v.dist)) + ' 앞';
  section.querySelector('[data-act=far]').disabled = v.atEarly;
  section.querySelector('[data-act=near]').disabled = v.atLate;
  section.querySelector('.rv-step .gl').textContent = glyph(g.type, g.instructions);
  section.querySelector('.rv-step b').textContent = g.instructions;
  section.querySelector('.rv-count').textContent = (s.step + 1) + ' / ' + r.guides.length;
  section.querySelector('[data-act=prev]').disabled = s.step === 0;
  section.querySelector('[data-act=next]').disabled = s.step === r.guides.length - 1;

  var media = section.querySelector('.rv-media'), box = section.querySelector('.rv-pano');
  media.classList.remove('none');
  media.classList.add('loading');
  rv.show(box, v, function(st){
    media.classList.remove('loading');
    if (st !== 'ok') media.classList.add('none');
  });

  // 다음에 볼 가능성이 큰 곳: 앞뒤 미세조정, 이전·다음 단계
  rv.preheat([
    rv.approachVantage(r, s.step, s.nudge + rv.NUDGE_M),
    rv.approachVantage(r, s.step, s.nudge - rv.NUDGE_M),
    s.step + 1 < r.guides.length ? rv.approachVantage(r, s.step + 1, 0) : null,
    s.step > 0 ? rv.approachVantage(r, s.step - 1, 0) : null
  ]);

  var on = host.querySelector('.step.on');
  if (on) on.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}

export function leaveDetail(host){
  built = null;
  rv.destroy(); rv.stopPreheat();
  toggleFull(host, false);
}

document.addEventListener('keydown', function(e){
  if (e.key !== 'Escape') return;
  var full = document.querySelector('.rv-media.full');
  if (full){ full.classList.remove('full'); var b = full.querySelector('.rv-expand'); b.textContent = '⤢'; setTimeout(rv.resize, 30); }
});
