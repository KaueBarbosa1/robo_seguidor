"""Controle remoto por Bluetooth: interpretador, modo MANUAL do controle, sessões de celular e o servidor
registrado num BlueZ FALSO (dbus-daemon privado). SIMULADO: não usa Bluetooth real, nem BlueZ real, nem celular.
Exige `dbus-daemon` e `dbus-fast` para a parte do servidor (se faltarem, essa parte é pulada e avisa).
    python tests/test_remoto.py
"""
import asyncio
import importlib.util
import shutil
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from controle import ThreadControle, aplicar_comando, aplicar_movimento_manual  # noqa: E402
from estado import EstadoRobo, Modo  # noqa: E402
from remoto.bluetooth_spp import SessaoRemota, ThreadBluetooth, mac_do_caminho  # noqa: E402
from remoto.comandos import (CONFIG_BLUEDOT, InterpretadorRemoto, calcular_pwm, calcular_pwm_analogico,
                             calcular_pwm_eletrogate)  # noqa: E402


b = None   # só para o pyflakes: "b" (booleano D-Bus) aparece como anotação de texto no BlueZ falso


class MotorFalso:
    def __init__(self):
        self.cmds, self.obst = [], False

    def motores(self, e, d): self.cmds.append((e, d))
    def parar(self, repetir=1): self.cmds.append((0, 0))
    def obstaculo(self, limite, n): return self.obst
    def sensores(self):
        return SimpleNamespace(timestamp=time.monotonic(), falha_sensor=False,
                               avanco_bloqueado=self.obst, distancia_cm=40)
    def ultimo(self): return self.cmds[-1] if self.cmds else None


def esperar(cond, t=3.0):
    fim = time.monotonic() + t
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def _tipos(dados, interp=None):
    i = interp or InterpretadorRemoto()
    return [(c.tipo, c.valor, c.de_linha) for c in i.alimentar(dados)]


# ----------------------------------------------------------------------------- interpretador
def test_botoes_de_app_rc():
    assert _tipos(b"F") == [("mover", "frente", False)]
    assert _tipos(b"B") == [("mover", "tras", False)]
    assert _tipos(b"L") == [("mover", "esq", False)] and _tipos(b"R") == [("mover", "dir", False)]
    assert [t[1] for t in _tipos(b"GIHJ")] == ["frente_esq", "frente_dir", "tras_esq", "tras_dir"]
    assert _tipos(b"S") == [("parar", None, False)] and _tipos(b"D") == [("parar", None, False)]
    assert _tipos(b"7") == [("velocidade", 7, False)] and _tipos(b"q") == [("velocidade", 10, False)]
    assert _tipos(b"wUvX")[0][0] == "ignorar"


def test_texto_com_enter_e_acentos():
    assert _tipos(b"frente\n") == [("mover", "frente", True)]
    assert _tipos(b"TRAS\r\n") == [("mover", "tras", True)]
    assert _tipos("ré\n".encode()) == [("mover", "tras", True)]
    assert _tipos(b"vel 4\n") == [("velocidade", 4, True)] and _tipos(b"velocidade 10\n") == [("velocidade", 10, True)]
    assert _tipos(b"vel 11\n")[0][0] == "desconhecido"
    assert _tipos(b"pare\n") == [("parar", None, True)] and _tipos(b"f\n") == [("mover", "frente", True)]
    assert _tipos(b"status\n")[0][0] == "status" and _tipos(b"ajuda\n")[0][0] == "ajuda"
    assert _tipos(b"abracadabra\n")[0][0] == "desconhecido"


def test_texto_em_pedacos_nao_vira_botao():
    i = InterpretadorRemoto()
    assert _tipos(b"fre", i) == [] and _tipos(b"nte\n", i) == [("mover", "frente", True)]


def test_lixo_nao_trava_os_proximos_comandos():
    t = [0.0]
    i = InterpretadorRemoto(relogio=lambda: t[0])
    assert _tipos(b"\xff\xfeS", i) == [("parar", None, False)]          # lixo antes do S: o S vale
    assert _tipos(b"zz", i) == []                                       # resto pendente sem Enter...
    t[0] += 1.0                                                         # ...que envelhece
    assert _tipos(b"F", i) == [("mover", "frente", False)]


