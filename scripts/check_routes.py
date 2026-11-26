"""Run route diagnostics against the actual embedded JavaScript using macOS JSC."""
import json
import re
import subprocess
from pathlib import Path

html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
def block(name):
    return re.search(r'id="' + name + r'">(.*?)</script>', html, re.S).group(1)

def section(start, end):
    begin = html.index(start)
    return html[begin:html.index(end, begin)]

source = 'var window={}; var DB=' + block('j-db') + '; window._MC=' + block('j-mc') + ';'
source += section('var DUR =', 'function rememberRoute')
source += section('function rememberRoute', '// описание автора')
source += section('function hav(', '(function(){')
source += 'var CORE_LA=55.75249,CORE_LO=37.61536,CORE_R=3400; function saveRecent(){};'
source += section('function pathLen(', '// ── swap single place')
source += section('function resyncStops(', 'async function gen(){')
source += 'async function checkSubscription(){return true;}'
source += 'function trim2(s){return s;} function makeTitle(){return "";} function render(){};'
source += r'''(async function(){
var seed=42; Math.random=function(){seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
var total=0,examples=[],far=0,otherMetro=0,duplicates=0,phaseErrors=0,mutations=0;
var scenarios=[['еда','кофе'],['кофе','бар'],['еда','природа','бар']];
for(var mode=0;mode<3;mode++) for(var s=0;s<scenarios.length;s++){
  sc={};scenarios[s].forEach(function(c){sc[c]=1;});dur=mode;pts=3;
  metro=['Третьяковская'];recent=[];prevNames=[];
  var pool=DB.filter(function(p){return !!sc[p.c];});
  for(var n=0;n<40;n++){
    var r=pickCluster(pool,DUR[dur]),a=window._MC[metro[0]];
    var d=hav(a[0],a[1],r[0].la,r[0].lo);
    if(d>900)far++;
    if((r[0].metro||[])[0]!==metro[0])otherMetro++;
    if(metro[0]!=='Третьяковская')mutations++;
    if(r.some(function(p,i){return r.slice(0,i).some(function(q){return p.n===q.n;});}))duplicates++;
    if(r.some(function(p,i){return i>1&&dayPhase(p)<dayPhase(r[i-1]);}))phaseErrors++;
    if(r.some(function(p){return (p.metro||[])[0]==='Библиотека им. Ленина';})&&examples.length<3){
      examples.push({mode:mode,cats:scenarios[s],startDistance:Math.round(d),fallback:window._fallbackReason,
        route:r.map(function(p){return {name:p.n,category:p.c,metro:p.metro[0]};})});
    }
    rememberRoute(r);total++;
  }
}
var a=window._MC['Третьяковская'];
var synthetic=[{n:'Ресторан у метро',c:'еда',la:a[0],lo:a[1]},
 {n:'Кофейня далеко',c:'кофе',la:a[0]+0.02,lo:a[1]},
 {n:'Бар рядом',c:'бар',la:a[0]+0.001,lo:a[1]}];
var ordered=orderRoute(synthetic,a[0],a[1]);
if(far||mutations||duplicates||phaseErrors) throw new Error('Route regression');
if(ordered[0].n!=='Ресторан у метро') throw new Error('Anchor displaced');
var pair=orderRoute([synthetic[1],synthetic[0]],a[0],a[1]);
if(pair[0].n!=='Ресторан у метро') throw new Error('Two-stop anchor displaced');
if(orderRoute([],a[0],a[1]).length) throw new Error('Empty route');
var swaps=0;
sc={'еда':1,'кофе':1,'бар':1};dur=0;pts=3;
var swapPool=DB.filter(function(p){return !!sc[p.c];});
var button={classList:{add:function(){},remove:function(){}},textContent:''};
for(var trial=0;trial<20;trial++){
  var initial=pickCluster(swapPool,DUR[dur]);
  last={_picked:initial,stops:initial.map(function(p){return {name:p.n};}),_m:{spread:0}};
  for(var idx=0;idx<3;idx++){
    await swapPlace(idx,button);
    if(hav(a[0],a[1],last._picked[0].la,last._picked[0].lo)>900) throw new Error('Swap displaced start');
    if(last.stops.some(function(st,i){return st.name!==last._picked[i].n;})) throw new Error('Stops out of sync');
    swaps++;
  }
}
print(JSON.stringify({total:total,selectionMutations:mutations,startsOver900m:far,
 swapChecks:swaps,
 differentFirstPlaceMetro:otherMetro,duplicates:duplicates,phaseErrors:phaseErrors,
 anchorRegression:ordered.map(function(p){return p.n;}),examples:examples},null,2));
})().catch(function(e){print(e);quit(1);});
'''
subprocess.run(['/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc', '-e', source], check=True)
