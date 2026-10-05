/* 부팅과 연결 — 사용자 동작(act) → state 변경 → 화면·지도 동기화. */
import {state, set, setCmp, setNarr, subscribe, transition, routeKeyOf, vias, MAX_VIA} from './store.js';
import {fetchRoute, fetchEvaluation, streamNarration, searchPlaces} from './api.js';
import {bindSearch} from './search.js';
import {friendlyError, esc} from './format.js';
import * as mapv from './mapview.js';
import * as sheet from './sheet.js';
import {clampNudge} from './roadview.js';
import {renderList} from './views/list.js';
import {renderDetail, leaveDetail} from './views/detail.js';
import {renderCompare, leaveCompare} from './views/compare.js';

var $ = function(id){ return document.getElementById(id); };
var routeCtrl = null, evalCtrl = null, narrStream = null;

function announce(msg){ var el = $('status'); el.textContent = ''; setTimeout(function(){ el.textContent = msg; }, 30); }

function toast(html){
  var t = $('toast'); t.innerHTML = html; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(function(){ t.hidden = true; }, 9000);
}
window.navermap_authFailure = function(){
  toast('<b>네이버 지도 인증에 실패했어요.</b><br>이 페이지는 <code>http://localhost:3000</code> 에서 열어야 해요.');
};

/* ---- 입력 칸: origin · wp0~wp2 · goal ---- */
var SLOTS = ['origin', 'wp0', 'wp1', 'wp2', 'goal'];
function getSlot(slot){ return slot.indexOf('wp') === 0 ? state.wp[+slot.slice(2)] : state[slot]; }
function slotPatch(slot, place){
  var p = {};
  if (slot.indexOf('wp') === 0){ var w = state.wp.slice(); w[+slot.slice(2)] = place; p.wp = w; }
  else p[slot] = place;
  return p;
}

/* ====================== 동작 ====================== */
var act = {
  pick: function(slot, place){
    var patch = slotPatch(slot, place); patch.editing = false;
    set(patch);
    if (state.origin && state.goal) act.findRoute();
  },

  findRoute: function(){
    var key = routeKeyOf(state);
    if (!key) return;
    if (routeCtrl) routeCtrl.abort();
    resetCompare();
    if (state.origin.coord.join(',') === state.goal.coord.join(',')){
      set({routeKey: key, routeStatus: 'error', routeError: '출발지와 도착지가 같아요. 다른 곳을 골라 주세요.',
           routes: [], view: 'list', step: null});
      return;
    }
    routeCtrl = new AbortController();
    set({routeKey: key, routeStatus: 'loading', view: 'list', step: null, hazard: null, hover: null});
    fetchRoute(state, routeCtrl.signal).then(function(d){
      if (state.routeKey !== key) return;                 // 그 사이 입력이 바뀌었다
      set({routes: d.routes, sel: 0, routeStatus: 'ok'});
      mapv.fitRoute(d.routes[0]);
      announce('경로 ' + d.routes.length + '개를 찾았어요.');
    }).catch(function(e){
      if (e.name === 'AbortError' || state.routeKey !== key) return;
      set({routeStatus: 'error', routeError: friendlyError(e.data || {error: e.message}), routes: []});
    });
  },
  retry: function(){ act.findRoute(); },

  selectRoute: function(i){
    if (i === state.sel) { mapv.fitRoute(state.routes[i]); return; }
    set({sel: i, step: null, nudge: 0, hazard: null});
    mapv.fitRoute(state.routes[i]);
  },
  hover: function(i){ if (state.hover !== i) set({hover: i}); },

  openDetail: function(i){
    transition({sel: i, view: 'detail', step: null, nudge: 0, hover: null, hazard: null});
    mapv.fitRoute(state.routes[i]);
  },
  focusStep: function(i){
    var r = state.routes[state.sel]; if (!r) return;
    set({step: i, nudge: 0});
    if (sheet.isMobile() && sheet.snap() === 'peek'){ sheet.setSnap('half'); set({sheet: 'half'}); }
    var g = r.guides[i];
    mapv.focusPoint(r.path[Math.min(g.pointIndex, r.path.length - 1)], 90);
  },
  nudge: function(delta){
    var r = state.routes[state.sel]; if (!r || state.step === null) return;
    set({nudge: clampNudge(r, state.step, state.nudge + delta)});
  },
  back: function(){
    transition({view: 'list', step: null, hazard: null});
    if (state.routes.length) mapv.fitRoute(state.routes[state.sel]);
  },

  openCompare: function(){
    transition({view: 'compare', step: null});
    if (sheet.isMobile()){ sheet.setSnap('full'); set({sheet: 'full'}); }
    ensureCompare();
  },
  startNarration: function(force){
    if (state.cmp.status === 'error' || !state.cmp.data){ resetCompare(); ensureCompare(); return; }
    startNarration(force);
  },
  stopNarration: function(){
    if (narrStream) narrStream.close();
    narrStream = null;
    setNarr({status: 'stopped'});
  },
  hazard: function(routeId, idx){
    var i = state.routes.findIndex(function(r){ return r.option === routeId; });
    if (i < 0) return;
    var er = state.cmp.data.evaluation.routes.find(function(x){ return x.id === routeId; });
    var h = er && er.hazards[idx]; if (!h) return;
    set({sel: i, hazard: {id: routeId, idx: idx}});
    if (sheet.isMobile()){ sheet.setSnap('half'); set({sheet: 'half'}); }
    // 패널은 그대로 두고 지도만 그 지점으로 — 목록으로 돌아올 때 스크롤을 잃지 않는다
    mapv.focusPoint(h.coord, 220);
  },
  roadview: function(ri, step){
    // transition 은 비동기로 적용된다 — 단계까지 한 번에 넘겨야 뒤늦게 step 이 덮이지 않는다
    transition({sel: ri, view: 'detail', step: step, nudge: 0, hazard: null, hover: null});
    var r = state.routes[ri], g = r && r.guides[step];
    if (g) mapv.focusPoint(r.path[Math.min(g.pointIndex, r.path.length - 1)], 90);
  },
  fitAll: function(){
    set({step: state.view === 'detail' ? null : state.step, hazard: null});
    if (state.routes.length) mapv.fitRoute(state.routes[state.sel]);
  }
};

