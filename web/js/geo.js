/* 경로 지오메트리 — 지도 SDK 에 의존하지 않는 순수 함수만 둔다.
   좌표는 모두 [경도, 위도] (NCP API 와 같은 순서). */

export const MLAT = 110540;
export function mlon(lat){ return 111320 * Math.cos(lat*Math.PI/180); }

// 지도 축척: level z 에서 위도 lat 의 1px 이 몇 m 인가
export function mpp(lat, zoom){ return 156543.03392 * Math.cos(lat*Math.PI/180) / Math.pow(2, zoom); }

export function distM(a, b){
  var lat = (a[1]+b[1])/2;
  return Math.hypot((b[0]-a[0])*mlon(lat), (b[1]-a[1])*MLAT);
}

/* ---- 우측통행 오프셋 ----
   구간(segment)마다 따로 평행이동한 뒤 꼭짓점을 이어붙인다. 이어붙이는 방법이 좌우로 다르다:
     · 우회전 = 오프셋이 커브 안쪽 → 두 평행선이 교차한다 → 교점(miter)으로 이어야 한다.
       예전처럼 원호를 넣으면 선이 코너를 지나쳤다 되돌아와 삐죽하게 튀어나온다.
     · 좌회전/유턴 = 오프셋이 커브 바깥쪽 → 벌어진다 → 원호(round)로 메운다.
   마지막에 코너를 한 번 더 둥글려(roundCorners) 네이버처럼 부드러운 곡선으로 만든다.

   반환값은 {pts, src} 다. src[i] 는 그 점이 원본 path 의 몇 번째에서 왔는지로,
   section(pointIndex/pointCount)을 잘라낼 때 쓴다 — 원호 때문에 점 개수가 달라지므로
   오프셋 결과를 원본 인덱스로 자르면 색이 엉뚱한 곳에 칠해진다. */
export function offsetPx(zoom){
  return Math.max(3.5, Math.min(13, 3.5 + (zoom - 12) * 1.9));
}

// 오프셋을 '픽셀'로만 잡으면 저배율에서 실거리가 폭발한다(zoom 12 → 106m).
// 도로 폭의 10배짜리 평행이동은 코너에서 자기 교차를 일으켜 선이 삐죽거린다.
// 실제 도로 반폭을 넘지 않도록 미터 단위로 상한을 둔다.
export var OFFSET_MAX_M = 14;
function offsetMeters(lat, zoom){
  return Math.min(offsetPx(zoom) * mpp(lat, zoom), OFFSET_MAX_M);
}

// 저배율에서는 화면상 1px 도 안 되는 잔굴곡이 잡음이 된다. 먼저 걸러낸다.
// (Douglas-Peucker, 허용오차는 화면 1px 남짓)
function simplify(path, tolM, lat){
  if (path.length < 3) return {pts: path, idx: path.map(function(_, i){ return i; })};
  var ML = mlon(lat), keep = new Array(path.length).fill(false);
  keep[0] = keep[path.length-1] = true;
  var stack = [[0, path.length-1]];
  function perp(p, a, b){
    var px=(p[0]-a[0])*ML, py=(p[1]-a[1])*MLAT;
    var bx=(b[0]-a[0])*ML, by=(b[1]-a[1])*MLAT;
    var L2 = bx*bx+by*by;
    if (!L2) return Math.hypot(px, py);
    var t = Math.max(0, Math.min(1, (px*bx+py*by)/L2));
    return Math.hypot(px-bx*t, py-by*t);
  }
  while (stack.length){
    var seg = stack.pop(), i0 = seg[0], i1 = seg[1], best = -1, bi = -1;
    for (var i = i0+1; i < i1; i++){
      var d = perp(path[i], path[i0], path[i1]);
      if (d > best){ best = d; bi = i; }
    }
    if (best > tolM && bi > 0){
      keep[bi] = true;
      stack.push([i0, bi], [bi, i1]);
    }
  }
  var out = [], idx = [];
  for (var k = 0; k < path.length; k++) if (keep[k]){ out.push(path[k]); idx.push(k); }
  return {pts: out, idx: idx};
}

