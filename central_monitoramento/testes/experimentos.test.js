import test from 'node:test';
import assert from 'node:assert/strict';
import { matriz,htmlCiencia } from '../frontend/src/experimentos.js';
import { extrair,identidade } from '../frontend/src/nucleo.js';
test('ausência de execução permanece indisponível na matriz A–D',()=>{
  assert.equal(matriz([]).length,4);assert.equal(matriz([])[0].media,null);
});
test('cada execução tem um voto e registros falhos não viram medição',()=>{
  const r=(v,estado='concluida')=>({configuracao:'A',estado,resultado:{metricas:{inferencia_s:{media:v}}}});
  const m=matriz([r(1),r(3),r(100,'falha')]);assert.equal(m[0].repeticoes,2);assert.equal(m[0].media,2);
});
test('plano e controles científicos identificam a simulação parada',()=>{
  const h=htmlCiencia();assert.ok(h.includes('simulador parado'));assert.ok(h.includes('cancelar-ciencia'));assert.ok(h.includes('nível')||h.includes('Nível'));
});
test('navegação antes da primeira telemetria mantém campos indisponíveis',()=>{
  assert.equal(extrair(null).erro,null);assert.equal(extrair(null).pps_esq,null);assert.equal(identidade(null),'::');
});
