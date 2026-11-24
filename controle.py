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
import math
from dataclasses import dataclass
import threading
import time

import config as cfg
from estado import EstadoRobo, Modo
from motor.protocolo import GUARDA_SONAR_MOTIVOS

log = logging.getLogger("controle")

@dataclass
class _SegurancaManual:
    # Compartilhado pelo callback Bluetooth e pelo loop, sob estado.lock.
    aguardando_comando: bool = False
    falha_encoder: bool = False


def _seguranca(estado):
    if not hasattr(estado, "_seguranca_manual"):
        estado._seguranca_manual = _SegurancaManual()
    return estado._seguranca_manual


def _motivo_encoder(estado, motor, agora=None, novo_comando=False):
    seguranca = _seguranca(estado)
    d = getattr(motor, "estado_motores", lambda: None)()
    if agora is None:
        agora = time.monotonic()
    recente = d is not None and 0 <= agora - d.timestamp <= cfg.SENSOR_TIMEOUT_S
    if recente and d.falha_encoder:
        seguranca.falha_encoder = True
    elif novo_comando and recente:
        # S limpa a falha no Uno; somente uma nova intencao aceita o rearme.
        seguranca.falha_encoder = False
    return "falha_encoder" if seguranca.falha_encoder else None


def _motivo_sensor(estado, motor, agora=None):
    """Nao conta pacotes FC como ecos: respeita a confirmacao/histerese do Uno."""
    if not cfg.OBSTACULO_ATIVO:
        return None
    s = getattr(motor, "sensores", lambda: None)()
    status = getattr(motor, "status_servo", lambda: None)()
    if agora is None:
        agora = time.monotonic()
    if s is None or not 0 <= agora - s.timestamp <= cfg.SENSOR_TIMEOUT_S:
        return "telemetria_vencida"
    if s.falha_sensor:
        return "eco_invalido"
    distancia = getattr(s, "distancia_cm", None)
    if distancia is None or not math.isfinite(distancia) or distancia < 0:
        return "eco_invalido"
    if s.avanco_bloqueado:
        return "obstaculo" if getattr(s, "obstaculo_confirmado", False) else "guarda_frontal"
    modo4 = (status is not None and status.ativo and status.sonar_movimento and
             0 <= agora - status.timestamp <= .5)
    if modo4:
        return "aguardando_centro" if estado.modo is Modo.SEGUINDO else None
    checar = getattr(motor, "obstaculo", None)
    return "obstaculo" if checar and checar(cfg.OBSTACULO_DIST_CM, cfg.OBSTACULO_LEITURAS) else None


def _motivo_lateral(motor, manual, agora=None):
    s = getattr(motor, "sensores", lambda: None)()
    if agora is None:
        agora = time.monotonic()
    if s is None or not 0 <= agora - s.timestamp <= cfg.SENSOR_TIMEOUT_S:
        return None
    esq, dir_ = manual[:2]
    bloqueada = ((esq < dir_ and getattr(s, "lateral_esq_bloqueada", False)) or
                 (esq > dir_ and getattr(s, "lateral_dir_bloqueada", False)))
    return "lateral_bloqueada" if bloqueada else None


