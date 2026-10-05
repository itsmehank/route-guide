/* 지도 — NCP Web Dynamic Map. 지도 인스턴스는 한 번만 만들고, 이후엔 오버레이만 갈아끼운다.
   state 를 받아 필요한 부분만 다시 그린다(sync). */
import {offsetPx, offsetPath, sliceBySrc, roundCorners, mpp, uniqueLabelPoints} from './geo.js';
import {CONG, END, mins, hzInfo, hzIcon, esc} from './format.js';
import {approachVantage} from './roadview.js';
import {vias} from './store.js';

var DIM = '#b6bec8', DIM_DARK = '#8b95a1';
// 밑선은 section 이 덮지 않는 구간이다 = 실시간 정보 없음
var BASE = '#8b95a1', BASE_DARK = '#5f676f';
var ROUND = 9;   // 코너 둥글리기 반경(px)

var map, traffic, cb = {}, insets = function(){ return {left:0, bottom:0, right:0, top:0}; };
var layers = [], arrows = [], labels = [], ends = [], hoverLines = [], hzMarks = [];
var focusDot = null, vantageDot = null;
var sig = {};

function ll(p){ return new naver.maps.LatLng(p[1], p[0]); }

export function init(el, callbacks, insetFn){
  cb = callbacks; insets = insetFn;
  map = new naver.maps.Map(el, {
    center: new naver.maps.LatLng(37.41, 127.07), zoom: 11,
    scaleControl: true,
    mapTypeControl: true,
    mapTypeControlOptions: {position: naver.maps.Position.TOP_RIGHT},
    zoomControl: true,                                   // 드래그 대신 쓸 수 있는 확대·축소 (WCAG 2.5.7)
    zoomControlOptions: {position: naver.maps.Position.RIGHT_CENTER, style: naver.maps.ZoomControlStyle.SMALL},
    logoControlOptions: {position: naver.maps.Position.BOTTOM_RIGHT}
  });
  // Directions 의 section 은 주요 도로만 덮는다(경로의 절반 안팎). 나머지는 지도 자체의 교통 레이어로 볼 수 있다.
  traffic = new naver.maps.TrafficLayer();

  var redraw = null;
  // 오프셋·화살표는 픽셀 기준이라 확대 레벨이 바뀌면 다시 계산해야 한다
  naver.maps.Event.addListener(map, 'zoom_changed', function(){
    clearTimeout(redraw);
    redraw = setTimeout(function(){ sig.routes = null; cb.redraw(); }, 140);
  });
  return map;
}

function polyline(pts, color, weight, z, opacity, clickable){
  var pl = new naver.maps.Polyline({
    map: map, path: pts.map(ll), strokeColor: color, strokeWeight: weight,
    strokeOpacity: opacity === undefined ? 1 : opacity, clickable: !!clickable,
    strokeLineCap: 'round', strokeLineJoin: 'round', zIndex: z
  });
  layers.push(pl);
  return pl;
}

// 테두리 있는 굵은 선: 어두운 casing 위에 색을 얹는다. 흰 바깥선으로 배경 도로와 분리한다.
function casedLine(pts, fill, dark, weight, z, white){
  if (white) polyline(pts, '#ffffff', weight + 7, z - 1, 0.95);
  polyline(pts, dark, weight + 3, z, 0.95);
  return polyline(pts, fill, weight, z + 1, 1);
}

// 진행 화살표: 일정 픽셀 간격으로 방향에 맞춰 배치
function addArrows(pts, spacingPx, maxCount){
  var zoom = map.getZoom(), acc = 0, placed = 0;
  for (var i = 1; i < pts.length && placed < maxCount; i++){
    var lat = (pts[i][1] + pts[i-1][1]) / 2;
    var mLon = 111320 * Math.cos(lat*Math.PI/180);
    var dx = (pts[i][0]-pts[i-1][0]) * mLon, dy = (pts[i][1]-pts[i-1][1]) * 110540;
    acc += Math.hypot(dx, dy) / mpp(lat, zoom);
    if (acc < spacingPx) continue;
    acc = 0; placed++;
    var deg = Math.atan2(dx, dy) * 180 / Math.PI;   // 북 기준 시계방향
    arrows.push(new naver.maps.Marker({
      position: ll(pts[i]), map: map, zIndex: 90, clickable: false,
      icon:{content:'<div class="arw" style="transform:translate(-50%,-50%) rotate('+deg.toFixed(0)+'deg)">▲</div>',
            anchor:new naver.maps.Point(0,0)}
    }));
  }
}

