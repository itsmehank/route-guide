/* 로드뷰(거리뷰) — maps-panorama.js 서브모듈이 있어야 동작한다.

   노면 화살표(직진/좌회전 표시)는 정지선 앞쪽 노면에 그려져 있다.
   분기점 좌표에 서면 이미 그 위를 지난 뒤라 차선 정보가 안 보인다.
   그래서 로드뷰는 분기점이 아니라 '진입 직전'에서 앞을 보게 한다. */
import {walkBack, bearingAt} from './geo.js';
import {km} from './format.js';

var APPROACH_SEC = 8;      // 몇 초 전 지점을 볼 것인가
var BACK_MIN_M = 25, BACK_MAX_M = 250;
export var NUDGE_M = 20;   // 차량에 가렸을 때 앞뒤로 움직이는 단위

// 이 분기점에서 관측 지점이 움직일 수 있는 범위(m). 구간 길이에 걸린다.
function vantageRange(r, i){
  var g = r.guides[i];
  // 그 구간의 평균 속도로 '몇 초 전'을 거리로 환산한다.
  // 고속도로 8초와 시내 8초는 거리가 전혀 다르므로 고정 거리는 쓰지 않는다.
  var mps = g.duration ? (g.distance / (g.duration/1000)) : 8;
  // 이전 분기점을 넘어가면 엉뚱한 도로를 보게 된다
  var max = Math.min(BACK_MAX_M, Math.max(10, g.distance - 5));
  return {mps: mps, base: mps * APPROACH_SEC, min: Math.min(BACK_MIN_M, max), max: max};
}

// 범위 안으로 자른 미세조정 값. 한계에서 계속 눌러도 내부 값이 불어나지 않게 한다.
export function clampNudge(r, i, nudge){
  var q = vantageRange(r, i);
  return Math.max(q.min, Math.min(q.max, q.base + nudge)) - q.base;
}

export function approachVantage(r, i, extraM){
  var q = vantageRange(r, i);
  var back = Math.max(q.min, Math.min(q.max, q.base + (extraM || 0)));
  var v = walkBack(r.path, r.guides[i].pointIndex, back);
  v.seconds  = q.mps > 0.5 ? v.dist / q.mps : 0;
  v.bearing  = bearingAt(r.path, v.index);
  v.atEarly  = back >= q.max - 0.5;   // 더 멀리 못 감
  v.atLate   = back <= q.min + 0.5;   // 더 가까이 못 감
  return v;
}

export function vantageText(v){
  return '분기점 ' + km(Math.round(v.dist)) + ' 앞 · 약 ' + Math.round(v.seconds) + '초 전';
}

function ll(p){ return new naver.maps.LatLng(p[1], p[0]); }
var CTRL_OFF = {flightSpot:false, aroundControl:false, zoomControl:false, logoControl:false};

/* ---- 보이는 뷰어 ---- */
var pano = null, host = null;

export function available(){ return !!(window.naver && naver.maps && naver.maps.Panorama); }

// box 에 뷰어를 띄운다. 같은 box 면 위치만 옮긴다(재생성하면 3~7초 다시 기다린다).
export function show(box, v, onStatus){
  if (!available()) { onStatus && onStatus('unavailable'); return; }
  if (pano && host === box){
    try {
      pano.setPosition(ll(v.coord));
      pano.setPov({pan: v.bearing, tilt: 0, fov: 100});
      return;
    } catch (e) { destroy(); }
  }
  destroy();
  host = box;
  try {
    pano = new naver.maps.Panorama(box, Object.assign({
      position: ll(v.coord), pov: {pan: v.bearing, tilt: 0, fov: 100}
    }, CTRL_OFF));
    naver.maps.Event.addListener(pano, 'pano_status', function(status){
      onStatus && onStatus(status === naver.maps.PanoramaStatus.ERROR ? 'none' : 'ok');
    });
  } catch (e) {
    pano = null; host = null;
    onStatus && onStatus('none');
  }
}

export function resize(){
  if (!pano || !host) return;
  try { pano.setSize(new naver.maps.Size(host.clientWidth, host.clientHeight)); } catch (e) {}
}

export function destroy(){
  if (pano){ try { pano.destroy(); } catch (e) {} }
  pano = null; host = null;
}

/* ---- 예열 ----
   다음에 보게 될 지점(앞뒤 미세조정 ±20m, 이전·다음 단계)만 숨긴 뷰어로 미리 한 번 띄운다.
   타일이 브라우저 HTTP 캐시에 남아서, 버튼을 누르면 네트워크 없이 바로 뜬다.
   경로 전체를 미리 받지 않는 이유: 분기점이 18개면 50회가 넘는데 대부분 안 본다. */
var prePano = null, preBox = null, preTimer = null, preQueue = [];

export function preheat(list){
  clearTimeout(preTimer);
  preQueue = (list || []).filter(Boolean);
  preTimer = setTimeout(runPreheat, 500);   // 보이는 뷰어가 먼저 뜨도록 잠깐 양보
}

function runPreheat(){
  if (!preQueue.length || !available()) return;
  var next = preQueue.shift();
  if (!prePano){
    preBox = document.createElement('div');
    // 화면 밖에 두되 크기는 실제로 줘야 타일을 받는다 (0 크기면 로드 안 함)
    preBox.style.cssText = 'position:absolute;left:-10000px;top:0;width:480px;height:270px';
    document.body.appendChild(preBox);
    try {
      prePano = new naver.maps.Panorama(preBox, Object.assign({
        position: ll(next.coord), pov: {pan: next.bearing, tilt: 0, fov: 100}
      }, CTRL_OFF));
    } catch (e) { prePano = null; return; }
  } else {
    try {
      prePano.setPosition(ll(next.coord));
      prePano.setPov({pan: next.bearing, tilt: 0, fov: 100});
    } catch (e) { return; }
  }
  preTimer = setTimeout(runPreheat, 900);
}

export function stopPreheat(){ clearTimeout(preTimer); preQueue = []; }