def aplicar_comando(estado: EstadoRobo, motor, comando: str) -> None:
    """Chamado pela thread de voz. Prioridade absoluta sobre a visão."""
    with estado.lock:
        if estado.encerrando and comando != "pare":
            return
        if comando in {"pare", "siga", "esquerda", "direita", "voltar"}:
            getattr(motor, 'usar_sonar_manual', lambda ativo: None)(False)
        if comando in {"pare", "esquerda", "direita", "voltar"}:
            centrar = getattr(motor, "configurar_servo", None)
            if centrar:
                motor.parar()
                centrar(False)
        if comando != "siga":
            estado._partida_ate = 0.0
            getattr(motor, "avisar", lambda tipo: None)(0)
        if comando in {"siga", "esquerda", "direita", "voltar"}:
            _motivo_encoder(estado, motor, novo_comando=True)
        if comando == "pare":
            _seguranca(estado).aguardando_comando = False
            estado._recuo_bloqueia_avanco = False
            estado._parada_manual_id += 1
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
        if estado.encerrando:
            return
        getattr(motor, 'usar_sonar_manual', lambda ativo: None)(bool(esq or dir_))
        centrar = getattr(motor, "configurar_servo", None)
        if centrar and (not cfg.SONAR_MOVIMENTO_ATIVO or not (esq or dir_)):
            centrar(False)
        estado.definir_manual(esq, dir_, validade_s)
        seguranca = _seguranca(estado)
        agora = time.monotonic()
        motivo = _motivo_encoder(estado, motor, novo_comando=True)
        if not motivo and (esq > 0 or dir_ > 0):
            motivo = _motivo_sensor(estado, motor)
        motivo = motivo or _motivo_lateral(motor, (esq, dir_))
        if esq == 0 and dir_ == 0:
            seguranca.aguardando_comando = False
            motor.parar()
        elif motivo:
            seguranca.aguardando_comando = True
            log.info("MANUAL comando recusado: %s; aguardando novo comando seguro", motivo)
            # Pacotes do botao nao interrompem uma re automatica ja em curso.
            if motivo == "falha_encoder" or not estado._recuo_bloqueia_avanco:
                motor.parar()
        else:
            # Este callback e uma nova intencao do operador; o loop nunca
            # reaproveita o pedido anterior ao bloqueio.
            seguranca.aguardando_comando = False
            if estado._recuo_bloqueia_avanco:
                estado._recuo_bloqueia_avanco = False
                estado._parada_manual_id += 1
            motor.motores(esq, dir_)


@dataclass(frozen=True)
class DecisaoLinha:
    esq: int
    dir: int
    motivo: str
    erro: float = 0.0
    estimada: bool = False
    idade_observacao_s: float | None = None


