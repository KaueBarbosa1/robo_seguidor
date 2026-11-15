"""Servidor Bluetooth serial (SPP / RFCOMM) para o celular Android controlar o carrinho.

Como funciona: esta thread registra no BlueZ (o serviço Bluetooth do Linux, via D-Bus) um "perfil" de porta serial com o
UUID padrão do SPP. Quando um celular JÁ PAREADO abre o serviço serial, o BlueZ entrega aqui o descritor do canal
(NewConnection) e a sessão passa a ler os comandos (remoto/comandos.py) e a aplicá-los no controle
(controle.aplicar_movimento_manual / aplicar_comando). Nada de PyBluez; só Python padrão + a biblioteca `dbus-fast`.

Segurança:
  * só celular pareado (BlueZ exige autenticação) e, se REMOTO_MACS_PERMITIDOS não estiver vazio, só os da lista;
  * texto expira em REMOTO_TIMEOUT_S; botoes podem manter ate S com REMOTO_BOTOES_ATE_SOLTAR;
  * conexão fechada/perdida com o carrinho em MANUAL -> para;
  * uma conexão por vez: a nova derruba a antiga;
  * se o Bluetooth/`dbus-fast` não existir, esta thread só avisa e o resto do robô segue (voz etc.).
"""
import asyncio
import importlib.util
import logging
import os
import socket
import threading

import config as cfg
from controle import aplicar_comando, aplicar_movimento_manual
from estado import EstadoRobo, Modo
from remoto.comandos import (AJUDA, CONFIG_BLUEDOT, InterpretadorRemoto, calcular_pwm,
                             calcular_pwm_analogico, calcular_pwm_eletrogate)

log = logging.getLogger("remoto")

UUID_SPP = "00001101-0000-1000-8000-00805f9b34fb"
CAMINHO_PERFIL = "/robo/spp"


def mac_do_caminho(caminho: str) -> str:
    """'/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF' -> 'AA:BB:CC:DD:EE:FF'."""
    nome = caminho.rsplit("/", 1)[-1]
    if nome.startswith("dev_"):
        nome = nome[4:]
    return nome.replace("_", ":").upper()


