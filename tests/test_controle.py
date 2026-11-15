"""Testes do controle (hierarquia de voz, PD, ação do aprendizado, obstáculo) com um motor FALSO. Sem hardware."""
import sys
import threading
import time
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from controle import ThreadControle, aplicar_comando, calcular_motores, filtrar_derivada  # noqa: E402
from estado import EstadoRobo, Modo  # noqa: E402
from motor.nulo import ArduinoNulo  # noqa: E402


class MotorFalso:
    def __init__(self):
        self.cmds, self.paradas, self.obst = [], 0, False

    def motores(self, e, d): self.cmds.append((e, d))
    def parar(self, repetir=1): self.paradas += 1; self.cmds.append((0, 0))
    def obstaculo(self, limite, n): return self.obst
    def sensores(self):
        return SimpleNamespace(timestamp=time.monotonic(), falha_sensor=False,
                               avanco_bloqueado=self.obst, distancia_cm=40)


def _rodar(est, mot, segundos):
    parar = threading.Event()
    t = ThreadControle(est, mot, parar); t.start()
    time.sleep(segundos)
    parar.set(); t.join(2)
    assert not t.is_alive()


def test_calcular_motores_sentido_e_limites():
    e, d = calcular_motores(0.5, 0.0)
    assert e > d                                             # linha à direita -> motor esquerdo mais forte (vira p/ direita)
    e, d = calcular_motores(-0.5, 0.0); assert e < d
    e, d = calcular_motores(50.0, 0.0); assert -cfg.VEL_MAX <= d and e <= cfg.VEL_MAX


def test_filtro_da_derivada():
    assert filtrar_derivada(0.0, 1.0, 0.0, 1.0, 1.0) == 1.0                 # alfa 1 = sem filtro
    assert abs(filtrar_derivada(0.0, 1.0, 0.0, 1.0, 0.3) - 0.3) < 1e-12    # suaviza degrau
    assert abs(filtrar_derivada(2.0, 0.0, 0.0, 1.0, 0.3) - 1.4) < 1e-12    # puxa para o novo valor aos poucos


def test_parado_nao_anda_e_pare_de_voz_corta_na_hora():
    est, mot = EstadoRobo(), MotorFalso()
    est.publicar_leitura(0.0, True)
    _rodar(est, mot, 0.3)
    assert all(c == (0, 0) for c in mot.cmds)                                # PARADO só manda parar
    aplicar_comando(est, mot, "siga"); assert est.modo is Modo.SEGUINDO
    n = mot.paradas
    aplicar_comando(est, mot, "pare")
    assert est.modo is Modo.PARADO and mot.paradas > n


def test_seguindo_usa_pd_com_leitura_fresca_e_para_se_ficou_velha():
    est, mot = EstadoRobo(), MotorFalso()
    est.definir_modo(Modo.SEGUINDO)
    parar = threading.Event(); t = ThreadControle(est, mot, parar); t.start()
    for _ in range(10):
        est.publicar_leitura(0.4, True); time.sleep(0.05)
    assert any(e > d for e, d in mot.cmds)                                   # corrige para a direita
    time.sleep(cfg.PERDA_LINHA_TIMEOUT_S + 0.4)                              # sem leituras novas: acaba parando
    parar.set(); t.join(2)
    assert mot.cmds[-1] == (0, 0)


def test_obstaculo_para_o_seguir():
    est, mot = EstadoRobo(), MotorFalso(); mot.obst = True
    est.definir_modo(Modo.SEGUINDO)
    parar = threading.Event(); t = ThreadControle(est, mot, parar); t.start()
    for _ in range(8):
        est.publicar_leitura(0.0, True); time.sleep(0.05)
    parar.set(); t.join(2)
    assert all(c == (0, 0) for c in mot.cmds)


def test_aprendizado_ativo_executa_acao_e_para_sem_acao_recente():
    cfg.APRENDIZADO_ATIVO = True
    try:
        est, mot = EstadoRobo(), MotorFalso()
        est.definir_modo(Modo.SEGUINDO)
        parar = threading.Event(); t = ThreadControle(est, mot, parar); t.start()
        for _ in range(6):
            est.publicar_acao(0.8, 1.0); time.sleep(0.05)
        assert any(e > d for e, d in mot.cmds)                               # steer>0 -> gira p/ a direita
        time.sleep(cfg.APR_ACAO_VALIDADE_S + 0.3)                            # ação envelhece: motores param
        assert mot.cmds[-1] == (0, 0)
        est.publicar_acao(0.8, 1.0); time.sleep(0.2)
        aplicar_comando(est, mot, "pare")
        assert est.ler_acao() is None                                        # 'pare' apaga a ação pendente
        parar.set(); t.join(2)
    finally:
        cfg.APRENDIZADO_ATIVO = False


