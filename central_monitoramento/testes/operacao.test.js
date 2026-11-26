import test from 'node:test';
import assert from 'node:assert/strict';
import {OperacaoUI,direcaoTecla,editavel} from '../frontend/src/operacao.js';

test('teclas direcionais e campos editáveis têm contratos separados',()=>{
  assert.equal(direcaoTecla('W'),'frente');assert.equal(direcaoTecla('ArrowLeft'),'esquerda');
  assert.equal(direcaoTecla('S'),'re');assert.equal(direcaoTecla('z'),undefined);
  assert.equal(editavel({closest:()=>({tagName:'INPUT'})}),true);
});

test('presença: soltar tecla envia zero, perder foco libera, digitação não move',async()=>{
  const anteriorWindow=globalThis.window,anteriorDocument=globalThis.document;
  const eventos=new Map(),enviadas=[];
  globalThis.window={addEventListener:(n,fn)=>eventos.set(n,fn)};
  globalThis.document={hidden:false,addEventListener:(n,fn)=>eventos.set(n,fn),getElementById:()=>({value:2})};
  const ui=new OperacaoUI(async(p,d)=>{enviadas.push(d);return {};},()=>{});
  clearInterval(ui.timer);
  ui.estado={instancia:'servidor',epoch:1};ui.naPagina=true;
  try {
    await ui.acao('habilitar');
    assert.equal(ui.direcao,'parar');
    const texto={key:'w',code:'KeyW',repeat:false,target:{closest:()=>({})},preventDefault(){}};
    eventos.get('keydown')(texto);await Promise.resolve();
    assert.equal(ui.direcao,'parar');assert.equal(enviadas.length,1);
    eventos.get('keydown')({...texto,target:{closest:()=>null}});await new Promise(setImmediate);
    assert.equal(ui.direcao,'frente');assert.equal(enviadas.at(-1).direcao,'frente');
    eventos.get('keyup')({key:'W'});await new Promise(setImmediate);
    assert.equal(ui.direcao,'parar');assert.equal(enviadas.at(-1).direcao,'parar');
    eventos.get('blur')();await Promise.resolve();
    assert.equal(ui.habilitado,false);assert.equal(enviadas.at(-1).acao,'liberar');
    const antes=enviadas.length;await ui.renovar();assert.equal(enviadas.length,antes);
  } finally {
    globalThis.window=anteriorWindow;globalThis.document=anteriorDocument;
  }
});

test('não renova se a página está oculta ou sem foco',async()=>{
  const antesW=globalThis.window,antesD=globalThis.document;
  let chamadas=0;
  globalThis.window={addEventListener(){}};
  globalThis.document={hidden:true,addEventListener(){}};
  const ui=new OperacaoUI(async()=>{chamadas++;},()=>{});clearInterval(ui.timer);
  try {ui.habilitado=true;ui.naPagina=true;await ui.renovar();assert.equal(chamadas,0);
    document.hidden=false;ui.foco=false;await ui.renovar();assert.equal(chamadas,0);
  } finally {globalThis.window=antesW;globalThis.document=antesD;}
});
