"""Exercise the actual subscription gate without contacting Telegram."""
import subprocess
from pathlib import Path

html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()
gate = html[html.index('var subscriptionBusy='):html.index("document.getElementById('subscriptionRetry').addEventListener")]
setup = r'''
var nodes={};
var document={getElementById:function(id){return nodes[id]||(nodes[id]={hidden:false,disabled:false,style:{}});}};
var location={search:'?api=https://service.onrender.com'};
function URLSearchParams(){this.get=function(){return 'https://service.onrender.com';};}
function AbortController(){this.signal={};this.abort=function(){};}
function setTimeout(){return 1;} function clearTimeout(){}
var tg={initData:'signed session'}, response={subscribed:true}, fail=false;
async function fetch(){if(fail)throw new Error('network');return {ok:true,json:async function(){return response;}};}
'''
checks = r'''
(async function(){
  if(!await checkSubscription()||nodes.routeApp.hidden)throw Error('Subscriber blocked');
  response={subscribed:false};
  if(await checkSubscription()||!nodes.routeApp.hidden||nodes.subscriptionGate.hidden)throw Error('Unsubscriber allowed');
  response={subscribed:true};
  if(!await checkSubscription())throw Error('Resubscription blocked');
  fail=true;
  if(await checkSubscription()||!nodes.routeApp.hidden)throw Error('Network error allowed');
  fail=false;tg.initData='';
  if(await checkSubscription()||!nodes.routeApp.hidden)throw Error('Missing Telegram session allowed');
  print('PASS: subscriber, unsubscribe, resubscribe, API failure and missing session');
})().catch(function(e){print(e);quit(1);});
'''
subprocess.run(['/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc',
                '-e', setup + gate + checks], check=True)
