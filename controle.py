"""Controle: o ÚNICO lugar que decide o que o robô faz e escreve nos motores.

Hierarquia:
  1. Voz (comando) -> aplicar_comando(): muda o modo e, no "pare", corta os motores na hora.
  2. Celular (Bluetooth) -> aplicar_movimento_manual(): modo MANUAL, vale só enquanto chegam comandos
     (REMOTO_TIMEOUT_S); "parar" do celular e "pare" de voz cortam os motores na hora.
  3. Visão (erro)  -> ThreadControle: só vira comando de motor quando o modo é SEGUINDO.

`estado.lock` é segurado durante "ler modo + enviar ao Arduino", então um "pare" da voz
nunca pode ser desfeito por um comando de linha que já estava a caminho.
"""
import logging
import threading
import time

import config as cfg
from estado import EstadoRobo, Modo

log = logging.getLogger("controle")


def aplicar_comando(estado: EstadoRobo, motor, comando: str) -> None:
    """Chamado pela thread de voz. Prioridade absoluta sobre a visão."""
    with estado.lock:
        if comando in {"pare", "esquerda", "direita", "voltar"}:
            centrar = getattr(motor, "configurar_servo", None)
            if centrar:
                motor.parar()
                centrar(False)
        if comando != "siga":
            estado._partida_ate = 0.0
            getattr(motor, "avisar", lambda tipo: None)(0)
        if comando == "pare":
            estado.definir_modo(Modo.PARADO)
            motor.parar(repetir=3)                          # imediato, sem esperar o ciclo de controle
        elif comando == "siga":
            if estado.modo is not Modo.SEGUINDO:
                motor.parar()
                estado._partida_ate = time.monotonic() + 0.6
                getattr(motor, "avisar", lambda tipo: None)(1)
            estado.definir_modo(Modo.SEGUINDO)
        elif comando == "esquerda":
            estado.definir_modo(Modo.GIRO_ESQ, cfg.TEMPO_GIRO_S)
        elif comando == "direita":
            estado.definir_modo(Modo.GIRO_DIR, cfg.TEMPO_GIRO_S)
        elif comando == "voltar":
            estado.definir_modo(Modo.RE, cfg.TEMPO_RE_S)
        else:
            log.warning("Comando desconhecido: %s", comando)


def calcular_motores(erro: float, derivada: float) -> tuple[int, int]:
    """Erro (-1..1) -> (PWM esquerdo, PWM direito). Erro positivo = linha à direita = virar à direita."""
    correcao = cfg.KP * erro + cfg.KD * derivada
    esq = cfg.VEL_BASE + correcao
    dir_ = cfg.VEL_BASE - correcao
    esq = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, esq))
    dir_ = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, dir_))
    return int(esq), int(dir_)


def filtrar_derivada(anterior: float, erro: float, erro_ant: float, dt: float, alfa: float) -> float:
    """Derivada do erro com filtro exponencial (alfa=1: sem filtro). Câmera rápida (ex.: 30 quadros/s) amplifica o ruído da
    posição da linha; o filtro evita que o termo D vire tremor nos motores."""
    bruta = (erro - erro_ant) / dt
    return (1.0 - alfa) * anterior + alfa * bruta


def aplicar_movimento_manual(estado: EstadoRobo, motor, esq: int, dir_: int, validade_s: float | None = None) -> None:
    """Chamado pela thread do Bluetooth: anda com estes PWM (-255..255) até o prazo sem renovar
    (validade_s; padrão REMOTO_TIMEOUT_S)."""
    esq = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(esq)))
    dir_ = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(dir_)))
    with estado.lock:
        centrar = getattr(motor, "configurar_servo", None)
        if centrar:
            centrar(False)
        estado.definir_manual(esq, dir_, validade_s)
        motor.motores(esq, dir_)