function htmlMarker(coord, html, z, onClick, title){
  var m = new naver.maps.Marker({
    position: ll(coord), map: map, zIndex: z, title: title || '',
    clickable: !!onClick,
    icon:{content: html, anchor: new naver.maps.Point(0,0)}
  });
  if (onClick) naver.maps.Event.addListener(m, 'click', onClick);
  return m;
}

function clearAll(list){ list.forEach(function(l){ l.setMap(null); }); list.length = 0; }

/* ---------------- 경로 ---------------- */
function drawRoutes(s){
  clearAll(layers); clearAll(arrows); clearAll(labels);
  if (!s.routes.length) return;
  var zoom = map.getZoom(), OFF = offsetPx(zoom);

  // 선택되지 않은 경로: 회색, 화살표 없음. 선을 눌러도 고를 수 있게 clickable.
  s.routes.forEach(function(r, i){
    if (i === s.sel) return;
    var pts = roundCorners(offsetPath(r.path, zoom).pts, ROUND, zoom);
    var top = casedLine(pts, DIM, DIM_DARK, 5, 10 + i*3);
    top.setOptions({clickable: true});
    naver.maps.Event.addListener(top, 'click', function(){ cb.selectRoute(i); });
    naver.maps.Event.addListener(top, 'mouseover', function(){ cb.hoverRoute(i); });
    naver.maps.Event.addListener(top, 'mouseout', function(){ cb.hoverRoute(null); });
  });

  // 선택된 경로: 흰 바깥선 + 밑선 + section 별 혼잡도 색 + 진행 화살표
  var sel = s.routes[s.sel];
  var o = offsetPath(sel.path, zoom);
  var base = roundCorners(o.pts, ROUND, zoom);
  casedLine(base, BASE, BASE_DARK, 7, 50, true);
  // section 은 반드시 '원본 인덱스'로 잘라야 한다. 오프셋 결과는 원호 때문에 점 개수가 다르다.
  sel.sections.forEach(function(sec){
    var seg = roundCorners(sliceBySrc(o, sec.pointIndex, sec.pointIndex + sec.pointCount - 1), ROUND, zoom);
    if (seg.length > 1){
      var c = CONG[sec.congestion] || CONG[0];
      casedLine(seg, c.color, c.dark, 7, 60);
    }
  });
  addArrows(base, 62, 55);

  // 라벨: 다른 경로와 겹치지 않는 구간 가운데. 그런 구간이 없으면 선택 경로만 중간에 둔다.
  var spots = uniqueLabelPoints(s.routes);
  s.routes.forEach(function(r, i){
    var p = spots[i];
    if (!p){
      if (i !== s.sel) return;
      p = r.path[Math.floor(r.path.length / 2)];
    }
    labels.push(htmlMarker(p,
      '<div class="rlabel'+(i===s.sel?'':' off')+'"><i>'+(i+1)+'</i>'+esc(mins(r.duration_min))+'</div>',
      100 + (i===s.sel?50:0), function(){ cb.selectRoute(i); }, r.label));
  });
}

function drawHover(s){
  clearAll(hoverLines);
  var i = s.hover;
  if (i === null || i === s.sel || !s.routes[i]) return;
  var zoom = map.getZoom();
  var pts = roundCorners(offsetPath(s.routes[i].path, zoom).pts, ROUND, zoom);
  hoverLines.push(new naver.maps.Polyline({
    map: map, path: pts.map(ll), strokeColor: '#2e6ff2', strokeWeight: 6, strokeOpacity: .85,
    strokeLineCap: 'round', strokeLineJoin: 'round', zIndex: 45
  }));
}

function drawEnds(s){
  clearAll(ends);
  var pts = [['origin', s.origin, '']].concat(vias(s).map(function(p, i){ return ['waypoint', p, String(i + 1)]; }))
    .concat([['goal', s.goal, '']]);
  pts.forEach(function(t){
    var k = t[0], p = t[1]; if (!p) return;
    ends.push(new naver.maps.Marker({
      position: ll(p.coord), map: map, zIndex: 200,
      // 이름은 툴팁으로만. 지도 위 라벨은 경로를 가린다.
      title: END[k].label + t[2] + ' · ' + p.title,
      icon:{content:'<div class="pin-se" style="--c:'+END[k].color+'">' + (t[2] ? '<b>' + t[2] + '</b>' : '') + '</div>',
            anchor:new naver.maps.Point(0,0)}
    }));
  });
}

