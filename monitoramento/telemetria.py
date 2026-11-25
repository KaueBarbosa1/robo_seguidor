"""Snapshots somente de leitura. Nunca envia comandos ou captura outra imagem."""
from dataclasses import asdict
import time


def campo(valor, natureza='medido', idade=None, prazo=None, motivo=None):
    estado = 'indisponivel' if valor is None else 'atual'
    if idade is not None and prazo is not None and not 0 <= idade <= prazo:
        estado = 'desatualizado'
    return dict(valor=valor, natureza=natureza, estado=estado,
                idade_s=idade, motivo=motivo)


class Telemetria:
    def __init__(self, estado=None, motor=None, fonte=None, controle=None,
                 inferencia=None, simulado=False, politica='opencv', fonte_simulada=False):
        self.estado, self.motor, self.fonte = estado, motor, fonte
        self.controle, self.inferencia = controle, inferencia
        self.simulado, self.politica = simulado, politica
        self.fonte_simulada = fonte_simulada
        self.anterior = None

    def coletar(self):
        import config as cfg
        agora = time.monotonic()
        n = 'simulado' if self.simulado else 'medido'
        saida = {'simulado': self.simulado or self.fonte_simulada,
                 'dominios': dict(motores='simulado' if self.simulado else 'real',
                                 imagem='simulada' if self.fonte_simulada else 'real_ou_ausente'),
                 'operacao': {}, 'sensores': {},
                 'motores': {}, 'visao': {}, 'ia': {}}
        if self.estado and self.estado.lock.acquire(False):
            try:
                leitura = self.estado.ler_leitura()
                saida['operacao'] = dict(modo=self.estado.modo.name,
                    sessao_visao=self.estado.sessao_visao, encerrando=self.estado.encerrando,
                    motivo_controle=getattr(getattr(self.controle, 'decisao_linha', None), 'motivo', None),
                    motivo_parada_controle=getattr(self.controle, 'motivo_parada', None),
                    ultrassom_bluetooth_ativo=cfg.ULTRASSOM_BLUETOOTH_ATIVO,
                    motivo_parada_global=campo(None, motivo='motivo_parada_controle e ultimo diagnostico; nao ha trilha global de eventos'))
                valida = leitura.timestamp > 0 and leitura.camera_ok
                idade = leitura.idade(agora) if valida else None
                saida['visao']['camera_ok'] = leitura.camera_ok
                saida['visao']['frame_id'] = leitura.frame_id if valida else None
                for k, v in [('erro', leitura.erro), ('linha_visivel', leitura.linha_visivel),
                             ('confianca_heuristica', leitura.confianca)]:
                    disponivel = valida and (k != 'erro' or leitura.linha_visivel)
                    saida['visao'][k] = campo(v if disponivel else None,
                                             'simulado' if self.fonte_simulada else 'estimado',
                                             idade, cfg.LEITURA_VALIDADE_S)
                saida['visao']['idade_ultima_leitura_s'] = campo(idade, 'estimado',
                    motivo='inclui limite superior de idade informado pela camera, quando disponivel')
                saida['visao']['algoritmo'] = self.politica
            finally:
                self.estado.lock.release()
        elif self.estado:
            saida['operacao']['snapshot'] = campo(None, motivo='estado ocupado; amostra descartada')
        # Os getters existentes possuem apenas locks curtos de cópia, sem serial/disk I/O.
        s = getattr(self.motor, 'sensores', lambda: None)()
        d = getattr(self.motor, 'estado_motores', lambda: None)()
        servo = getattr(self.motor, 'status_servo', lambda: None)()
        idade = agora-s.timestamp if s else None
        for k in ('distancia_cm', 'avanco_bloqueado', 'falha_sensor', 'obstaculo_confirmado'):
            saida['sensores'][k] = campo(getattr(s, k, None), n, idade, cfg.SENSOR_TIMEOUT_S)
        saida['sensores']['angulo_servo_graus'] = campo(
            getattr(servo, 'angulo_nominal', None), 'simulado' if self.simulado else 'comandado',
            agora-servo.timestamp if servo else None, .5,
            'sem sensor de posicao fisica')
        for k in ('pwm_esq', 'pwm_dir', 'falha_encoder', 'pi_ativo'):
            saida['motores'][k] = campo(getattr(d, k, None),
                'simulado' if self.simulado else 'comandado' if k.startswith('pwm') else n,
                agora-d.timestamp if d else None, cfg.SENSOR_TIMEOUT_S)
        for lado in ('esq', 'dir'):
            ticks = getattr(s, 'ticks_'+lado, None)
            saida['motores']['ticks_'+lado] = campo(ticks, n, idade, cfg.SENSOR_TIMEOUT_S)
            pps = None
            if s and self.anterior and 0 <= idade <= cfg.SENSOR_TIMEOUT_S:
                ant = self.anterior
                dt = s.timestamp-ant['timestamp']
                delta = ticks-ant['ticks_'+lado]
                if dt > 0 and delta >= 0:
                    pps = delta/dt
            saida['motores']['pps_'+lado] = campo(pps, 'simulado' if self.simulado else 'estimado',
                idade, cfg.SENSOR_TIMEOUT_S, 'magnitude por delta; encoder nao mede sentido')
        if s and (self.anterior is None or s.timestamp > self.anterior['timestamp']):
            self.anterior = asdict(s)
        for k in ('erro_pi', 'velocidade_m_s', 'sentido_medido'):
            saida['motores'][k] = campo(None, motivo='nao exportado ou sem calibracao/feedback suficiente')
        saida['motores']['pedidos'] = 'ver pedidos do benchmark; envio nao confirma aplicacao'
        saida['ia'] = dict(politica=self.politica, local='raspberry_ou_host_embarcado',
                           aprendizado_ativo=cfg.APRENDIZADO_ATIVO,
                           recompensa=campo(None, motivo='nao fornecida na operacao atual'))
        if self.inferencia:
            saida['ia']['diagnostico'] = self.inferencia.status()
        if self.fonte and hasattr(self.fonte, 'estatisticas'):
            saida['camera'] = dict(self.fonte.estatisticas)
            if hasattr(self.fonte, 'saude'):
                saida['camera']['saude'] = self.fonte.saude()
            idade_camera = saida['camera'].get('idade_ms')
            limite = getattr(self.fonte, 'idade_max_s', cfg.LEITURA_VALIDADE_S)*1000
            saida['camera']['estado_idade'] = ('indisponivel' if idade_camera is None else
                'atual' if 0 <= idade_camera <= limite else 'desatualizado')
        saida['serial'] = dict(getattr(self.motor, 'estatisticas', {}))
        return saida
