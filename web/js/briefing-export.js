/* 브리핑을 HTML 파일 하나로 내려받기 — 인터넷·로컬 서버 없이도 열린다.
   지도: Static Map 이미지(서버 프록시, data URL 로 넣음) 위에 경로·후보 지점을 SVG 로 겹쳐 그린다.
   로드뷰: 뷰어는 파일 안에서 돌지 않으므로(도메인 인증) 서버가 헤드리스 크롬으로 그 시점 화면을
   찍은 JPEG(/api/roadview-shot)를 넣는다. 개인 확인용이며 네이버 로드뷰 이미지이므로 재배포하지 않는다. */
import {esc, mins, won, hzInfo} from './format.js';
import {LETTERS, distLabel, segHtml} from './briefing-text.js';

/* ---- 웹 메르카토르: Static Map(center, level, w×h) 위 픽셀 좌표 ----
   NCP Static Map 의 level 은 256px 타일 기준 줌보다 한 단계 크다(실측: z 로 계산하면 경로가 절반 크기로
   겹쳐졌다. ncp_maps/api.py pick_level 의 -1 보정도 같은 이유). 그래서 계산은 level + 1 로 한다. */
var LEVEL_OFFSET = 1;
function mx(lon, z){ return (lon + 180) / 360 * 256 * Math.pow(2, z); }
function my(lat, z){
  var s = Math.sin(Math.max(-85, Math.min(85, lat)) * Math.PI / 180);
  return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * 256 * Math.pow(2, z);
}
function fitView(pts, w, h, maxZ){
  var lo = [180, 90], hi = [-180, -90];
  pts.forEach(function(p){ lo = [Math.min(lo[0], p[0]), Math.min(lo[1], p[1])]; hi = [Math.max(hi[0], p[0]), Math.max(hi[1], p[1])]; });
  var c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2], z = maxZ;
  while (z > 3){
    var zz = z + LEVEL_OFFSET;
    var dx = mx(hi[0], zz) - mx(lo[0], zz), dy = my(lo[1], zz) - my(hi[1], zz);
    if (dx < w * 0.82 && dy < h * 0.82) break;
    z--;
  }
  return {center: c, level: z, w: w, h: h};
}
function project(v, p){
  var z = v.level + LEVEL_OFFSET;
  return [mx(p[0], z) - mx(v.center[0], z) + v.w / 2, my(p[1], z) - my(v.center[1], z) + v.h / 2];
}

function imageData(v){
  var url = '/api/staticmap?center=' + v.center[0].toFixed(6) + ',' + v.center[1].toFixed(6)
    + '&level=' + v.level + '&w=' + v.w + '&h=' + v.h;
  return fetch(url).then(function(r){
    if (!r.ok) throw new Error('지도 이미지 ' + r.status);
    return r.blob();
  }).then(function(b){
    return new Promise(function(ok){ var fr = new FileReader(); fr.onload = function(){ ok(fr.result); }; fr.readAsDataURL(b); });
  }).catch(function(e){ console.warn('[briefing export]', e); return null; });
}

function shotData(coord, bearing){
  var url = '/api/roadview-shot?lon=' + coord[0] + '&lat=' + coord[1] + '&pan=' + Math.round(bearing || 0) + '&w=640&h=360';
  return fetch(url).then(function(r){
    if (!r.ok) return null;
    return r.blob().then(function(b){
      return new Promise(function(ok){ var fr = new FileReader(); fr.onload = function(){ ok(fr.result); }; fr.readAsDataURL(b); });
    });
  }).catch(function(){ return null; });
}

// 동시에 n 개씩 (서버도 크롬을 3개까지만 띄운다)
function pool(jobs, n, onEach){
  var out = new Array(jobs.length), next = 0, done = 0;
  return new Promise(function(resolve){
    if (!jobs.length) return resolve(out);
    function run(){
      if (next >= jobs.length) return;
      var k = next++;
      jobs[k]().then(function(v){
        out[k] = v; done++; onEach(done, jobs.length);
        if (done === jobs.length) resolve(out); else run();
      });
    }
    for (var i = 0; i < Math.min(n, jobs.length); i++) run();
  });
}