export function offsetPath(path, zoom){
  if (!path || path.length < 2) return {pts: path || [], src: []};
  var lat0 = path[Math.floor(path.length/2)][1];

  // 1) 화면에서 안 보이는 잔굴곡 제거 (원본 인덱스는 그대로 따라간다)
  var sim = simplify(path, Math.max(0.5, 1.1 * mpp(lat0, zoom)), lat0);
  var base = sim.pts, baseIdx = sim.idx;

  // 2) 중복점 제거
  var pts = [base[0]], idx = [baseIdx[0]];
  for (var i = 1; i < base.length; i++){
    var a = pts[pts.length-1], b = base[i];
    if (Math.abs(a[0]-b[0]) > 1e-9 || Math.abs(a[1]-b[1]) > 1e-9){ pts.push(b); idx.push(baseIdx[i]); }
  }
  if (pts.length < 2) return {pts: pts, src: idx};

  var dir = [], nrm = [], amt = [];
  for (i = 0; i < pts.length-1; i++){
    var p = pts[i], q = pts[i+1], lat = (p[1]+q[1])/2, ml = mlon(lat);
    var dx = (q[0]-p[0])*ml, dy = (q[1]-p[1])*MLAT, len = Math.hypot(dx, dy) || 1;
    dir.push([dx/len, dy/len]);
    nrm.push([dy/len, -dx/len]);          // 진행방향의 오른쪽
    amt.push(offsetMeters(lat, zoom));    // px 가 아니라 미터 상한이 걸린 값
  }

  var out = [], src = [];
  function emit(v, mx, my, srcIdx){
    var ml2 = mlon(v[1]);
    out.push([ v[0] + mx/ml2, v[1] + my/MLAT ]);
    src.push(srcIdx);
  }

  emit(pts[0], nrm[0][0]*amt[0], nrm[0][1]*amt[0], idx[0]);

  for (i = 0; i < pts.length-2; i++){
    var v = pts[i+1], si = idx[i+1];
    var d1 = dir[i], d2 = dir[i+1], m1 = amt[i], m2 = amt[i+1];
    var p1 = [nrm[i][0]*m1,   nrm[i][1]*m1];
    var p2 = [nrm[i+1][0]*m2, nrm[i+1][1]*m2];
    var cross = d1[0]*d2[1] - d1[1]*d2[0];
    var dot   = d1[0]*d2[0] + d1[1]*d2[1];

    if (dot > 0.9995 && Math.abs(cross) < 1e-4){       // 사실상 직진
      emit(v, p1[0], p1[1], si);
      continue;
    }

    if (cross < 0 && dot > -0.9){                       // 우회전 → 교점(miter)
      var wx = p2[0]-p1[0], wy = p2[1]-p1[1];
      var t  = (wx*d2[1] - wy*d2[0]) / cross;
      var mx = p1[0] + d1[0]*t, my = p1[1] + d1[1]*t;
      if (Math.hypot(mx, my) <= Math.max(m1, m2) * 4.5){
        emit(v, mx, my, si);
      } else {                                          // 너무 뾰족하면 잘라낸다
        emit(v, p1[0], p1[1], si);
        emit(v, p2[0], p2[1], si);
      }
      continue;
    }

    // 좌회전 / 유턴 → 바깥쪽이 벌어지므로 원호로 메운다
    var a1 = Math.atan2(p1[1], p1[0]), a2 = Math.atan2(p2[1], p2[0]);
    var sweep = a2 - a1;
    while (sweep >  Math.PI) sweep -= 2*Math.PI;
    while (sweep < -Math.PI) sweep += 2*Math.PI;
    // 유턴은 cross 가 0 에 가까워 방향이 모호하다. 국내 유턴은 좌회전이므로 왼쪽으로 돈다.
    var sign = cross > 1e-9 ? 1 : (cross < -1e-9 ? -1 : 1);
    sweep = sign * Math.abs(sweep || Math.PI);
    var steps = Math.max(2, Math.min(20, Math.ceil(Math.abs(sweep) / 0.20)));
    for (var k = 0; k <= steps; k++){
      var ang = a1 + sweep*(k/steps), r = m1 + (m2-m1)*(k/steps);
      emit(v, Math.cos(ang)*r, Math.sin(ang)*r, si);
    }
  }

  var L = pts.length-2;
  emit(pts[pts.length-1], nrm[L][0]*amt[L], nrm[L][1]*amt[L], idx[pts.length-1]);
  return {pts: out, src: src};
}