def test_pwm_por_direcao_e_limite():
    assert calcular_pwm("frente", 10) == (cfg.REMOTO_VEL_MAX, cfg.REMOTO_VEL_MAX)
    assert calcular_pwm("frente", 0) == (0, 0)
    e, d = calcular_pwm("esq", 5); assert e < 0 < d                      # esquerda: roda esquerda para trás
    e, d = calcular_pwm("dir", 5); assert d < 0 < e
    e, d = calcular_pwm("frente_esq", 5); assert 0 < e < d               # curva à esquerda: roda esquerda mais lenta
    e, d = calcular_pwm("tras", 5); assert e < 0 and d < 0
    assert max(abs(x) for x in calcular_pwm("frente", 99)) <= min(cfg.VEL_MAX, cfg.REMOTO_VEL_MAX)


# ----------------------------------------------------------------------------- app Blue Dot (analógico)
def test_bluedot_protocolo_linhas():
    assert _tipos(b"3,2,Blue Dot Android\n") == [("dot_protocolo", (2, "Blue Dot Android"), True)]
    assert _tipos(b"1,0,0,0.25,-0.5\n") == [("dot_toque", (0.25, -0.5), True)]
    assert _tipos(b"2,0,0,3.0,-9\n") == [("dot_toque", (1.0, -1.0), True)]          # fora da faixa: trava em +-1 (como a biblioteca)
    assert _tipos(b"0,0,0,0.0,0.0\n")[0][0] == "dot_soltar"
    assert _tipos(b"1,0,0,0.1,0.1\n2,0,0,0.2,0.2\n0,0,0,0.2,0.2\n") == [("dot_toque", (0.1, 0.1), True), ("dot_toque", (0.2, 0.2), True), ("dot_soltar", (0.2, 0.2), True)]
    for ruim in (b"1,1,0,0.5,0.5\n", b"1,0,0,abc,1\n", b"1,0,0\n", b"1,0,0,nan,0\n", b"4,xyz\n"):    # outro botão, corrompida, incompleta
        assert _tipos(ruim)[0][0] == "ignorar", ruim


def test_bluedot_pedaco_de_linha_nao_vira_botao_nem_velocidade():
    i = InterpretadorRemoto()
    assert _tipos(b"3,2,Blue Dot\n", i)[0][0] == "dot_protocolo"
    assert _tipos(b"1,0,0,0.5,0.", i) == []                                             # termina em dígito: NÃO é velocidade
    assert _tipos(b"5\n", i) == [("dot_toque", (0.5, 0.5), True)]


def test_mistura_analogica():
    assert calcular_pwm_analogico(0, 0) == (0, 0) and calcular_pwm_analogico(0.1, 0.1) == (0, 0)   # zona morta
    assert calcular_pwm_analogico(0, 1) == (cfg.REMOTO_VEL_MAX, cfg.REMOTO_VEL_MAX)                # tudo para cima: frente
    assert calcular_pwm_analogico(0, -1) == (-cfg.REMOTO_VEL_MAX, -cfg.REMOTO_VEL_MAX)             # tudo para baixo: ré
    e, d = calcular_pwm_analogico(1, 0); assert e > 0 > d                                           # direita: gira à direita no lugar
    e, d = calcular_pwm_analogico(-1, 0); assert d > 0 > e
    e, d = calcular_pwm_analogico(0.4, 0.8); assert e > d > 0                                       # frente-direita: roda esquerda mais rápida
    e, d = calcular_pwm_analogico(-0.4, 0.8); assert d > e > 0
    e, d = calcular_pwm_analogico(0, 0.5); assert 0 < e == d < cfg.REMOTO_VEL_MAX                   # mais perto do centro: mais devagar
    for x in (-1, -0.6, 0, 0.6, 1):
        for y in (-1, -0.6, 0, 0.6, 1):
            assert max(abs(v) for v in calcular_pwm_analogico(x, y)) <= min(cfg.VEL_MAX, cfg.REMOTO_VEL_MAX)