class ThreadControle(threading.Thread):
    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event, fonte=None, inferencia_rl=None):
        super().__init__(name="controle", daemon=True)
        self._estado = estado
        self._motor = motor
        self._parar = parar
        self._fonte = fonte
        self._inferencia_rl = inferencia_rl
        self._linha_geracao = None
        self._linha_sessao = -1
        self._linha_min_t = 0.0
        self._limpar_linha()
        self.decisao_linha = DecisaoLinha(0, 0, "aguardando_observacao")
        self._obst_ant = False
        self._inspecao_inicio = None
        self._inspecao_aguarda_frente = False
        self._retomada_visual_pendente = False
        self._retomada_exige_linha = False
        self.motivo_parada = "modo_PARADO"
        self._recuo = None  # (inicio, comando de origem, ticks E/D)
        self._recuo_parada_id = estado._parada_manual_id
        self._diagnostico_manual_chave = None
        self._diagnostico_manual_t = float('-inf')

    def run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception("Thread de controle caiu")
            self._parar.set()
            self._estado.encerrar()
        finally:
            self._parar.set()
            with self._estado.lock:
                self._estado.definir_modo(Modo.PARADO)
                self._motor.parar(repetir=3)
                self._recuo = None
                self._limpar_linha()
                self.decisao_linha = DecisaoLinha(0, 0, "encerrado")
                self._cancelar_inspecao()
                getattr(self._motor, "avisar", lambda tipo: None)(0)

    def _limpar_linha(self):
        self._linha_ultima = None
        self._linha_erro = 0.0
        self._linha_derivada = 0.0
        self._linha_em_vao = False

    def _parar_linha(self, motivo, agora):
        self._limpar_linha()
        self._linha_min_t = max(self._linha_min_t, agora)
        return DecisaoLinha(0, 0, motivo)

    def decidir_linha(self, agora: float, bloqueado: bool = False) -> DecisaoLinha:
        """Sob estado.lock. Só calcula: não escreve em motores ou sensores.

        `bloqueado` vem da inspeção/guarda de ultrassom já existentes no loop.
        Recebe a mesma leitura usada na operação; permite teste sem hardware.
        A memória guarda apenas números de uma observação, nunca frames.
        """
        sessao = self._estado.sessao_visao
        if sessao != self._linha_sessao:
            self._limpar_linha()
            self._linha_sessao, self._linha_min_t = sessao, 0.0
        if self._parar.is_set() or self._estado.modo is not Modo.SEGUINDO:
            return self._parar_linha("parado", agora)
        if bloqueado:
            return self._parar_linha("obstaculo_ou_sensor", agora)
        leitura = self._estado.ler_leitura()
        saude = getattr(self._fonte, 'saude', None)
        monitorada = callable(saude)
        if monitorada:
            if cfg.APRENDIZADO_ATIVO:
                return self._parar_linha("cnn_sem_contrato_esp32", agora)
            camera = saude()
            if camera['geracao'] != self._linha_geracao:
                self._limpar_linha()
                self._linha_geracao = camera['geracao']
            if camera['status'] != 'ok' or leitura.geracao_camera != camera['geracao']:
                return self._parar_linha("camera_indisponivel", agora)
        if not leitura.camera_ok:
            return self._parar_linha("camera_indisponivel", agora)
        if leitura.sessao != sessao:
            return self._parar_linha("sessao_visual_invalida", agora)
        numeros = (leitura.erro, leitura.timestamp, leitura.idade_captura_s,
                   leitura.direcao, leitura.escala_direcao, leitura.confianca)
        if (not all(math.isfinite(v) for v in numeros) or
                leitura.idade_captura_s < 0 or not -1 <= leitura.erro <= 1 or
                not 0 <= leitura.confianca <= 1):
            return self._parar_linha("leitura_invalida", agora)
        limite = min(cfg.LEITURA_VALIDADE_S,
                     getattr(self._fonte, 'idade_max_s', cfg.LEITURA_VALIDADE_S))
        if agora < leitura.timestamp or not 0 <= leitura.idade(agora) <= limite:
            return self._parar_linha("frame_vencido", agora)
        if leitura.timestamp < self._linha_min_t:
            return DecisaoLinha(0, 0, "aguardando_observacao")
        if leitura.linha_visivel:
            if leitura.confianca < cfg.TRACEJADO_CONFIANCA_MIN:
                return self._parar_linha("deteccao_nao_confiavel", agora)
            erro = max(-1., min(1., leitura.erro + cfg.TRACEJADO_ANTECIPACAO *
                               leitura.direcao * leitura.escala_direcao))
            anterior = self._linha_ultima
            if anterior is None or leitura.timestamp > anterior.timestamp:
                if (anterior is not None and not self._linha_em_vao and
                        leitura.timestamp - anterior.timestamp <= cfg.LEITURA_VALIDADE_S):
                    self._linha_derivada = filtrar_derivada(
                        self._linha_derivada, erro, self._linha_erro,
                        leitura.timestamp - anterior.timestamp, cfg.KD_FILTRO)
                else:
                    self._linha_derivada = 0.0
                self._linha_ultima, self._linha_erro = leitura, erro
            self._linha_em_vao = False
            esq, dir_ = calcular_motores(self._linha_erro, self._linha_derivada)
            return DecisaoLinha(esq, dir_, "observada", self._linha_erro,
                               idade_observacao_s=leitura.idade(agora))
        if leitura.motivo in {"trajetorias_ambiguas", "suporte_insuficiente"}:
            return self._parar_linha("deteccao_nao_confiavel", agora)
        ultima = self._linha_ultima
        if ultima is None:
            return DecisaoLinha(0, 0, "aguardando_observacao")
        idade = ultima.idade(agora)
        if not 0 <= idade < cfg.PERDA_LINHA_TIMEOUT_S:
            return self._parar_linha("linha_perdida", agora)
        # Mantém a última geometria confiável; não inventa velocidade lateral.
        # Tempo sem observação aumenta continuamente, mesmo com frames repetidos.
        self._linha_em_vao = True
        self._linha_derivada = 0.0
        esq, dir_ = calcular_motores(self._linha_erro, 0.0)
        fator = max(0., min(1., cfg.TRACEJADO_VAO_FATOR)) * ultima.confianca
        fator *= 1. - idade / cfg.PERDA_LINHA_TIMEOUT_S
        return DecisaoLinha(int(esq * fator), int(dir_ * fator), "vao_limitado",
                           self._linha_erro, True, idade)

    def decidir_cnn_rl(self, agora, bloqueado=False):
        """RL escolhe; guarda visual existente e ultrassom podem vetar, nunca substituir por PD."""
        base = self.decidir_linha(agora, bloqueado)
        if self._inferencia_rl.sombra:
            return DecisaoLinha(0, 0, "cnn_rl_sombra")
        if base.motivo not in {"observada", "vao_limitado"}:
            return DecisaoLinha(0, 0, base.motivo)
        diagnostico = getattr(self._motor, 'estado_motores', lambda: None)()
        if (diagnostico is None or not 0 <= time.monotonic()-diagnostico.timestamp <= cfg.SENSOR_TIMEOUT_S or
                diagnostico.falha_encoder):
            return DecisaoLinha(0, 0, "diagnostico_motor_rl_indisponivel")
        a = self._estado.ler_acao_rl()
        if a is None:
            return DecisaoLinha(0, 0, "aguardando_cnn_rl")
        camera = self._fonte.saude()
        limite = min(cfg.LEITURA_VALIDADE_S, self._fonte.idade_max_s)
        numeros = (a.steer, a.vel_fator, a.timestamp, a.idade_captura_s, a.erro_cnn, a.visibilidade)
        if (not all(math.isfinite(v) for v in numeros) or not -1 <= a.steer <= 1 or
                not 0 <= a.vel_fator <= 1 or not -1 <= a.erro_cnn <= 1 or
                not 0 <= a.visibilidade <= 1 or a.idade_captura_s < 0):
            return DecisaoLinha(0, 0, "acao_rl_invalida")
        if (camera['status'] != 'ok' or a.geracao_camera != camera['geracao'] or
                a.sessao != self._estado.sessao_visao or not 0 <= agora-a.timestamp or
                not 0 <= a.idade(agora) <= limite):
            return DecisaoLinha(0, 0, "acao_rl_vencida")
        if a.timestamp < self._linha_min_t:
            return DecisaoLinha(0, 0, "aguardando_rl_apos_bloqueio")
        if a.motivo != 'cnn_rl':
            return DecisaoLinha(0, 0, a.motivo)
        from aprendizado.politica import direcao_para_pwm
        esq, direita = direcao_para_pwm(a.steer, a.vel_fator)
        if base.estimada:
            fator = max(0., min(1., cfg.TRACEJADO_VAO_FATOR)) * self._linha_ultima.confianca
            fator *= max(0., 1.-base.idade_observacao_s/cfg.PERDA_LINHA_TIMEOUT_S)
            esq, direita = int(esq*fator), int(direita*fator)
        return DecisaoLinha(esq, direita, "cnn_rl", a.erro_cnn, base.estimada, a.idade(agora))

    def _diagnosticar_manual(self, manual, motivo):
        """Somente leitura/log: nao altera o pedido nem envia comandos de motor."""
        if not getattr(cfg, 'REMOTO_DIAGNOSTICO_MOVIMENTO', True):
            return
        motor = self._motor
        s = getattr(motor, 'sensores', lambda: None)()
        d = getattr(motor, 'estado_motores', lambda: None)()
        v = getattr(motor, 'status_servo', lambda: None)()
        g = getattr(motor, 'guarda_sonar', lambda: None)()
        agora = time.monotonic()  # depois dos snapshots: nao tratar pacote novo como timestamp futuro
        def recente(pacote, prazo):
            return pacote is not None and 0 <= agora - getattr(pacote, 'timestamp', float('-inf')) <= prazo
        sens_ok = recente(s, cfg.SENSOR_TIMEOUT_S)
        diag_ok = recente(d, cfg.SENSOR_TIMEOUT_S)
        servo_ok = recente(v, .5)
        bloqueio = s.avanco_bloqueado if sens_ok else 'indisponivel'
        falha_sensor = s.falha_sensor if sens_ok else 'indisponivel'
        falha_encoder = d.falha_encoder if diag_ok else 'indisponivel'
        modo4 = bool(getattr(v, 'ativo', False) and getattr(v, 'sonar_movimento', False)) if servo_ok else 'indisponivel'
        guarda = 'indisponivel'
        if modo4 is True and g is not None and 0 <= agora - g[1] <= cfg.SENSOR_TIMEOUT_S:
            guarda = '+'.join(nome for bit, nome in enumerate(GUARDA_SONAR_MOTIVOS) if g[0] & (1 << bit)) or 'livre'
        if motivo == 'pedido_movimento' and falha_encoder is True:
            motivo = 'falha_encoder_no_arduino'
        elif motivo == 'pedido_movimento' and cfg.SONAR_MOVIMENTO_ATIVO and modo4 is not True:
            motivo = 'aguardando_modo4'
        chave = (motivo, bloqueio, falha_sensor, falha_encoder, modo4, guarda)
        if chave == self._diagnostico_manual_chave and agora - self._diagnostico_manual_t < 1.:
            return
        self._diagnostico_manual_chave, self._diagnostico_manual_t = chave, agora
        pedido = manual[:2] if manual else ('indisponivel', 'indisponivel')
        log.info('MANUAL motivo=%s | pedido E=%s D=%s | frente_bloqueada=%s falha_sensor=%s | '
                 'modo4=%s | PWM E=%s D=%s falha_encoder=%s | encoders E=%s D=%s | '
                 'frente_cm=%s angulo_nominal=%s guarda=%s',
                 motivo, *pedido, bloqueio, falha_sensor, modo4,
                 d.pwm_esq if diag_ok else 'indisponivel', d.pwm_dir if diag_ok else 'indisponivel',
                 falha_encoder, getattr(s, 'ticks_esq', 'indisponivel') if sens_ok else 'indisponivel',
                 getattr(s, 'ticks_dir', 'indisponivel') if sens_ok else 'indisponivel',
                 getattr(s, 'distancia_cm', 'indisponivel') if sens_ok else 'indisponivel',
                 getattr(v, 'angulo_nominal', 'indisponivel') if servo_ok else 'indisponivel', guarda)

    def _obstaculo(self) -> bool:
        return _motivo_sensor(self._estado, self._motor) is not None

    def _lateral_bloqueada(self, manual) -> bool:
        return _motivo_lateral(self._motor, manual) is not None

    def _diagnosticar_parada(self, motivo):
        if motivo != self.motivo_parada:
            log.info("CONTROLE motivo=%s", motivo or "movimento_solicitado")
            self.motivo_parada = motivo

    def _cancelar_inspecao(self) -> None:
        if self._inspecao_inicio is not None:
            self._motor.parar()
            self._motor.configurar_servo(False)
            self._inspecao_inicio = None

    def _recuar_manual(self, agora: float, manual) -> bool:
        """Sob estado.lock: uma re limitada por toque; True assume o envio ao motor."""
        est, motor = self._estado, self._motor
        if self._recuo_parada_id != est._parada_manual_id:
            self._recuo = None
            self._recuo_parada_id = est._parada_manual_id
        if est.modo is not Modo.MANUAL or manual is None:
            if self._recuo is not None:
                motor.parar()
            self._recuo = None
            return False
        comando = manual[:2]
        avanco = any(v > 0 for v in comando)
        if self._recuo is not None and comando != self._recuo[1]:
            motor.parar()
            self._recuo = None
        if not avanco:
            return False  # re explicita do operador tem prioridade
        habilitado = (cfg.RECUO_MANUAL_ATIVO and cfg.OBSTACULO_ATIVO and
                      cfg.SONAR_MOVIMENTO_ATIVO and cfg.CONTROLE_VELOCIDADE_ATIVO and
                      not cfg.FIRMWARE_COM_CAMERA and callable(getattr(motor, 'velocidade', None)))
        s = getattr(motor, 'sensores', lambda: None)()
        status = getattr(motor, 'status_servo', lambda: None)()
        recente = (s is not None and 0 <= agora - s.timestamp <= cfg.SENSOR_TIMEOUT_S and
                   status is not None and status.ativo and status.sonar_movimento and
                   0 <= agora - status.timestamp <= cfg.SENSOR_TIMEOUT_S)
        if self._recuo is None and not est._recuo_bloqueia_avanco:
            if not (habilitado and recente and not s.falha_sensor and s.avanco_bloqueado and
                    getattr(s, 'obstaculo_confirmado', False) and
                    s.distancia_cm is not None and 0 <= s.distancia_cm < cfg.RECUO_MANUAL_DIST_CM):
                return False
            est._recuo_bloqueia_avanco = True
            self._recuo = (agora, comando, (s.ticks_esq, s.ticks_dir))
            log.warning('Obstaculo frontal muito proximo: parada e re curta automatica manual')
        if self._recuo is not None:
            inicio, _, ticks = self._recuo
            decorrido = agora - inicio
            deltas = (s.ticks_esq - ticks[0], s.ticks_dir - ticks[1]) if recente else (-1, -1)
            # A re pode invalidar a frente; exigir comunicacao, nao frente livre.
            if (not habilitado or not recente or min(deltas) < 0 or
                    max(deltas) >= cfg.RECUO_MANUAL_MAX_PULSOS or
                    decorrido >= cfg.RECUO_MANUAL_REPOUSO_S + cfg.RECUO_MANUAL_TEMPO_S):
                self._recuo = None
                log.warning('Re automatica encerrada; aguardando frente livre e novo comando')
            elif decorrido >= cfg.RECUO_MANUAL_REPOUSO_S:
                motor.velocidade(-cfg.RECUO_MANUAL_PPS, -cfg.RECUO_MANUAL_PPS)
                return True
        if est._recuo_bloqueia_avanco:
            _seguranca(est).aguardando_comando = True
            if self._recuo is None and _motivo_sensor(est, motor, agora) is None:
                est._recuo_bloqueia_avanco = False
                return False  # sensor livre; o pedido antigo continua descartado
            motor.parar()
            return True
        return False

    def _inspecionar_obstaculo(self, agora: float) -> bool:
        """Executado sob estado.lock. Mantem parada; nunca escolhe movimento lateral."""
        if not (cfg.OBSTACULO_ATIVO and cfg.INSPECAO_OBSTACULO_ATIVA):
            self._cancelar_inspecao()
            return False
        if not callable(getattr(self._motor, "inspecionar_obstaculo", None)):
            return False
        if self._inspecao_aguarda_frente:
            if _motivo_sensor(self._estado, self._motor, agora) is None:
                self._inspecao_aguarda_frente = False
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
            log.warning("Inspecao concluida: aguardando frente livre e nova observacao da linha")
            self._cancelar_inspecao()
            self._inspecao_aguarda_frente = True
        return True

    def _loop(self) -> None:
        periodo = 1.0 / cfg.FREQ_CONTROLE_HZ
        modo_ant = None
        aviso_ant = 0
        t_ultima_linha = time.monotonic()

        while not self._parar.is_set():
            inicio = time.monotonic()

            with self._estado.lock:                          # decisão + envio atômicos
                modo = self._estado.atualizar_manobra()
                if modo is not Modo.MANUAL:
                    if modo_ant is Modo.MANUAL and getattr(cfg, 'REMOTO_DIAGNOSTICO_MOVIMENTO', True):
                        log.info('MANUAL encerrado: modo=%s', modo.name)
                    self._diagnostico_manual_chave = None
                    self._recuar_manual(inicio, None)

                if modo is not Modo.SEGUINDO:
                    self.decisao_linha = DecisaoLinha(0, 0, "modo_" + modo.name.lower())
                    self._cancelar_inspecao()
                getattr(self._motor, 'usar_sonar_manual', lambda ativo: None)(modo is Modo.MANUAL)

                # Renovar mesmo enquanto a guarda espera as primeiras leituras;
                # V nao renova o watchdog dos motores e nao envia movimento.
                if cfg.SONAR_MOVIMENTO_ATIVO and modo is Modo.MANUAL:
                    getattr(self._motor, 'iniciar_sonar_movimento', lambda: None)()

                leitura_aviso = self._estado.ler_leitura()
                partida = modo is Modo.SEGUINDO and inicio < self._estado._partida_ate
                if fresca_aviso := (leitura_aviso.camera_ok and
                                    0 <= leitura_aviso.idade(inicio) <= cfg.LEITURA_VALIDADE_S and
                                    leitura_aviso.linha_visivel):
                    t_ultima_linha = leitura_aviso.timestamp - leitura_aviso.idade_captura_s
                aviso = (1 if partida else 2 if modo is Modo.SEGUINDO and
                         modo_ant is Modo.SEGUINDO and not fresca_aviso and
                         inicio - t_ultima_linha > cfg.PERDA_LINHA_TIMEOUT_S else 0)
                if aviso or aviso_ant:
                    getattr(self._motor, "avisar", lambda tipo: None)(aviso)
                aviso_ant = aviso
                if partida:
                    self.decisao_linha = DecisaoLinha(0, 0, "partida")
                    self._motor.parar()
                    modo_ant = None
                    self._estado.lock.release()
                    try:
                        self._parar.wait(periodo)
                    finally:
                        self._estado.lock.acquire()
                    continue

                motivo_encoder = _motivo_encoder(self._estado, self._motor)
                if motivo_encoder:
                    _seguranca(self._estado).aguardando_comando = True
                    self._retomada_visual_pendente = True
                    self._retomada_exige_linha = True
                    self._parar_linha("falha_encoder", inicio)
                    self._diagnosticar_parada("falha_encoder")
                    self._motor.parar()
                elif modo is Modo.PARADO:
                    self._diagnosticar_parada("modo_PARADO")
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
                        motivo_manual = 'comando_expirado'
                        log.warning("Controle remoto: sem comando há mais de %.1f s, parando", prazo)
                        self._estado.definir_modo(Modo.PARADO)
                        self._recuar_manual(inicio, None)
                        self._motor.parar()
                    elif self._recuar_manual(inicio, manual):
                        _seguranca(self._estado).aguardando_comando = True
                        motivo_manual = 'recuo_automatico' if self._recuo else 'aguardando_novo_comando_apos_recuo'
                    else:
                        motivo_manual = _motivo_lateral(self._motor, manual)
                        if not motivo_manual and any(v > 0 for v in manual[:2]):
                            motivo_manual = _motivo_sensor(self._estado, self._motor)
                        seguranca = _seguranca(self._estado)
                        if motivo_manual:
                            seguranca.aguardando_comando = True
                            self._motor.parar()
                        elif seguranca.aguardando_comando:
                            motivo_manual = 'aguardando_novo_comando'
                            self._motor.parar()
                        else:
                            motivo_manual = 'pedido_movimento' if any(manual[:2]) else 'neutro'
                            self._motor.motores(manual[0], manual[1])
                    self._diagnosticar_parada(motivo_manual)
                    self._diagnosticar_manual(manual, motivo_manual)

                elif modo is Modo.SEGUINDO:
                    if modo_ant is not Modo.SEGUINDO:
                        t_ultima_linha = inicio
                    inspecao = self._inspecionar_obstaculo(inicio)
                    motivo_sensor = _motivo_sensor(self._estado, self._motor)
                    bloqueado = inspecao or motivo_sensor is not None
                    if bloqueado:
                        self._retomada_visual_pendente = True
                        self._retomada_exige_linha = True
                    elif self._retomada_visual_pendente:
                        # A observacao deve ser posterior a confirmacao de caminho livre.
                        self._parar_linha("aguardando_observacao", time.monotonic())
                        self._retomada_visual_pendente = False
                    self._diagnosticar_parada("inspecao" if inspecao else motivo_sensor)
                    if cfg.APRENDIZADO_ATIVO:
                        from aprendizado.politica import direcao_para_pwm   # import tardio: só o aprendizado precisa
                        # quem decide a direção é a thread de aprendizado (professor/CNN); aqui só se executa,
                        # e sem ação recente ou com obstáculo os motores PARAM (nunca mantém comando velho)
                        acao = self._estado.ler_acao()
                        if self._retomada_exige_linha and not bloqueado:
                            visual = self.decidir_linha(time.monotonic())
                            if visual.motivo == "observada":
                                self._retomada_exige_linha = False
                        if (bloqueado or self._retomada_exige_linha or callable(getattr(self._fonte, 'saude', None)) or
                                acao is None or inicio - acao.timestamp > cfg.APR_ACAO_VALIDADE_S):
                            self._motor.parar()
                        else:
                            esq, dir_ = direcao_para_pwm(acao.steer, acao.vel_fator)
                            self._motor.motores(esq, dir_)
                    else:
                        decisao = (self.decidir_cnn_rl(time.monotonic(), bloqueado) if self._inferencia_rl is not None
                                   else self.decidir_linha(time.monotonic(), bloqueado))
                        self.decisao_linha = decisao
                        self._diagnosticar_parada(motivo_sensor or
                                                 (decisao.motivo if not (decisao.esq or decisao.dir) else None))
                        if decisao.esq == 0 and decisao.dir == 0:
                            self._motor.parar()
                        else:
                            self._motor.motores(decisao.esq, decisao.dir)

                modo_ant = modo

            time.sleep(max(0.0, periodo - (time.monotonic() - inicio)))