/* ====================== 경로 비교 ====================== */
function resetCompare(){
  if (evalCtrl) evalCtrl.abort();
  if (narrStream) narrStream.close();
  evalCtrl = null; narrStream = null;
  setCmp({key: null, status: 'idle', data: null, error: null,
          narr: {status: 'idle', data: null, stage: null, startedAt: 0, error: null}});
}

function ensureCompare(){
  var key = state.routeKey;
  if (state.cmp.key === key && state.cmp.status !== 'error') return;   // 이미 받았거나 받는 중 — 다시 부르지 않는다
  resetCompare();
  evalCtrl = new AbortController();
  setCmp({key: key, status: 'loading'});
  fetchEvaluation(state, evalCtrl.signal).then(function(d){
    if (state.cmp.key !== key) return;
    setCmp({status: 'ok', data: d});
    announce('비교표가 준비됐어요. AI 설명은 이어서 도착해요.');
    startNarration(false);
  }).catch(function(e){
    if (e.name === 'AbortError' || state.cmp.key !== key) return;
    console.warn('[route-guide] 평가 실패', e);
    setCmp({status: 'error', error: e.message});
  });
}

function startNarration(){
  var key = state.cmp.key;
  if (narrStream) narrStream.close();
  setNarr({status: 'streaming', stage: 'start', data: null, error: null, startedAt: Date.now()});
  var mine = function(){ return state.cmp.key === key && state.cmp.narr.status === 'streaming'; };
  narrStream = streamNarration(state, {
    stage:   function(d){ if (mine()) setNarr({stage: d.stage}); },
    partial: function(d){ if (mine()) setNarr({data: d.narration, stage: 'writing'}); },
    retry:   function(){ if (mine()) setNarr({stage: 'retry', data: null}); },
    done:    function(d){
      if (!mine()) return;
      narrStream = null;
      setNarr({status: 'done', data: d.narration});
      announce('AI 경로 설명이 완성됐어요.');
    },
    fail:    function(d){
      if (!mine()) return;
      narrStream = null;
      setNarr({status: 'error', error: d.error});
    }
  });
}

/* ====================== 화면 동기화 ====================== */
var shown = null, listSig = null;

function render(s){
  // 입력부
  for (var i = 0; i < MAX_VIA; i++) $('f-wp' + i).hidden = i >= s.viaCount;
  $('viaadd').hidden = s.viaCount >= MAX_VIA;
  $('viacnt').textContent = s.viaCount ? s.viaCount + '/' + MAX_VIA : '';
  ['origin', 'goal'].forEach(function(k){
    var c = document.querySelector('[data-clear=' + k + ']');
    if (c) c.hidden = !$('q-' + k).value;
  });
  var hasTrip = !!(s.origin && s.goal && s.routes.length);
  $('panel').classList.toggle('has-trip', hasTrip && !s.editing);
  if (hasTrip) $('tripsum').innerHTML = '<span class="dot o"></span>' + esc(s.origin.title)
    + vias(s).map(function(p){ return ' <span class="muted">→ ' + esc(p.title) + '</span>'; }).join('')
    + ' → <span class="dot g"></span>' + esc(s.goal.title) + '<span class="edit">수정</span>';

  // 화면 전환
  if (shown !== s.view){
    if (shown === 'detail') leaveDetail($('v-detail'));
    if (shown === 'compare') leaveCompare();
    ['list', 'detail', 'compare'].forEach(function(v){ $('v-' + v).hidden = v !== s.view; });
    shown = s.view;
    listSig = null;
    $('pbody').scrollTop = 0;
  }
  if (s.view === 'list'){
    var sig = [s.routeKey, s.routeStatus, s.routes.length, s.sel, s.cmp.status].join('|');
    if (sig !== listSig){ renderList($('v-list'), s, act); listSig = sig; }
  }
  if (s.view === 'detail') renderDetail($('v-detail'), s, act);
  if (s.view === 'compare') renderCompare($('v-compare'), s, act);

  // 지도 컨트롤
  $('traffic').setAttribute('aria-pressed', String(s.traffic));
  $('fitall').hidden = !(s.step !== null || s.hazard);
  mapv.sync(s);
}