/* 원본 인덱스 구간 [from, to] 에 해당하는 오프셋 점들만 뽑는다 */
export function sliceBySrc(o, from, to){
  var a = [];
  for (var i = 0; i < o.pts.length; i++){
    if (o.src[i] >= from && o.src[i] <= to) a.push(o.pts[i]);
  }
  return a;
}

/* ---- 코너 둥글리기: 각 꼭짓점을 2차 베지에로 갈아끼운다 ---- */
export function roundCorners(pts, px, zoom){
  if (pts.length < 3) return pts;
  var out = [pts[0]];
  for (var i = 1; i < pts.length-1; i++){
    var A = pts[i-1], B = pts[i], C = pts[i+1];
    var ml = mlon(B[1]);
    var ax = (A[0]-B[0])*ml, ay = (A[1]-B[1])*MLAT;
    var cx = (C[0]-B[0])*ml, cy = (C[1]-B[1])*MLAT;
    var la = Math.hypot(ax, ay), lc = Math.hypot(cx, cy);
    if (!la || !lc){ continue; }
    var cosang = (ax*cx + ay*cy) / (la*lc);
    if (cosang < -0.995){ out.push(B); continue; }        // 거의 직진 — 그대로
    var r = Math.min(px * mpp(B[1], zoom), OFFSET_MAX_M * 0.9, la*0.45, lc*0.45);
    if (r < 0.2){ out.push(B); continue; }
    var P = [ax/la*r, ay/la*r], Q = [cx/lc*r, cy/lc*r];
    var steps = 6;
    for (var k = 0; k <= steps; k++){
      var t = k/steps, u = 1-t;
      var mx = u*u*P[0] + t*t*Q[0];                        // 제어점 = 꼭짓점(원점)
      var my = u*u*P[1] + t*t*Q[1];
      out.push([ B[0] + mx/ml, B[1] + my/MLAT ]);
    }
  }
  out.push(pts[pts.length-1]);
  return out;
}

// path 의 idx 지점에서 경로를 거슬러 meters 만큼 뒤로 간 지점
export function walkBack(path, idx, meters){
  var i = Math.min(idx, path.length - 1), acc = 0;
  while (i > 0 && acc < meters){
    var a = path[i-1], b = path[i];
    var d = distM(a, b);
    if (acc + d >= meters){
      var t = (meters - acc) / d;                 // b 에서 a 쪽으로
      return {coord:[b[0]+(a[0]-b[0])*t, b[1]+(a[1]-b[1])*t], index:i-1, dist:meters};
    }
    acc += d; i--;
  }
  return {coord: path[Math.max(0,i)], index: Math.max(0,i), dist: acc};
}

export function bearingAt(path, i){
  var a = path[Math.max(0, i-2)], b = path[Math.min(path.length-1, i+2)];
  if (!a || !b) return 0;
  var lat = (a[1]+b[1])/2;
  var dx = (b[0]-a[0]) * mlon(lat), dy = (b[1]-a[1]) * MLAT;
  return Math.atan2(dx, dy) * 180 / Math.PI;     // 북 기준 시계방향
}

/* ---- 경로 라벨 자리 ----
   여러 경로가 같은 도로를 지나면 '경로 길이의 n%' 지점에 둔 라벨끼리 겹친다.
   다른 경로와 겹치지 않는(약 50m 격자 기준) 가장 긴 구간의 가운데에 둔다. 없으면 null. */
function cellKey(p){ return Math.round(p[0]*2000) + ',' + Math.round(p[1]*2000); }

export function uniqueLabelPoints(routes){
  var cells = routes.map(function(r){
    var s = new Set();
    r.path.forEach(function(p){ s.add(cellKey(p)); });
    return s;
  });
  return routes.map(function(r, i){
    var best = null, run = null;
    function close(){ if (run && (!best || run.len > best.len)) best = run; run = null; }
    for (var k = 0; k < r.path.length; k++){
      var key = cellKey(r.path[k]);
      var shared = cells.some(function(s, j){ return j !== i && s.has(key); });
      if (shared){ close(); continue; }
      if (!run) run = {from:k, to:k, len:0};
      else { run.len += distM(r.path[run.to], r.path[k]); run.to = k; }
    }
    close();
    if (!best || best.len < 150) return null;
    return r.path[Math.floor((best.from + best.to) / 2)];
  });
}