function thin(path, v){
  // 화면상 2px 미만 간격 점은 버려 파일 크기를 줄인다
  var out = [], last = null;
  path.forEach(function(p){
    var q = project(v, p);
    if (!last || Math.hypot(q[0] - last[0], q[1] - last[1]) >= 2){ out.push(q); last = q; }
  });
  return out;
}

function mapFigure(img, v, B, marks, caption){
  var line = thin(B.path, v).map(function(q){ return q[0].toFixed(1) + ',' + q[1].toFixed(1); }).join(' ');
  var svg = '<svg viewBox="0 0 ' + v.w + ' ' + v.h + '" preserveAspectRatio="xMidYMid slice">'
    + '<polyline points="' + line + '" fill="none" stroke="#fff" stroke-width="9" stroke-linejoin="round" stroke-linecap="round"/>'
    + '<polyline points="' + line + '" fill="none" stroke="#2e6ff2" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/>'
    + marks.map(function(m){
        var q = project(v, m.p);
        if (q[0] < -20 || q[1] < -20 || q[0] > v.w + 20 || q[1] > v.h + 20) return '';
        return '<g transform="translate(' + q[0].toFixed(1) + ',' + q[1].toFixed(1) + ')">'
          + '<circle r="' + (m.r || 11) + '" fill="' + m.fill + '" stroke="#fff" stroke-width="2.5"/>'
          + '<text text-anchor="middle" dy="4.2" font-size="' + (m.fs || 12) + '" font-weight="800" fill="' + (m.ink || '#fff') + '">' + esc(m.t) + '</text>'
          + (m.label ? '<text x="' + ((m.r || 11) + 4) + '" dy="4" font-size="11" font-weight="700" fill="#191c1f" stroke="#fff" stroke-width="3" paint-order="stroke">' + esc(m.label) + '</text>' : '')
          + '</g>';
      }).join('')
    + '</svg>';
  return '<figure class="map" style="aspect-ratio:' + v.w + '/' + v.h + '">'
    + (img ? '<img alt="" src="' + img + '">' : '<div class="noimg">지도 이미지를 받지 못했어요</div>')
    + svg + (caption ? '<figcaption>' + caption + '</figcaption>' : '') + '</figure>';
}

