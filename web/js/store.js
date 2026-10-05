/* 화면 상태는 여기 한 곳에만 둔다. 화면은 state 를 읽어서 그리고, 바꿀 때는 set() 을 부른다.
   (예전처럼 'detail 패널에 open 클래스가 있나'로 상태를 추측하지 않는다.) */

export var state = {
  origin: null, goal: null,                   // 검색 후보 객체 {title, coord, ...}
  wp: [null, null, null],                     // 경유지 칸 (최대 3개, Directions 15 는 5개까지 받는다)
  viaCount: 0,                                // 열려 있는 경유지 칸 수

  routeKey: null,                             // 출발|도착|경유 좌표 — 늦게 도착한 응답을 버리는 기준
  routeStatus: 'idle',                        // idle | loading | ok | error
  routeError: null,
  routes: [],
  sel: 0,

  view: 'list',                               // list | detail | compare
  step: null,                                 // 상세에서 고른 안내 단계(guide index)
  nudge: 0,                                   // 로드뷰 관측 지점 앞뒤 미세조정(m)
  hover: null,                                // 카드 hover 중인 경로

  cmp: {
    key: null,
    status: 'idle',                           // idle | loading | ok | error
    data: null, error: null,
    narr: {status:'idle', data:null, stage:null, startedAt:0, error:null}  // idle|streaming|done|error|stopped
  },
  hazard: null,                               // {route, idx} 지도에서 강조할 위험 지점

  traffic: false,                             // 실시간 교통 레이어 (기본 끔: 경로 색과 같은 3색이라 경로가 묻힌다)
  editing: false,                             // 경로가 있어도 입력부를 펼쳐 둔 상태
  sheet: 'half'                               // 모바일 바텀시트 높이 peek | half | full
};

var subs = [];
var pending = false;

export function subscribe(fn){ subs.push(fn); }

export function set(patch){
  Object.assign(state, patch);
  if (!pending){ pending = true; queueMicrotask(flush); }
}

export function setCmp(patch){ set({cmp: Object.assign({}, state.cmp, patch)}); }
export function setNarr(patch){ setCmp({narr: Object.assign({}, state.cmp.narr, patch)}); }

export function flush(){
  pending = false;
  subs.forEach(function(fn){ fn(state); });
}

// 화면 전환(목록 ↔ 상세 ↔ 비교)은 View Transition 으로 부드럽게. 지원 안 하면 즉시 바뀐다.
export function transition(patch){
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!document.startViewTransition || reduce){ set(patch); return; }
  var t = document.startViewTransition(function(){ Object.assign(state, patch); flush(); });
  // 탭이 백그라운드이거나 전환이 겹치면 애니메이션만 취소된다(상태 변경은 그대로 적용). 거부를 삼킨다.
  t.ready.catch(function(){}); t.finished.catch(function(){});
}

export var MAX_VIA = 3;

// 채워진 경유지만, 순서대로
export function vias(s){ return s.wp.slice(0, s.viaCount).filter(Boolean); }

export function routeKeyOf(s){
  if (!(s.origin && s.goal)) return null;
  return s.origin.coord.join(',') + '|' + s.goal.coord.join(',') + '|'
    + vias(s).map(function(p){ return p.coord.join(','); }).join(';');
}