/* ====================== 부팅 ====================== */
function boot(){
  if (typeof naver === 'undefined' || !naver.maps){
    toast('지도 스크립트를 불러오지 못했어요.');
    return;
  }
  sheet.initSheet($('panel'), $('grab'), {
    onSnap: function(name){ set({sheet: name}); },
    onLayout: function(){ mapv.refresh(); }
  });
  mapv.init($('map'), {
    selectRoute: function(i){ act.selectRoute(i); },
    hoverRoute: act.hover,
    hazardClick: function(id, idx){
      if (state.view !== 'compare') transition({view: 'compare'});
      act.hazard(id, idx);
    },
    redraw: function(){ mapv.sync(state); }
  }, sheet.insets);

  SLOTS.forEach(function(slot, n){
    bindSearch({
      input: $('q-' + slot), list: $('sg-' + slot), field: $('f-' + slot),
      onPick: function(p){ act.pick(slot, p); },
      onClear: function(){ if (getSlot(slot)) set(slotPatch(slot, null)); else set({}); },
      hasValue: function(){ return !!getSlot(slot); },
      reference: function(){
        // 기준점: 바로 앞 칸(출발지는 도착지), 없으면 지도 중심
        var prev = null;
        for (var j = n - 1; j >= 0 && !prev; j--) prev = getSlot(SLOTS[j]);
        var other = slot === 'origin' ? state.goal : prev || state.goal;
        return other ? other.coord : mapv.center();
      },
      status: announce
    });
  });

  document.querySelectorAll('[data-clear]').forEach(function(b){
    b.onclick = function(){
      var k = b.dataset.clear, p = {editing: true}; p[k] = null;
      $('q-' + k).value = '';
      set(p);
      $('q-' + k).focus();
    };
  });
  $('viaadd').onclick = function(){
    if (state.viaCount >= MAX_VIA) return;
    var i = state.viaCount;
    set({viaCount: i + 1, editing: true});
    setTimeout(function(){ $('q-wp' + i).focus(); });
  };
  // 경유지 삭제: 뒤 칸을 한 칸씩 당긴다 (입력 글자도 함께)
  document.querySelectorAll('[data-viadel]').forEach(function(b){
    b.onclick = function(){
      var i = +b.dataset.viadel, had = !!state.wp[i];
      var w = state.wp.slice(); w.splice(i, 1); w.push(null);
      for (var j = i; j < MAX_VIA; j++) $('q-wp' + j).value = j + 1 < MAX_VIA ? $('q-wp' + (j + 1)).value : '';
      set({wp: w, viaCount: state.viaCount - 1});
      if (had && state.origin && state.goal) act.findRoute();
    };
  });
  $('swap').onclick = function(){
    var a = $('q-origin'), b = $('q-goal'), t = a.value; a.value = b.value; b.value = t;
    // 방향이 뒤집히면 경유 순서도 뒤집는다
    var n = state.viaCount, w = state.wp.slice(0, n).reverse().concat(state.wp.slice(n));
    var texts = []; for (var i = 0; i < n; i++) texts.push($('q-wp' + i).value);
    texts.reverse().forEach(function(v, i){ $('q-wp' + i).value = v; });
    set({origin: state.goal, goal: state.origin, wp: w});
    if (state.origin && state.goal) act.findRoute();
  };
  $('tripsum').onclick = function(){
    set({editing: true});
    if (sheet.isMobile()){ sheet.setSnap('full'); set({sheet: 'full'}); }
    setTimeout(function(){ $('q-origin').focus(); });
  };
  $('collapse').onclick = function(){
    sheet.setCollapsed(true); $('expand').hidden = false; $('expand').focus();
    setTimeout(mapv.refresh, 250);
  };
  $('expand').onclick = function(){
    sheet.setCollapsed(false); $('expand').hidden = true; $('collapse').focus();
    setTimeout(mapv.refresh, 250);
  };
  $('traffic').onclick = function(){ set({traffic: !state.traffic}); };
  $('fitall').onclick = act.fitAll;

  subscribe(render);
  set({});

  // 데모: 첫 진입 시 죽전역 → 강남역을 채워 둔다
  Promise.all([prefill('origin', '죽전역'), prefill('goal', '강남역')]).then(function(){
    if (state.origin && state.goal) act.findRoute();
  });
}

function prefill(slot, query){
  $('q-' + slot).value = query;
  return searchPlaces(query).then(function(places){
    if (places.length){
      var p = {}; p[slot] = places[0]; set(p);
      $('q-' + slot).value = places[0].title;
    }
  }).catch(function(){});
}

boot();