def test_protocolo_robokit_eletrogate():
    assert _tipos(b"F192T0D0E0\n") == [("eletrogate", (192, 0, 0, 0), True)]
    assert _tipos(b"F0T192D0E0\n")[0][1] == (0, 192, 0, 0)
    assert _tipos(b"F0T0D192E0\n")[0][1] == (0, 0, 192, 0)
    assert _tipos(b"F0T0D0E192\n")[0][1] == (0, 0, 0, 192)
    assert _tipos(b"F192T0D128E0\n")[0][1] == (192, 0, 128, 0)  # diagonal por mistura dos eixos
    assert _tipos(b"F0T0D0E0\n")[0][1] == (0, 0, 0, 0)
    i = InterpretadorRemoto()
    assert i.alimentar(b"F192T0D") == []  # pacote parcial: não vira F + comandos avulsos
    assert _tipos(b"168E0\n", i) == [("eletrogate", (192, 0, 168, 0), True)]
    assert _tipos(b"F999T0D0E0\n")[0][0] == "ignorar"
    i = InterpretadorRemoto()
    assert _tipos(b"F0T0D0E0\n", i)[0][0] == "eletrogate"
    assert _tipos(b"F\nT\nE\nD\n", i) == [
        ("eletrogate_direcao", "F", True), ("eletrogate_direcao", "T", True),
        ("eletrogate_direcao", "E", True), ("eletrogate_direcao", "D", True),
    ]
    assert _tipos(b"D\n") == [("parar", None, True)]  # D continua sendo parar no protocolo RC


def test_pwm_eletrogate_todas_direcoes_e_intensidade():
    teto = min(cfg.VEL_MAX, cfg.REMOTO_VEL_MAX)
    escala = teto / 255.0
    assert calcular_pwm_eletrogate(192, 0, 0, 0) == (round(192 * escala),) * 2
    assert calcular_pwm_eletrogate(0, 192, 0, 0) == (-round(192 * escala),) * 2
    esq, dir_ = calcular_pwm_eletrogate(0, 0, 192, 0)
    assert esq > 0 > dir_
    esq, dir_ = calcular_pwm_eletrogate(0, 0, 0, 192)
    assert dir_ > 0 > esq
    e1, d1 = calcular_pwm_eletrogate(64, 0, 0, 0)
    e2, d2 = calcular_pwm_eletrogate(192, 0, 0, 0)
    assert 0 < e1 == d1 < e2 == d2 <= teto
    assert calcular_pwm_eletrogate(0, 0, 0, 0) == (0, 0)


# ----------------------------------------------------------------------------- controle MANUAL
def _controle(est, mot):
    parar = threading.Event(); t = ThreadControle(est, mot, parar); t.start()
    return parar, t


def test_manual_anda_renova_e_expira():
    antigo, cfg.REMOTO_TIMEOUT_S = cfg.REMOTO_TIMEOUT_S, 0.4
    try:
        est, mot = EstadoRobo(), MotorFalso(); parar, t = _controle(est, mot)
        aplicar_movimento_manual(est, mot, 100, 100)
        time.sleep(0.25); assert est.modo is Modo.MANUAL and mot.ultimo() == (100, 100)
        for _ in range(4):                                                # renovando, passa do prazo sem parar
            aplicar_movimento_manual(est, mot, 100, 100); time.sleep(0.2)
        assert est.modo is Modo.MANUAL and mot.ultimo() == (100, 100)
        time.sleep(0.8)                                                   # sem renovar: expira
        assert est.modo is Modo.PARADO and mot.ultimo() == (0, 0)
        parar.set(); t.join(2)
    finally:
        cfg.REMOTO_TIMEOUT_S = antigo


def test_manual_pare_de_voz_e_novo_modo_vencem():
    est, mot = EstadoRobo(), MotorFalso(); parar, t = _controle(est, mot)
    aplicar_movimento_manual(est, mot, 120, 120); time.sleep(0.15)
    aplicar_comando(est, mot, "pare")                                     # voz corta
    time.sleep(0.2)
    assert est.modo is Modo.PARADO and est.ler_manual() is None and mot.ultimo() == (0, 0)
    aplicar_movimento_manual(est, mot, 120, 120); time.sleep(0.1)
    aplicar_comando(est, mot, "siga")                                     # voz troca de modo: o manual some
    assert est.modo is Modo.SEGUINDO and est.ler_manual() is None
    parar.set(); t.join(2)