/* ---------------- 상세: 분기점 포커스 ---------------- */
function drawFocus(s){
  if (focusDot){ focusDot.setMap(null); focusDot = null; }
  if (vantageDot){ vantageDot.setMap(null); vantageDot = null; }
  var r = s.routes[s.sel];
  if (s.view !== 'detail' || s.step === null || !r) return;
  var g = r.guides[s.step];
  var at = r.path[Math.min(g.pointIndex, r.path.length-1)];
  // 경로선을 덮어 칠하지 않는다 — 분기점 위에 흰 원만 얹는다
  focusDot = htmlMarker(at, '<div class="focusdot"></div>', 350, null, '분기점');
  var v = approachVantage(r, s.step, s.nudge || 0);
  vantageDot = htmlMarker(v.coord, '<div class="vantagedot"></div>', 340, null, '로드뷰 관측 지점');
}

/* ---------------- 위험 지점 ---------------- */
function drawHazards(s){
  clearAll(hzMarks);
  var ev = s.cmp.data && s.cmp.data.evaluation;
  var r = s.routes[s.sel];
  if (!ev || !r || s.cmp.key !== s.routeKey) return;
  var er = ev.routes.find(function(x){ return x.id === r.option; });
  if (!er) return;
  // 멀리서 보면 보호구역·카메라가 경로를 뒤덮는다. 사고 이력만 늘 보이고, 나머지는 확대(14+)했을 때만.
  var close = map.getZoom() >= 14;
  (er.hazards || []).forEach(function(h, idx){
    var info = hzInfo(h.type);
    var on = s.hazard && s.hazard.id === r.option && s.hazard.idx === idx;
    var minor = info.tone === 'cam' || info.tone === 'zone';
    if (minor && !close && !on) return;
    hzMarks.push(htmlMarker(h.coord,
      '<div class="hzpin' + (on ? ' on' : '') + '">' + hzIcon(h.type, h.text) + '</div>',
      on ? 380 : (minor ? 290 : 300), function(){ cb.hazardClick(r.option, idx); },
      info.label + ' · ' + (h.text || '').replace(/^[^—]*—\s*/, '')));
  });
}

/* ---------------- 시점 ---------------- */
function pad(extra){
  var i = insets(), e = extra || 48;
  return {top: i.top + e, right: i.right + e, bottom: i.bottom + e, left: i.left + e};
}

export function fitRoute(r){
  if (!r) return;
  var b = new naver.maps.LatLngBounds(ll(r.path[0]), ll(r.path[0]));
  r.path.forEach(function(p){ b.extend(ll(p)); });
  map.fitBounds(b, pad(48));
}

// 한 점 주변을 일정 배율로 보여준다(halfM = 화면에 담을 반경)
export function focusPoint(coord, halfM){
  var dLat = halfM / 110540, dLon = halfM / (111320 * Math.cos(coord[1]*Math.PI/180));
  var b = new naver.maps.LatLngBounds(
    new naver.maps.LatLng(coord[1]-dLat, coord[0]-dLon),
    new naver.maps.LatLng(coord[1]+dLat, coord[0]+dLon));
  map.fitBounds(b, pad(24));
}

export function setTraffic(on){ traffic.setMap(on ? map : null); }

export function sync(s){
  var routesSig = [s.routeKey, s.routes.length, s.sel, map.getZoom()].join('|');
  if (sig.routes !== routesSig){ sig.routes = routesSig; drawRoutes(s); drawEnds(s); sig.hover = null; }
  var endsSig = [s.origin, s.goal].concat(vias(s)).map(function(p){ return p ? p.coord.join(',') : ''; }).join('|');
  if (sig.ends !== endsSig){ sig.ends = endsSig; drawEnds(s); }
  var hoverSig = routesSig + '|' + s.hover;
  if (sig.hover !== hoverSig){ sig.hover = hoverSig; drawHover(s); }
  var focusSig = routesSig + '|' + s.view + '|' + s.step + '|' + (s.nudge || 0);
  if (sig.focus !== focusSig){ sig.focus = focusSig; drawFocus(s); }
  var hzSig = routesSig + '|' + s.cmp.key + '|' + s.cmp.status + '|' + JSON.stringify(s.hazard);
  if (sig.hz !== hzSig){ sig.hz = hzSig; drawHazards(s); }
  if (sig.traffic !== s.traffic){ sig.traffic = s.traffic; setTraffic(s.traffic); }
}

export function center(){ var c = map.getCenter(); return [c.lng(), c.lat()]; }

export function refresh(){ if (map) naver.maps.Event.trigger(map, 'resize'); }