var CSS = [
  ':root{--blue:#2e6ff2;--ink:#191c1f;--muted:#5f6873;--line:#e4e7eb;--bg:#f5f6f8}',
  '*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 "Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;word-break:keep-all}',
  'main{max-width:760px;margin:0 auto;background:#fff;padding:28px 28px 40px}',
  'h1{font-size:22px;margin:0}h2{font-size:17px;margin:28px 0 10px}.trip{color:var(--muted)}',
  '.facts{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.facts span{background:var(--bg);border-radius:10px;padding:6px 10px;font-size:13px}',
  '.muted{color:var(--muted)}.ai{border:1px solid #b9cffb;background:#f5f8ff;border-radius:12px;padding:10px 14px;margin:10px 0}',
  '.legs{list-style:none;padding:0;margin:0}.legs li{display:flex;gap:10px;font-size:14px;padding:3px 0}.legs .k{width:60px;color:var(--muted)}',
  'figure.map{position:relative;margin:12px 0;border-radius:12px;overflow:hidden;background:#e9ecef;width:100%}',
  'figure.map img,figure.map svg{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}',
  'figure.map figcaption{position:absolute;left:8px;bottom:8px;background:rgba(255,255,255,.92);border-radius:8px;padding:2px 8px;font-size:12px}',
  '.noimg{position:absolute;inset:0;display:grid;place-items:center;color:var(--muted)}',
  'ol.flow{list-style:none;padding:0;margin:0;display:grid;gap:10px}',
  '.seg-card{background:var(--bg);border-radius:12px;padding:12px 14px;font-size:14px}.seg-head{display:flex;gap:8px;font-weight:700}.seg-len{margin-left:auto;color:var(--muted);font-weight:500}',
  '.seg-lead{margin:6px 0 0}.seg-notes{margin:6px 0 0;color:#1b5fd9}.seg-steps-list,.seg-steps ol{margin:6px 0 0;padding-left:0;list-style:none}.seg-steps-list li,.seg-steps li{display:flex;gap:8px;padding:2px 0}.gl{width:20px;text-align:center}',
  '.item{border:1.5px solid var(--blue);border-radius:14px;padding:14px;break-inside:avoid}.item.hz{border-color:#d93a2b}',
  '.ih{display:flex;gap:10px;align-items:flex-start}.no{flex:none;width:30px;height:30px;border-radius:50%;background:var(--blue);color:#fff;display:grid;place-items:center;font-weight:800}.item.hz .no{background:#d93a2b}',
  '.ih .meta{font-size:12px;color:var(--muted)}.ih .ins{font-weight:700}.badge{margin-left:auto;font-size:12px;font-weight:800;background:#edf3ff;color:#1b5fd9;border-radius:99px;padding:2px 8px;white-space:nowrap}',
  '.clues{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}.clue{background:var(--bg);border-radius:8px;padding:4px 10px;font-size:13px}.clue.sign{background:#0b6b3a;color:#fff;font-weight:700}',
  'table{width:100%;border-collapse:collapse;font-size:14px;margin-top:6px}td{padding:7px 6px;border-top:1px solid var(--line);vertical-align:top}td.l{width:34px}td.l b{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#fff;border:3px solid var(--blue);font-size:11px}',
  'td.d{white-space:nowrap;color:var(--muted);width:92px}.ai-n{font-size:13px;color:#4e5661;margin-top:8px}',
  '.cand{margin-top:14px}.ch{display:flex;gap:10px;align-items:center}.ch small{display:block;color:var(--muted)}',
  '.lt{flex:none;display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;border:3px solid var(--blue);color:var(--blue);font-size:13px}',
  'img.rv{display:block;width:100%;border-radius:10px;margin-top:8px;aspect-ratio:16/9;object-fit:cover;background:#e9ecef}',
  '.rv.none{display:grid;place-items:center;aspect-ratio:16/9;background:#e9ecef;border-radius:10px;margin-top:8px;color:var(--muted)}.cand p{margin:8px 0 0}',
  '@media (max-width:600px){main{padding:16px 14px 30px}h1{font-size:20px}}',
  'label.ok{display:inline-flex;gap:6px;align-items:center;margin-top:10px;font-weight:700;font-size:14px}',
  'footer{color:var(--muted);font-size:12px;margin-top:28px;line-height:1.7}',
  '@media print{body{background:#fff}main{padding:0}.item,.seg-card{break-inside:avoid}}'
].join('\n');