class ThreadControle(threading.Thread):
    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event):
        super().__init__(name="controle", daemon=True)
        self._estado = estado
        self._motor = motor
        self._parar = parar
        self._obst_ant = False
        self._inspecao_inicio = None

    def run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception("Thread de controle caiu")
            self._parar.set()
        finally:
            with self._estado.lock:
                self._cancelar_inspecao()
                getattr(self._motor, "avisar", lambda tipo: None)(0)

    def _obstaculo(self) -> bool:
        """Cópia de segurança na Pi; a barreira autoritativa e imediata também existe no Arduino."""
        if not cfg.OBSTACULO_ATIVO:
            return False
        sensores = getattr(self._motor, "sensores", lambda: None)()
        if sensores is None or time.monotonic() - sensores.timestamp > cfg.SENSOR_TIMEOUT_S:
            return True
        if sensores.falha_sensor or sensores.avanco_bloqueado:
            return True
        checar = getattr(self._motor, "obstaculo", None)
        obst = bool(checar and checar(cfg.OBSTACULO_DIST_CM, cfg.OBSTACULO_LEITURAS))
        if obst != self._obst_ant:
            log.warning("Obstáculo à frente: parando" if obst else "Caminho livre")
            self._obst_ant = obst
        return obst

    def _cancelar_inspecao(self) -> None:
        if self._inspecao_inicio is not None:
            self._motor.parar()
            self._motor.configurar_servo(False)
            self._inspecao_inicio = None

    def _inspecionar_obstaculo(self, agora: float) -> bool:
        """Executado sob estado.lock. Mantem parada; nunca escolhe movimento lateral."""
        if not (cfg.OBSTACULO_ATIVO and cfg.INSPECAO_OBSTACULO_ATIVA):
            self._cancelar_inspecao()
            return False
        if not callable(getattr(self._motor, "inspecionar_obstaculo", None)):
            return False
        if self._inspecao_inicio is None:
            s = self._motor.sensores()
            if (s is None or agora - s.timestamp > cfg.SENSOR_TIMEOUT_S or
                    s.falha_sensor or not s.avanco_bloqueado or
                    not getattr(s, "obstaculo_confirmado", False) or
                    s.distancia_cm is None or s.distancia_cm >= cfg.OBSTACULO_DIST_CM):
                return False
            self._inspecao_inicio = agora
            log.warning("Obstaculo confirmado: parando antes da inspecao em tres posicoes")
        self._motor.parar()
        if agora - self._inspecao_inicio > cfg.INSPECAO_TIMEOUT_S:
            log.error("Inspecao sem conclusao no prazo: permanecendo PARADO")
            self._estado.definir_modo(Modo.PARADO)
            self._cancelar_inspecao()
            return True
        if agora - self._inspecao_inicio < cfg.INSPECAO_REPOUSO_S:
            return True
        self._motor.inspecionar_obstaculo()
        status = self._motor.status_servo()
        amostras = self._motor.leituras_inspecao()
        recentes = (len(amostras) == 3 and
                    len({a.rodada for a in amostras}) == 1 and
                    {a.angulo_nominal for a in amostras} == {45, 90, 135} and
                    all(a.timestamp >= self._inspecao_inicio for a in amostras))
        if (status and status.ativo and status.inspecao and status.concluida and
                0 <= agora - status.timestamp <= cfg.SENSOR_TIMEOUT_S and recentes):
            for a in sorted(amostras, key=lambda a: a.angulo_nominal):
                log.warning("Inspecao: angulo nominal %s, distancia %s cm", a.angulo_nominal,
                            a.distancia_cm if a.distancia_cm is not None else "DESCONHECIDA")
            log.warning("Inspecao concluida: permanecendo PARADO; desvio ainda nao habilitado")
            self._estado.definir_modo(Modo.PARADO)
            self._cancelar_inspecao()
        return True

    def _loop(self) -> None:
        periodo = 1.0 / cfg.FREQ_CONTROLE_HZ
        modo_ant = None
        aviso_ant = 0
        erro_ant = 0.0
        t_leitura_ant = 0.0
        derivada = 0.0
        t_ultima_linha = time.monotonic()

        while not self._parar.is_set():
            inicio = time.monotonic()

            with self._estado.lock:                          # decisão + envio atômicos
                modo = self._estado.atualizar_manobra()

                if modo is not Modo.SEGUINDO:
                    self._cancelar_inspecao()

                leitura_aviso = self._estado.ler_leitura()
                partida = modo is Modo.SEGUINDO and inicio < self._estado._partida_ate
                if fresca_aviso := (inicio - leitura_aviso.timestamp <= cfg.LEITURA_VALIDADE_S and leitura_aviso.linha_visivel):
                    t_ultima_linha = inicio
                aviso = (1 if partida else 2 if modo is Modo.SEGUINDO and
                         modo_ant is Modo.SEGUINDO and not fresca_aviso and
                         inicio - t_ultima_linha > cfg.PERDA_LINHA_TIMEOUT_S else 0)
                if aviso or aviso_ant:
                    getattr(self._motor, "avisar", lambda tipo: None)(aviso)
                aviso_ant = aviso
                if partida:
                    self._motor.parar()
                    modo_ant = None
                    self._estado.lock.release()
                    try:
                        self._parar.wait(periodo)
                    finally:
                        self._estado.lock.acquire()
                    continue

                if modo is Modo.PARADO:
                    self._motor.parar()                      # também serve de "keep-alive" do watchdog

                elif modo is Modo.GIRO_ESQ:
                    if self._obstaculo(): self._motor.parar()
                    else: self._motor.motores(-cfg.VEL_GIRO, cfg.VEL_GIRO)
                elif modo is Modo.GIRO_DIR:
                    if self._obstaculo(): self._motor.parar()
                    else: self._motor.motores(cfg.VEL_GIRO, -cfg.VEL_GIRO)
                elif modo is Modo.RE:
                    self._motor.motores(-cfg.VEL_RE, -cfg.VEL_RE)

                elif modo is Modo.MANUAL:
                    manual = self._estado.ler_manual()
                    prazo = manual[3] if manual and manual[3] else cfg.REMOTO_TIMEOUT_S
                    if manual is None or inicio - manual[2] > prazo:
                        log.warning("Controle remoto: sem comando há mais de %.1f s, parando", prazo)
                        self._estado.definir_modo(Modo.PARADO)
                        self._motor.parar()
                    elif (manual[0] > 0 or manual[1] > 0) and self._obstaculo():
                        self._motor.parar()                  # só para para a FRENTE; ré e giro seguem livres
                    else:
                        self._motor.motores(manual[0], manual[1])

                elif modo is Modo.SEGUINDO:
                    if modo_ant is not Modo.SEGUINDO:        # acabou de entrar: zera memória do PD
                        erro_ant, derivada = 0.0, 0.0
                        t_leitura_ant = 0.0
                        t_ultima_linha = inicio
                    bloqueado = self._inspecionar_obstaculo(inicio) or self._obstaculo()
                    leitura = self._estado.ler_leitura()
                    fresca = (inicio - leitura.timestamp) <= cfg.LEITURA_VALIDADE_S

                    if cfg.APRENDIZADO_ATIVO:
                        from aprendizado.politica import direcao_para_pwm   # import tardio: só o aprendizado precisa
                        # quem decide a direção é a thread de aprendizado (professor/CNN); aqui só se executa,
                        # e sem ação recente ou com obstáculo os motores PARAM (nunca mantém comando velho)
                        acao = self._estado.ler_acao()
                        if bloqueado or acao is None or inicio - acao.timestamp > cfg.APR_ACAO_VALIDADE_S:
                            self._motor.parar()
                        else:
                            esq, dir_ = direcao_para_pwm(acao.steer, acao.vel_fator)
                            self._motor.motores(esq, dir_)
                    elif bloqueado:
                        self._motor.parar()                  # algo à frente: espera sumir
                        t_ultima_linha = inicio              # parar por obstáculo não é "linha perdida"
                    elif fresca and leitura.linha_visivel:
                        t_ultima_linha = inicio
                        if t_leitura_ant and leitura.timestamp > t_leitura_ant:
                            dt = leitura.timestamp - t_leitura_ant
                            derivada = filtrar_derivada(derivada, leitura.erro, erro_ant, dt, cfg.KD_FILTRO)
                        erro_ant, t_leitura_ant = leitura.erro, leitura.timestamp
                        esq, dir_ = calcular_motores(leitura.erro, derivada)
                        self._motor.motores(esq, dir_)
                    elif inicio - t_ultima_linha > cfg.PERDA_LINHA_TIMEOUT_S:
                        log.warning("Linha perdida: parando")
                        self._motor.parar()
                    else:
                        # perdeu por pouco tempo: mantém a última correção em vez de parar
                        esq, dir_ = calcular_motores(erro_ant, 0.0)
                        self._motor.motores(esq, dir_)

                modo_ant = modo

            time.sleep(max(0.0, periodo - (time.monotonic() - inicio)))
