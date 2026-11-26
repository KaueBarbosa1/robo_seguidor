"""Amostragem a 1 Hz. Todas as chamadas potencialmente lentas ficam no worker."""
from pathlib import Path
import subprocess
import time

try:
    import psutil
except ImportError:
    psutil = None


class Sistema:
    def __init__(self, raiz=Path('/'), ps=psutil):
        self.raiz, self.ps = Path(raiz), ps
        self.processo = ps.Process() if ps else None
        self.anterior_rede = None
        if ps:
            ps.cpu_percent(interval=None, percpu=True)  # primeira amostra apenas prepara baseline
            self.processo.cpu_percent(interval=None)
        self.preparado = False

    def _texto(self, relativo):
        try:
            return (self.raiz / relativo).read_text().strip()
        except (OSError, UnicodeError):
            return None

    def coletar(self):
        dados = dict(cpu_total_pct=None, cpu_nucleos_pct=None, ram_pct=None,
                     ram_usada_bytes=None, processo_rss_bytes=None, processo_cpu_pct=None,
                     temperatura_c=None, frequencia_mhz=None, throttling_atual=None,
                     subtensao_atual=None, throttling_desde_boot=None, subtensao_desde_boot=None,
                     rede_rx_bytes=None, rede_tx_bytes=None, rede_rx_bytes_s=None,
                     rede_tx_bytes_s=None, rede_erros=None, rede_descartes=None, processo_threads=None)
        indisponiveis = {}
        if self.ps:
            try:
                nucleos = self.ps.cpu_percent(interval=None, percpu=True)
                cpu_processo = self.processo.cpu_percent(interval=None)
                if self.preparado:
                    dados.update(cpu_nucleos_pct=nucleos,
                                 cpu_total_pct=sum(nucleos)/len(nucleos) if nucleos else None,
                                 processo_cpu_pct=cpu_processo)
                self.preparado = True
                ram = self.ps.virtual_memory()
                dados.update(ram_pct=ram.percent, ram_usada_bytes=ram.used,
                             processo_rss_bytes=self.processo.memory_info().rss)
                if hasattr(self.processo,'num_threads'):dados['processo_threads']=self.processo.num_threads()
                try:
                    freq = self.ps.cpu_freq()
                    dados['frequencia_mhz'] = freq.current if freq else None
                except (OSError, NotImplementedError, AttributeError):
                    pass
                rede = self.ps.net_io_counters()
                if rede:
                    t = time.perf_counter()
                    dados.update(rede_rx_bytes=rede.bytes_recv, rede_tx_bytes=rede.bytes_sent,
                                 rede_erros=rede.errin+rede.errout,
                                 rede_descartes=rede.dropin+rede.dropout)
                    if self.anterior_rede:
                        t0, rx0, tx0 = self.anterior_rede
                        if t > t0 and rede.bytes_recv >= rx0 and rede.bytes_sent >= tx0:
                            dados.update(rede_rx_bytes_s=(rede.bytes_recv-rx0)/(t-t0),
                                         rede_tx_bytes_s=(rede.bytes_sent-tx0)/(t-t0))
                    self.anterior_rede = t, rede.bytes_recv, rede.bytes_sent
            except (OSError, self.ps.Error) as exc:
                indisponiveis['psutil'] = type(exc).__name__
        else:
            indisponiveis['psutil'] = 'ausente; instale requirements-benchmark.txt'
        # No Pi, somente sensores explicitamente identificados como CPU/SoC.
        for zona in sorted((self.raiz/'sys/class/thermal').glob('thermal_zone*')):
            tipo = self._texto(str(zona.relative_to(self.raiz)/'type'))
            if tipo and ('cpu' in tipo.lower() or 'soc' in tipo.lower()):
                try:
                    dados['temperatura_c'] = float((zona/'temp').read_text()) / 1000
                except (OSError, ValueError):
                    pass
                break
        modelo = self._texto('proc/device-tree/model') or ''
        if 'Raspberry Pi' in modelo:
            # no máximo uma chamada por amostra (1 Hz), com prazo, nunca no controle
            try:
                r = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True,
                                   text=True, timeout=.2, check=True)
                bits = int(r.stdout.strip().split('=')[1], 16)
                dados.update(subtensao_atual=bool(bits & 1), throttling_atual=bool(bits & 4),
                             subtensao_desde_boot=bool(bits & (1 << 16)),
                             throttling_desde_boot=bool(bits & (1 << 18)))
            except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                indisponiveis['throttling'] = 'vcgencmd indisponivel ou timeout'
        for k, v in dados.items():
            if v is None:
                indisponiveis.setdefault(k, 'interface ausente, sem baseline ou nao aplicavel neste host')
        return dict(valores=dados, indisponiveis=indisponiveis,
                    escopo_rede='host inteiro, todas as interfaces; nao e trafego exclusivo do robo',
                    escopo_processo='somente este processo; CPU pode superar 100% em varios nucleos')