def test_manual_obstaculo_so_barra_a_frente():
    est, mot = EstadoRobo(), MotorFalso(); mot.obst = True; parar, t = _controle(est, mot)
    aplicar_movimento_manual(est, mot, 100, 100); time.sleep(0.2)
    assert mot.ultimo() == (0, 0)                                         # frente bloqueada
    aplicar_movimento_manual(est, mot, -100, -100); time.sleep(0.2)
    assert mot.ultimo() == (-100, -100)                                   # ré livre
    aplicar_movimento_manual(est, mot, -80, 80); time.sleep(0.2)
    assert mot.ultimo() == (0, 0)                                         # giro com uma roda avançando também bloqueia
    parar.set(); t.join(2)


# ----------------------------------------------------------------------------- sessão do celular (socketpair)
def _sessao():
    est, mot = EstadoRobo(), MotorFalso()
    a, b = socket.socketpair()
    s = SessaoRemota(a, "AA:BB:CC:DD:EE:FF", est, mot); s.iniciar()
    b.settimeout(2.0)
    return est, mot, s, b


def test_botao_mantem_apos_prazo_e_para_ao_soltar():
    est, mot, s, b = _sessao()
    parar, t = _controle(est, mot)
    try:
        b.send(b"F")
        assert esperar(lambda: est.modo is Modo.MANUAL)
        with est.lock:
            e, d, ts, validade = est.ler_manual()
            est._manual = (e, d, ts - cfg.REMOTO_TIMEOUT_S - 10, validade)
        time.sleep(0.15)
        assert est.modo is Modo.MANUAL and mot.ultimo() == calcular_pwm("frente", cfg.REMOTO_VEL_INICIAL)
        b.send(b"8")
        assert esperar(lambda: mot.ultimo() == calcular_pwm("frente", 8))
        assert est.ler_manual()[3] == float("inf")
        b.send(b"S")
        assert esperar(lambda: est.modo is Modo.PARADO and mot.ultimo() == (0, 0))
    finally:
        parar.set(); t.join(2); s.fechar(); b.close()


def test_sessao_botoes_velocidade_e_parar():
    est, mot, s, b = _sessao()
    b.send(b"5"); b.send(b"F")
    assert esperar(lambda: mot.ultimo() == calcular_pwm("frente", 5)) and est.modo is Modo.MANUAL
    b.send(b"8")                                                          # muda a velocidade andando: reaplica
    assert esperar(lambda: mot.ultimo() == calcular_pwm("frente", 8))
    b.send(b"S")
    assert esperar(lambda: mot.ultimo() == (0, 0) and est.modo is Modo.PARADO)
    s.fechar()


def test_sessao_responde_so_ao_que_veio_com_enter():
    est, mot, s, b = _sessao()
    b.send(b"F"); time.sleep(0.2)
    b.settimeout(0.3)
    try:
        b.recv(256); raise AssertionError("botão de app RC não deveria receber resposta")
    except socket.timeout:
        pass
    b.settimeout(2.0); b.send(b"status\n")
    assert b"modo=MANUAL" in b.recv(256)
    b.send(b"xis\n"); assert b"ERRO" in b.recv(256)
    s.fechar()


def test_sessao_desconectar_andando_para_o_carrinho():
    est, mot, s, b = _sessao()
    b.send(b"F"); assert esperar(lambda: est.modo is Modo.MANUAL)
    b.close()                                                             # celular sumiu
    assert esperar(lambda: est.modo is Modo.PARADO and mot.ultimo() == (0, 0))


def test_desconectar_nao_atrapalha_outro_modo():
    est, mot, s, b = _sessao()
    est.definir_modo(Modo.SEGUINDO)                                       # voz mandou seguir a linha
    b.close(); time.sleep(0.4)
    assert est.modo is Modo.SEGUINDO


def test_sessao_bluedot_toque_move_solta_para_e_responde_config():
    est, mot, s, b = _sessao()
    b.send(b"3,2,Blue Dot Android\n")
    assert b.recv(256).decode().strip() == CONFIG_BLUEDOT                 # configura o botão como a biblioteca bluedot
    b.send(b"1,0,0,0.0,1.0\n")                                            # apertou no topo
    assert esperar(lambda: mot.ultimo() == calcular_pwm_analogico(0.0, 1.0) and est.modo is Modo.MANUAL)
    b.send(b"2,0,0,1.0,0.0\n")                                            # arrastou para a direita
    assert esperar(lambda: mot.ultimo() == calcular_pwm_analogico(1.0, 0.0))
    b.send(b"0,0,0,1.0,0.0\n")                                            # soltou
    assert esperar(lambda: mot.ultimo() == (0, 0) and est.modo is Modo.PARADO)
    s.fechar()