class SessaoRemota:
    """Uma conexão de celular: lê bytes, interpreta, aplica no robô e responde ao que veio com Enter."""

    def __init__(self, sock: socket.socket, mac: str, estado: EstadoRobo, motor):
        self._sock, self.mac, self._estado, self._motor = sock, mac, estado, motor
        self._interp = InterpretadorRemoto()
        self.nivel = max(0, min(10, int(cfg.REMOTO_VEL_INICIAL)))
        self._direcao: str | None = None
        self._fim = threading.Event()
        self.thread = threading.Thread(target=self._rodar, name=f"remoto-{mac}", daemon=True)

    def iniciar(self) -> None:
        self.thread.start()

    def fechar(self) -> None:
        self._fim.set()
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass

    def _enviar(self, texto: str) -> None:
        self._enviar_linha(texto, "\r\n")

    def _enviar_linha(self, texto: str, fim: str = "\n") -> None:
        try:
            self._sock.sendall((texto + fim).encode("utf-8"))
        except OSError:
            pass

    def _rodar(self) -> None:
        log.info("Celular conectado: %s", self.mac)       # sem saudação: o app Blue Dot não espera texto solto do servidor
        self._sock.settimeout(0.5)
        try:
            while not self._fim.is_set():
                try:
                    dados = self._sock.recv(256)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not dados:                                  # o celular fechou a conexão
                    break
                if cfg.REMOTO_LOG_BYTES:
                    legivel = "".join(chr(b) if 32 <= b < 127 else "." for b in dados)
                    log.info("Bluetooth RX %s bytes hex=%s ascii=%r", len(dados), dados.hex(" "), legivel)
                for cmd in self._interp.alimentar(dados):
                    self._tratar(cmd)
        finally:
            self._fim.set()
            with self._estado.lock:
                buzinar = getattr(self._motor, "buzinar", None)
                if buzinar:
                    buzinar(False)
                if self._estado.modo is Modo.MANUAL:           # conexão acabou andando: para
                    aplicar_comando(self._estado, self._motor, "pare")
                    log.warning("Celular %s desconectou com o carrinho em movimento: parado.", self.mac)
            try:
                self._sock.close()
            except OSError:
                pass
            log.info("Celular desconectado: %s", self.mac)

    def _responder(self, cmd, texto: str) -> None:
        if cmd.de_linha:                                       # botões de apps RC (sem Enter) não recebem eco
            self._enviar(texto)

    def _tratar(self, cmd) -> None:
        if cmd.tipo == "mover":
            self._direcao = cmd.valor
            esq, dir_ = calcular_pwm(cmd.valor, self.nivel)
            validade = float("inf") if cfg.REMOTO_BOTOES_ATE_SOLTAR and not cmd.de_linha else None
            aplicar_movimento_manual(self._estado, self._motor, esq, dir_, validade_s=validade)
            self._responder(cmd, f"OK {cmd.valor} vel={self.nivel}")
        elif cmd.tipo == "parar":
            self._direcao = None
            aplicar_comando(self._estado, self._motor, "pare")
            self._responder(cmd, "OK parado")
        elif cmd.tipo == "buzina_pulso":
            buzinar = getattr(self._motor, "buzinar", None)
            if buzinar:
                # O app manda somente Y: rearmar antes de cada toque permite
                # repetir apos o limite local sem exigir byte de soltar.
                buzinar(False)
                buzinar(True)
        elif cmd.tipo == "buzina":
            buzinar = getattr(self._motor, "buzinar", None)
            if buzinar:
                buzinar(bool(cmd.valor))
                self._responder(cmd, "OK comando de buzina enviado")
            else:
                self._responder(cmd, "ERRO buzina indisponivel")
        elif cmd.tipo == "velocidade":
            self.nivel = max(0, min(10, int(cmd.valor)))
            with self._estado.lock:
                if self._direcao and self._estado.modo is Modo.MANUAL:      # já andando: aplica a nova velocidade
                    esq, dir_ = calcular_pwm(self._direcao, self.nivel)
                    manual = self._estado.ler_manual()
                    aplicar_movimento_manual(self._estado, self._motor, esq, dir_,
                                             validade_s=manual[3] if manual else None)
            self._responder(cmd, f"OK vel={self.nivel}")
        elif cmd.tipo == "status":
            self._responder(cmd, f"modo={self._estado.modo.name} vel={self.nivel} timeout={cfg.REMOTO_TIMEOUT_S}s")
        elif cmd.tipo == "ajuda":
            self._responder(cmd, AJUDA)
        elif cmd.tipo == "dot_protocolo":
            versao, nome = cmd.valor
            log.info("App Blue Dot conectado (%s, protocolo %s).", nome or "?", versao)
            self._enviar_linha(CONFIG_BLUEDOT)                  # como a biblioteca bluedot: cor/tamanho do botão
        elif cmd.tipo == "dot_toque":
            esq, dir_ = calcular_pwm_analogico(*cmd.valor)
            aplicar_movimento_manual(self._estado, self._motor, esq, dir_, validade_s=cfg.REMOTO_BLUEDOT_TIMEOUT_S)
        elif cmd.tipo == "dot_soltar":
            self._direcao = None
            aplicar_comando(self._estado, self._motor, "pare")
        elif cmd.tipo == "eletrogate":
            esq, dir_ = calcular_pwm_eletrogate(*cmd.valor)
            if esq == 0 and dir_ == 0:
                self._direcao = None
                aplicar_comando(self._estado, self._motor, "pare")
            else:
                aplicar_movimento_manual(self._estado, self._motor, esq, dir_,
                                         validade_s=cfg.REMOTO_ELETROGATE_TIMEOUT_S)
        elif cmd.tipo == "eletrogate_direcao":
            # A captura real do app nesta instalação mostrou F/T/E/D avulsos após o pacote de
            # estado F0T0D0E0. Neste robô, o F recebido ao empurrar para frente acionava a ré;
            # por isso a polaridade longitudinal fica invertida apenas para esse modo do app.
            direcao = {"F": "tras", "T": "frente", "E": "esq", "D": "dir"}[cmd.valor]
            esq, dir_ = calcular_pwm(direcao, self.nivel)
            aplicar_movimento_manual(self._estado, self._motor, esq, dir_,
                                     validade_s=cfg.REMOTO_ELETROGATE_TIMEOUT_S)
        elif cmd.tipo == "desconhecido":
            self._responder(cmd, f"ERRO comando desconhecido: {cmd.valor!r}. Envie 'ajuda'.")