def test_acao_so_vale_em_modo_seguindo():
    est = EstadoRobo()
    assert est.publicar_acao(0.5, 1.0) is False and est.ler_acao() is None  # PARADO: recusa
    est.definir_modo(Modo.SEGUINDO)
    assert est.publicar_acao(0.5, 1.0) is True and est.ler_acao().steer == 0.5
    est.definir_modo(Modo.PARADO); assert est.ler_acao() is None


def test_motor_nulo_tem_a_interface_do_arduino():
    m = ArduinoNulo(); m.conectar()
    m.motores(100, -100); assert m.ultimo == (100, -100)
    m.parar(repetir=3); assert m.ultimo == (0, 0)
    assert m.sensores() is None and m.obstaculo(20, 3) is False
    m.fechar()



class MotorInspecao(MotorFalso):
    def __init__(self):
        super().__init__()
        self.obst = True
        self.renovacoes, self.centros = 0, []
        self.pacote = SimpleNamespace(timestamp=100., falha_sensor=False,
                                     avanco_bloqueado=True, distancia_cm=20, obstaculo_confirmado=True)
        self.status, self.amostras = None, []
    def sensores(self): return self.pacote
    def inspecionar_obstaculo(self): self.renovacoes += 1
    def configurar_servo(self, varrer=False): self.centros.append(varrer)
    def status_servo(self): return self.status
    def leituras_inspecao(self): return self.amostras


def test_inspecao_espera_repouso_conclui_parada_e_nao_reutiliza_amostras():
    est, mot = EstadoRobo(), MotorInspecao()
    est.definir_modo(Modo.SEGUINDO)
    t = ThreadControle(est, mot, threading.Event())
    assert t._inspecionar_obstaculo(100.) and mot.renovacoes == 0
    assert t._inspecionar_obstaculo(100.5) and mot.renovacoes == 1
    mot.status = SimpleNamespace(ativo=True, inspecao=True, concluida=True, timestamp=101.)
    mot.amostras = [SimpleNamespace(angulo_nominal=a, distancia_cm=None, rodada=1, timestamp=99.)
                    for a in (45, 90, 135)]
    t._inspecionar_obstaculo(101.)
    assert est.modo is Modo.SEGUINDO  # amostras antigas nao concluem a nova rodada
    for a in mot.amostras: a.timestamp = 101.
    t._inspecionar_obstaculo(101.)
    assert est.modo is Modo.PARADO and t._inspecao_inicio is None
    assert mot.centros == [False] and all(c == (0, 0) for c in mot.cmds)


def test_inspecao_timeout_e_sensor_invalido_nao_iniciam_desvio():
    est, mot = EstadoRobo(), MotorInspecao()
    est.definir_modo(Modo.SEGUINDO)
    t = ThreadControle(est, mot, threading.Event())
    mot.pacote.obstaculo_confirmado = False
    assert not t._inspecionar_obstaculo(100.)
    mot.pacote.obstaculo_confirmado = True
    mot.pacote.falha_sensor = True
    assert not t._inspecionar_obstaculo(100.) and mot.renovacoes == 0
    mot.pacote.falha_sensor = False
    mot.pacote.timestamp = 90.
    assert not t._inspecionar_obstaculo(100.)
    mot.pacote.timestamp = 100.
    t._inspecionar_obstaculo(100.)
    t._inspecionar_obstaculo(100. + cfg.INSPECAO_TIMEOUT_S + .1)
    assert est.modo is Modo.PARADO and mot.centros == [False]
    assert all(c == (0, 0) for c in mot.cmds)


def test_manual_e_pare_interrompem_servo_sem_esperar_ciclo():
    from controle import aplicar_movimento_manual
    est, mot = EstadoRobo(), MotorInspecao()
    est.definir_modo(Modo.SEGUINDO)
    aplicar_movimento_manual(est, mot, 80, 80)
    assert est.modo is Modo.MANUAL and mot.centros == [False]
    aplicar_comando(est, mot, 'pare')
    assert est.modo is Modo.PARADO and mot.centros == [False, False]
    assert mot.cmds[-1] == (0, 0)

if __name__ == "__main__":
    falhou = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("ok   ", n)
            except Exception:
                import traceback; falhou += 1; print("FALHA", n); traceback.print_exc()
    print("tudo ok" if not falhou else f"{falhou} falhas"); sys.exit(1 if falhou else 0)