def test_sessao_eletrogate_joystick_e_parada_central():
    est, mot, s, b = _sessao()
    b.send(b"F192T0D0E0\n")
    assert esperar(lambda: mot.ultimo() == calcular_pwm_eletrogate(192, 0, 0, 0))
    b.send(b"F0T0D192E0\n")
    assert esperar(lambda: mot.ultimo() == calcular_pwm_eletrogate(0, 0, 192, 0))
    b.send(b"F0T0D0E0\n")
    assert esperar(lambda: mot.ultimo() == (0, 0) and est.modo is Modo.PARADO)
    s.fechar()


def test_eletrogate_silencio_do_joystick_expira_sem_desconectar():
    antigo, cfg.REMOTO_ELETROGATE_TIMEOUT_S = cfg.REMOTO_ELETROGATE_TIMEOUT_S, 0.2
    try:
        est, mot, s, b = _sessao()
        parar, t = _controle(est, mot)
        b.send(b"F192T0D0E0\n")
        assert esperar(lambda: mot.ultimo() == calcular_pwm_eletrogate(192, 0, 0, 0))
        assert esperar(lambda: est.modo is Modo.PARADO and mot.ultimo() == (0, 0))
        assert b.fileno() >= 0  # timeout de joystick não significa desconexão Bluetooth
        parar.set(); t.join(2); s.fechar()
    finally:
        cfg.REMOTO_ELETROGATE_TIMEOUT_S = antigo


def test_bluedot_conexao_cai_com_o_dedo_na_tela_para_pelo_prazo_curto():
    antigo, cfg.REMOTO_BLUEDOT_TIMEOUT_S = cfg.REMOTO_BLUEDOT_TIMEOUT_S, 0.4
    try:
        est, mot, s, b = _sessao()
        parar, t = _controle(est, mot)
        b.send(b"1,0,0,0.0,1.0\n")                                        # dedo apertado, e ... silêncio (enlace caiu sem fechar)
        assert esperar(lambda: mot.ultimo() == calcular_pwm_analogico(0.0, 1.0))
        assert esperar(lambda: est.modo is Modo.PARADO and mot.ultimo() == (0, 0), t=3.0)
        parar.set(); t.join(2); s.fechar()
    finally:
        cfg.REMOTO_BLUEDOT_TIMEOUT_S = antigo


def test_mac_do_caminho():
    assert mac_do_caminho("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF") == "AA:BB:CC:DD:EE:FF"


# ----------------------------------------------------------------------------- servidor com BlueZ falso
def _assinar(fn, **anot):
    fn.__annotations__ = anot
    return fn