export function exportBriefing(B, done, btn){
  var orig = btn.textContent;
  btn.disabled = true; btn.textContent = '만드는 중…';

  var ov = fitView(B.path, 900, 560, 15);
  var itemViews = B.items.map(function(it){
    var pts = [it.coord].concat(it.type === 'maneuver' ? it.candidates.map(function(c){ return c.coord; }) : [it.view]);
    return fitView(pts, 640, 300, 17);
  });
  // 지도 이미지는 순서대로 받는다 (서버 캐시·호출 수 확인이 쉽도록)
  var imgs = [];
  var chain = [ov].concat(itemViews).reduce(function(p, v){
    return p.then(function(){ return imageData(v).then(function(d){ imgs.push(d); }); });
  }, Promise.resolve());

  // 로드뷰: 후보 지점(A·B·C…)마다, 사고 이력 지점은 60m 앞에서
  var spots = [];
  B.items.forEach(function(it, i){
    if (it.type === 'maneuver') it.candidates.forEach(function(c, k){ spots.push({i: i, k: k, coord: c.coord, bearing: c.bearing}); });
    else spots.push({i: i, k: 0, coord: it.view, bearing: it.bearing});
  });
  var shots = {};
  chain = chain.then(function(){
    return pool(spots.map(function(sp){ return function(){ return shotData(sp.coord, sp.bearing); }; }), 3, function(d, n){
      btn.textContent = '로드뷰 찍는 중 ' + d + '/' + n;
    }).then(function(res){ spots.forEach(function(sp, j){ shots[sp.i + ':' + sp.k] = res[j]; }); });
  });

  return chain.then(function(){
    var t = B.trip, r = B.route, s = B.summary;
    var ovMarks = [{p: B.path[0], t: '출', fill: '#2e6ff2', r: 12, fs: 10},
                   {p: B.path[B.path.length - 1], t: '도', fill: '#e8452c', r: 12, fs: 10}]
      .concat(B.items.map(function(it, i){ return {p: it.coord, t: String(i + 1), fill: it.type === 'hazard' ? '#d93a2b' : '#2e6ff2'}; }));

    var html = '<header><h1>출발 전 브리핑</h1><div class="trip">' + esc(t.origin) + (t.via ? ' → ' + esc(t.via) : '') + ' → ' + esc(t.goal)
      + ' · ' + esc(r.label) + '</div></header>'
      + '<div class="facts"><span><b>' + esc(mins(r.duration_min)) + '</b> 예상</span><span><b>' + r.distance_km + 'km</b></span>'
      + '<span>' + (r.toll_fare ? '통행료 ' + won(r.toll_fare) : '통행료 없음') + '</span><span>체크 지점 ' + B.items.length + '곳</span>'
      + (s.cameras ? '<span>단속카메라 ' + s.cameras + '</span>' : '') + (s.zones ? '<span>보호구역 ' + s.zones + '</span>' : '') + '</div>'
      + (B.ai.verdict || B.ai.headline ? '<div class="ai"><b>AI 요약</b> ' + esc(B.ai.verdict || B.ai.headline) + '</div>' : '')
      + mapFigure(imgs[0], ov, B, ovMarks, '숫자 = 체크 지점')
      + '<h2>길 이해하기 — 어떤 도로를 타나</h2>'
      + (B.ai.overview.length ? '<p>' + esc(B.ai.overview.join(' ')) + '</p>' : '')
      + '<ol class="legs">' + B.legs.map(function(l){ return '<li><span class="k">' + l.from_km + 'km</span><b>' + esc(l.name) + '</b><span class="muted">' + l.km + 'km</span></li>'; }).join('') + '</ol>'
      + '<h2>가는 순서대로</h2><ol class="flow">';

    B.items.forEach(function(it, i){
      html += '<li>' + segHtml(B.segments[i], B, i, false) + '</li>';
      var ins = it.type === 'hazard' ? (it.text || '').replace(/^[^—]*—\s*/, '') : it.instruction;
      html += '<li class="item' + (it.type === 'hazard' ? ' hz' : '') + '"><div class="ih"><span class="no">' + (i + 1) + '</span>'
        + '<div><div class="meta">출발 후 ' + it.km + 'km · 약 ' + it.min + '분</div><div class="ins">' + esc(ins) + '</div></div>'
        + '<span class="badge">' + esc(it.type === 'hazard' ? hzInfo(it.kind).label : it.label) + '</span></div>';
      var marks = [{p: it.coord, t: String(i + 1), fill: it.type === 'hazard' ? '#d93a2b' : '#2e6ff2', r: 13}];
      if (it.type === 'maneuver'){
        var clues = (it.target ? '<span class="clue sign">' + esc(it.target) + ' · 표지판에서 찾을 방면</span>' : '')
          + (it.side ? '<span class="clue">' + (it.side === 'left' ? '↰ 왼쪽' : '↱ 오른쪽') + ' 차로로 준비</span>' : '')
          + (it.place ? '<span class="clue">📍 ' + esc(it.place) + '</span>' : '');
        if (clues) html += '<div class="clues">' + clues + '</div>';
        it.candidates.forEach(function(c, k){
          marks.push({p: c.coord, t: LETTERS[k], fill: '#fff', ink: '#2e6ff2', r: 10, fs: 11, label: distLabel(c.dist_m) + ' 앞'});
        });
        html += mapFigure(imgs[i + 1], itemViews[i], B, marks, '숫자 = 체크 지점 · 문자 = 미리 볼 곳')
          + it.candidates.map(function(c, k){
              var img = shots[i + ':' + k];
              return '<div class="cand"><div class="ch"><b class="lt">' + LETTERS[k] + '</b><span><b>' + esc(c.title) + '</b>'
                + '<small>' + esc(distLabel(c.dist_m)) + ' 앞' + (c.seconds ? ' · 약 ' + c.seconds + '초 전' : '') + '</small></span></div>'
                + (img ? '<img class="rv" alt="' + LETTERS[k] + ' 지점 로드뷰" src="' + img + '">' : '<div class="rv none">이 지점은 로드뷰가 없어요</div>')
                + '<p>' + esc(c.say) + '</p></div>';
            }).join('');
        if (it.ai_notes.length || it.ai_pick)
          html += '<div class="ai-n"><b>AI</b> ' + esc(it.ai_notes.concat(it.ai_pick ? [it.ai_pick] : []).join(' ')) + '</div>';
      } else {
        marks.push({p: it.view, t: 'A', fill: '#fff', ink: '#2e6ff2', r: 10, fs: 11, label: '60m 앞'});
        html += '<div class="clues"><span class="clue">' + esc(it.detail || '') + '</span><span class="clue">경로에서 ' + it.distance_m + 'm</span></div>'
          + mapFigure(imgs[i + 1], itemViews[i], B, marks, '')
          + (shots[i + ':0'] ? '<div class="cand"><div class="ch"><b class="lt">A</b><span><b>60m 앞에서 본 모습</b></span></div><img class="rv" alt="로드뷰" src="' + shots[i + ':0'] + '"></div>' : '')
          + '<p>' + esc(it.text) + '. 이 근처에서는 속도를 줄이고 보행자·옆 차로를 한 번 더 살펴.</p>';
      }
      html += '<label class="ok"><input type="checkbox"' + (done[i] ? ' checked' : '') + '> 확인했어요</label></li>';
    });
    html += '<li>' + segHtml(B.segments[B.items.length], B, B.items.length, false) + '</li></ol>';
    html += '<footer>만든 시각 ' + esc(new Date().toLocaleString('ko-KR')) + '. 표지판 위치는 예고 표지의 일반 배치(2km·1km·500m)와 교차로 앞 거리로 고른 후보예요. '
      + '로드뷰 사진은 저장한 시점의 화면이에요(촬영 시기는 지점마다 다를 수 있어요). 개인 확인용으로만 쓰세요. 위험 지점은 공공데이터 기준이며 실시간 교통·공사는 반영되지 않아요.</footer>';

    var doc = '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
      + '<title>출발 전 브리핑 · ' + esc(t.origin) + ' → ' + esc(t.goal) + '</title><style>' + CSS + '</style></head><body><main>' + html + '</main></body></html>';
    var d = new Date(), ymd = d.getFullYear() + String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
    var name = ('브리핑_' + t.origin + '_' + t.goal + '_' + ymd + '.html').replace(/[\\/:*?"<>|\s]+/g, '_');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([doc], {type: 'text/html;charset=utf-8'}));
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function(){ URL.revokeObjectURL(a.href); }, 5000);
    return {name: name, bytes: doc.length, images: imgs.filter(Boolean).length,
            roadviews: Object.keys(shots).filter(function(k){ return shots[k]; }).length};
  }).finally(function(){ btn.disabled = false; btn.textContent = orig; });
}