class ThreadBluetooth(threading.Thread):
    """Registra o perfil serial no BlueZ e atende os celulares. Falhas aqui NÃO derrubam o robô."""

    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event, bus_address: str | None = None):
        super().__init__(name="bluetooth", daemon=True)
        self._estado, self._motor, self._parar = estado, motor, parar
        self._bus_address = bus_address            # None = barramento do sistema (testes passam um endereço privado)
        self._sessao: SessaoRemota | None = None
        self._lock = threading.Lock()
        self.registrado = threading.Event()

    # ------------------------------------------------------------ sessões
    def _nova_conexao(self, caminho_dispositivo: str, fd: int) -> None:
        mac = mac_do_caminho(caminho_dispositivo)
        permitidos = {m.upper() for m in cfg.REMOTO_MACS_PERMITIDOS}
        if permitidos and mac not in permitidos:
            log.warning("Conexão de %s recusada (fora de REMOTO_MACS_PERMITIDOS).", mac)
            os.close(fd)
            return
        sock = socket.socket(fileno=fd)
        with self._lock:
            antiga, self._sessao = self._sessao, SessaoRemota(sock, mac, self._estado, self._motor)
            nova = self._sessao
        if antiga is not None:
            log.info("Nova conexão de %s: a anterior (%s) foi encerrada.", mac, antiga.mac)
            antiga.fechar()
        nova.iniciar()

    def _desconectar(self, caminho_dispositivo: str) -> None:
        mac = mac_do_caminho(caminho_dispositivo)
        with self._lock:
            s = self._sessao
        if s is not None and s.mac == mac:
            s.fechar()

    def sessao_atual(self) -> SessaoRemota | None:
        with self._lock:
            return self._sessao

    # ------------------------------------------------------------ D-Bus
    def run(self) -> None:
        if importlib.util.find_spec("dbus_fast") is None:
            log.error("Controle por Bluetooth DESLIGADO: falta a biblioteca dbus-fast (pip install dbus-fast). "
                      "O resto do robô continua normalmente.")
            return
        while not self._parar.is_set():
            try:
                asyncio.run(self._servir())
            except Exception as e:
                log.error("Bluetooth indisponível (%s: %s). O bluetoothd está ativo? (systemctl status bluetooth). "
                          "Nova tentativa em 5 s.", type(e).__name__, e)
            self.registrado.clear()
            self._parar.wait(5.0)
        with self._lock:
            s = self._sessao
        if s is not None:
            s.fechar()

    async def _servir(self) -> None:
        from dbus_fast import BusType, Variant
        from dbus_fast.aio import MessageBus
        from dbus_fast.service import ServiceInterface, method

        servidor = self

        class Perfil(ServiceInterface):
            def __init__(self):
                super().__init__("org.bluez.Profile1")

            # O dbus-fast lê a assinatura D-Bus das anotações ("o" = caminho de objeto, "h" = descritor de arquivo,
            # "a{sv}" = dicionário): por isso elas são postas à mão antes do decorador.
            def _release(self):
                log.info("BlueZ liberou o perfil serial.")

            def _new_connection(self, device, fd, fd_properties):
                try:
                    servidor._nova_conexao(device, int(fd))
                except Exception:
                    log.exception("Falha ao aceitar conexão Bluetooth")

            def _request_disconnection(self, device):
                servidor._desconectar(device)

            _new_connection.__annotations__ = {"device": "o", "fd": "h", "fd_properties": "a{sv}"}
            _request_disconnection.__annotations__ = {"device": "o"}
            Release = method(name="Release")(_release)
            NewConnection = method(name="NewConnection")(_new_connection)
            RequestDisconnection = method(name="RequestDisconnection")(_request_disconnection)

        kw = {"bus_address": self._bus_address} if self._bus_address else {"bus_type": BusType.SYSTEM}
        bus = await MessageBus(negotiate_unix_fd=True, **kw).connect()
        try:
            bus.export(CAMINHO_PERFIL, Perfil())
            intro = await bus.introspect("org.bluez", "/org/bluez")
            gerente = bus.get_proxy_object("org.bluez", "/org/bluez", intro).get_interface("org.bluez.ProfileManager1")
            await gerente.call_register_profile(CAMINHO_PERFIL, UUID_SPP, {
                "Name": Variant("s", cfg.REMOTO_NOME),
                "Role": Variant("s", "server"),
                "RequireAuthentication": Variant("b", True),     # só celular pareado
                "RequireAuthorization": Variant("b", False),     # sem pergunta extra a cada conexão
            })
            await self._ligar_adaptador(bus)
            dono = await self._dono_bluez(bus)
            log.info("Controle por Bluetooth pronto: pareie o celular e abra o serviço serial '%s' (docs/07).", cfg.REMOTO_NOME)
            self.registrado.set()
            n = 0
            while not self._parar.is_set():
                await asyncio.sleep(0.2)
                n += 1
                if not bus.connected:
                    raise ConnectionError("conexão com o D-Bus caiu")
                if n % 25 == 0 and await self._dono_bluez(bus) != dono:
                    raise ConnectionError("o bluetoothd reiniciou: registrando o perfil de novo")
            try:
                await gerente.call_unregister_profile(CAMINHO_PERFIL)
            except Exception:
                pass
        finally:
            bus.disconnect()

    @staticmethod
    async def _ligar_adaptador(bus) -> None:
        """Melhor esforço (como a biblioteca bluedot faz): garante o adaptador ligado. Nunca derruba o servidor."""
        from dbus_fast import Variant
        try:
            caminho = f"/org/bluez/{cfg.REMOTO_ADAPTADOR}"
            intro = await bus.introspect("org.bluez", caminho)
            props = bus.get_proxy_object("org.bluez", caminho, intro).get_interface("org.freedesktop.DBus.Properties")
            if not (await props.call_get("org.bluez.Adapter1", "Powered")).value:
                await props.call_set("org.bluez.Adapter1", "Powered", Variant("b", True))
                log.info("Adaptador Bluetooth %s ligado.", cfg.REMOTO_ADAPTADOR)
        except Exception as e:
            log.warning("Não consegui conferir/ligar o adaptador %s (%s: %s). Se o celular não achar a Pi: "
                        "rfkill list; sudo rfkill unblock bluetooth; bluetoothctl power on",
                        cfg.REMOTO_ADAPTADOR, type(e).__name__, e)

    @staticmethod
    async def _dono_bluez(bus) -> str:
        intro = await bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        dbus = bus.get_proxy_object("org.freedesktop.DBus", "/org/freedesktop/DBus", intro).get_interface("org.freedesktop.DBus")
        return await dbus.call_get_name_owner("org.bluez")
