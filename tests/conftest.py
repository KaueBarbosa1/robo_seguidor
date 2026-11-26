"""Categorias de software; integração PTY legada roda isolada pelo executor."""
import sys
from pathlib import Path
import pytest

# Este arquivo legado executa um roteiro ao importar e altera config global.
# tools/testes.py o executa em processo separado no Linux, sem omiti-lo do relatório.
collect_ignore=['test_integracao_robo.py']


def pytest_configure(config):
    for marca in ('unitario','integracao','seguranca','carga','lento'):
        config.addinivalue_line('markers',marca+': categoria de validação de software')


def pytest_collection_modifyitems(items):
    integracao=('armazenamento','comunicacao','distribuido','central_monitoramento','gemeo_digital','inferencia_esp32')
    seguranca=('seguranca','recuo','sonar','bluetooth','distribuido','decisao','velocidade')
    for item in items:
        nome=item.nodeid
        if not any(item.get_closest_marker(m) for m in ('unitario','integracao')):
            item.add_marker(getattr(pytest.mark,'integracao' if any(s in nome for s in integracao) else 'unitario'))
        if any(s in nome for s in seguranca):item.add_marker(pytest.mark.seguranca)
        if 'ciclo_completo_sintetico' in nome:item.add_marker(pytest.mark.lento)
        if 'carga' in nome or 'filas' in nome:item.add_marker(pytest.mark.carga)
        if sys.platform=='win32' and ('test_esp32_wifi.py' in nome or 'test_cadeia_completa_com_simulador' in nome):
            item.add_marker(pytest.mark.skip(reason='Requer Linux/POSIX, bash e PTY; simulador sem hardware físico'))
        if 'test_sem_bluez_o_servidor_nao_derruba_nada' in nome:
            import importlib.util
            if importlib.util.find_spec('dbus_fast') is None:item.add_marker(pytest.mark.skip(reason='Dependência opcional dbus-fast ausente; não testa instalação de dependência'))


@pytest.fixture(autouse=True)
def restaurar_configuracao():
    """Os testes legados mudam cfg diretamente; uma mudança não deve contaminar outro."""
    import config as cfg
    valores={k:v for k,v in vars(cfg).items() if k.isupper()}
    yield
    for k,v in valores.items():setattr(cfg,k,v)
