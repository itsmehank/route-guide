/* 패널 배치 — 데스크톱: 지도 위 왼쪽 접이식 패널 / 모바일(≤720px): 3단 바텀시트.
   지도는 항상 화면 전체를 쓰고, 패널이 가리는 만큼은 insets() 로 알려 지도 시점 계산에 쓴다. */

var MQ = window.matchMedia('(max-width: 720px)');
var panel, onSnap, current = 'half', dragging = null;

export function isMobile(){ return MQ.matches; }

function heights(){
  var vh = window.innerHeight;
  return {peek: 132, half: Math.round(vh * 0.5), full: vh - 56};
}

function apply(h){
  panel.style.setProperty('--sheet-h', h + 'px');
}

export function setSnap(name){
  current = name;
  if (isMobile()) apply(heights()[name]);
  panel.dataset.snap = name;
}

export function snap(){ return current; }

export function insets(){
  var top = 0, right = 56, bottom = 0, left = 0;   // 오른쪽: 지도 컨트롤 줄
  if (isMobile()){
    bottom = panel.getBoundingClientRect().height;
    right = 12;
    top = 48;
  } else if (!panel.classList.contains('collapsed')){
    left = panel.getBoundingClientRect().right;
  }
  return {top: top, right: right, bottom: bottom, left: left};
}

export function initSheet(el, grab, opts){
  panel = el; onSnap = opts.onSnap;
  setSnap('half');

  // 손잡이는 누르기로도 높이를 바꿀 수 있어야 한다 (드래그 대체 수단, WCAG 2.5.7)
  grab.addEventListener('click', function(){
    if (dragging && dragging.moved) return;
    var next = {peek: 'half', half: 'full', full: 'peek'}[current];
    setSnap(next); onSnap(next);
  });

  grab.addEventListener('pointerdown', function(e){
    if (!isMobile()) return;
    dragging = {y: e.clientY, h: panel.getBoundingClientRect().height, moved: false};
    grab.setPointerCapture(e.pointerId);
    panel.classList.add('dragging');
  });
  grab.addEventListener('pointermove', function(e){
    if (!dragging) return;
    var dy = dragging.y - e.clientY;
    if (Math.abs(dy) > 4) dragging.moved = true;
    var hs = heights();
    apply(Math.max(hs.peek - 40, Math.min(hs.full, dragging.h + dy)));
  });
  grab.addEventListener('pointerup', function(){
    if (!dragging) return;
    panel.classList.remove('dragging');
    var h = panel.getBoundingClientRect().height, hs = heights();
    var best = Object.keys(hs).reduce(function(a, b){ return Math.abs(hs[a] - h) < Math.abs(hs[b] - h) ? a : b; });
    setSnap(best); onSnap(best);
    var d = dragging; setTimeout(function(){ if (dragging === d) dragging = null; }, 0);
  });

  MQ.addEventListener('change', function(){ setSnap(current); opts.onLayout(); });
  window.addEventListener('resize', function(){ setSnap(current); });
}

export function setCollapsed(on){
  panel.classList.toggle('collapsed', on);
}