def test_servidor_com_bluez_falso():
    if not shutil.which("dbus-daemon"):
        print("PULADO test_servidor_com_bluez_falso: dbus-daemon não instalado"); return
    if importlib.util.find_spec("dbus_fast") is None:
        print("PULADO test_servidor_com_bluez_falso: pip install dbus-fast"); return
    from dbus_fast.aio import MessageBus
    from dbus_fast.service import ServiceInterface, dbus_property, method

    daemon = subprocess.Popen(["dbus-daemon", "--session", "--print-address=1", "--nofork"],
                              stdout=subprocess.PIPE, text=True)
    addr = daemon.stdout.readline().strip()
    try:
        class GerenteFalso(ServiceInterface):
            def __init__(self):
                super().__init__("org.bluez.ProfileManager1")
                self.registros, self.removidos = [], []

            def _reg(self, profile, uuid, options):
                self.registros.append((profile, uuid, {k: v.value for k, v in options.items()}))

            def _unreg(self, profile):
                self.removidos.append(profile)

            _reg.__annotations__ = {"profile": "o", "uuid": "s", "options": "a{sv}"}
            _unreg.__annotations__ = {"profile": "o"}
            RegisterProfile = method(name="RegisterProfile")(_reg)
            UnregisterProfile = method(name="UnregisterProfile")(_unreg)

        class AdaptadorFalso(ServiceInterface):
            def __init__(self):
                super().__init__("org.bluez.Adapter1")
                self.ligado = False

            @dbus_property()
            def Powered(self) -> "b":
                return self.ligado

            @Powered.setter
            def Powered_setter(self, v: "b"):
                self.ligado = v

        async def cenario():
            loop = asyncio.get_running_loop()
            bus = await MessageBus(bus_address=addr, negotiate_unix_fd=True).connect()
            gerente = GerenteFalso()
            bus.export("/org/bluez", gerente)
            adaptador = AdaptadorFalso(); bus.export("/org/bluez/hci0", adaptador)
            await bus.request_name("org.bluez")
            remetente = {}

            def espiao(msg):
                if getattr(msg, "member", None) == "RegisterProfile":
                    remetente["nome"] = msg.sender
            bus.add_message_handler(espiao)

            est, mot, parar = EstadoRobo(), MotorFalso(), threading.Event()
            tb = ThreadBluetooth(est, mot, parar, bus_address=addr); tb.start()
            assert await loop.run_in_executor(None, tb.registrado.wait, 5.0), "o servidor não registrou o perfil"
            (caminho, uuid, opts), = gerente.registros
            assert uuid == "00001101-0000-1000-8000-00805f9b34fb" and opts["Role"] == "server"
            assert adaptador.ligado is True, "o servidor devia ligar o adaptador Bluetooth"
            assert opts["RequireAuthentication"] is True and opts["Name"] == cfg.REMOTO_NOME

            async def conectar(mac_path):
                """Faz o papel do BlueZ: entrega ao perfil um canal (um lado de um socketpair) de um 'celular'."""
                intro = await bus.introspect(remetente["nome"], caminho)
                perfil = bus.get_proxy_object(remetente["nome"], caminho, intro).get_interface("org.bluez.Profile1")
                dono, celular = socket.socketpair()
                await perfil.call_new_connection(mac_path, dono.fileno(), {})
                dono.close()
                celular.settimeout(2.0)
                return celular

            # 1) celular normal: botões movem, S para, resposta a texto
            cel = await conectar("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF")
            cel.send(b"6F")
            assert await loop.run_in_executor(None, esperar, lambda: mot.ultimo() == calcular_pwm("frente", 6))
            cel.send(b"S")
            assert await loop.run_in_executor(None, esperar, lambda: est.modo is Modo.PARADO)
            cel.send(b"status\n")
            assert b"modo=PARADO" in await loop.run_in_executor(None, cel.recv, 256)

            # 2) nova conexão derruba a anterior (e, andando, o carrinho para)
            cel.send(b"B")
            assert await loop.run_in_executor(None, esperar, lambda: est.modo is Modo.MANUAL)
            cel2 = await conectar("/org/bluez/hci0/dev_11_22_33_44_55_66")
            assert await loop.run_in_executor(None, esperar, lambda: est.modo is Modo.PARADO and mot.ultimo() == (0, 0))
            assert tb.sessao_atual().mac == "11:22:33:44:55:66"
            cel2.close()

            # 3) lista de permitidos: outro celular é recusado
            cfg.REMOTO_MACS_PERMITIDOS = ["11:22:33:44:55:66"]
            intruso = await conectar("/org/bluez/hci0/dev_DE_AD_BE_EF_00_01")
            assert await loop.run_in_executor(None, intruso.recv, 256) == b""      # EOF: fd fechado sem atender
            cfg.REMOTO_MACS_PERMITIDOS = []

            # 4) encerrar o robô cancela o registro e fecha tudo
            parar.set()
            await loop.run_in_executor(None, tb.join, 5.0)
            assert not tb.is_alive() and gerente.removidos == [caminho]
            bus.disconnect()

        asyncio.run(cenario())
    finally:
        daemon.terminate(); daemon.wait(3)


def test_sem_bluez_o_servidor_nao_derruba_nada():
    est, mot, parar = EstadoRobo(), MotorFalso(), threading.Event()
    tb = ThreadBluetooth(est, mot, parar, bus_address="unix:path=/nao/existe/mesmo"); tb.start()
    time.sleep(0.8); assert tb.is_alive() and not tb.registrado.is_set()     # só tenta de novo
    parar.set(); tb.join(3); assert not tb.is_alive()


if __name__ == "__main__":
    falhou = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("ok   ", n)
            except Exception:
                import traceback; falhou += 1; print("FALHA", n); traceback.print_exc()
    print("tudo ok" if not falhou else f"{falhou} falhas"); sys.exit(1 if falhou else 0)
