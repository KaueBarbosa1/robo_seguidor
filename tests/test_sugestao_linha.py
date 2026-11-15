"""OpenCV e confirmação humana: testes sintéticos, sem GUI, modelos ou hardware."""
import sys
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from visao.sugestao import VERSAO, sugerir_linha, tratar_cinza  # noqa: E402
from tools.rotular_linha import (abrir_interface, carregar_revisoes, montar_revisao,  # noqa: E402
                                 preparar_lote, proxima_pendente, referencia_anterior, selecionar_lote)


def imagem_pontilhada(xs=(180,)):
    img = np.full((640, 360, 3), 230, np.uint8)
    for x in xs:
        for y in [100, 200, 300, 400, 500]:
            cv2.rectangle(img, (x - 8, y - 20), (x + 8, y + 20), (20, 20, 20), -1)
    return img


def registro(nome='a.jpg', video='a.mp4', tempo='0'):
    return {'imagem': nome, 'video_origem': video, 'timestamp': tempo,
            'largura': '360', 'altura': '640'}


def test_linha_tracejada_e_rejunte_fino():
    img = imagem_pontilhada()
    cv2.line(img, (0, 500), (359, 200), (50, 50, 50), 1)
    s = sugerir_linha(img)
    assert len(s.pontos) >= 4
    assert all(abs(x - 180) < 10 for x, _ in s.pontos)
    assert s.pontos == sorted(s.pontos, key=lambda p: p[1])


def test_normalizacao_reduz_sombra_sem_apagar_fita_ou_alterar_original():
    fundo = np.linspace(80, 230, 640).astype(np.uint8)
    img = np.repeat(fundo[:, None], 360, axis=1)
    img[:, 170:190] = (img[:, 170:190] * .2).astype(np.uint8)
    original = img.copy()
    tratado = tratar_cinza(img)
    assert tratado.shape == img.shape and tratado.dtype == np.uint8
    assert tratado[30:-30, 180].mean() < 80
    assert tratado[30:-30, 70].std() < img[30:-30, 70].std() * .2
    np.testing.assert_array_equal(img, original)


def test_fita_com_vao_grande_vence_rejunte_fragmentado_na_borda():
    img = np.full((640, 360, 3), 230, np.uint8)
    for y in [120, 335, 570]:
        cv2.rectangle(img, (110, y - 45), (130, y + 45), (20, 20, 20), -1)
    for y in range(20, 450, 40):
        cv2.rectangle(img, (310, y), (314, y + 12), (60, 60, 60), -1)
    s = sugerir_linha(img)
    assert s.segmentos >= 3
    assert all(abs(x - 120) < 12 for x, _ in s.pontos)
    assert s.pontos[-1][1] - s.pontos[0][1] > 400


def test_linha_real_perto_da_borda_nao_e_forcada_para_o_centro():
    s = sugerir_linha(imagem_pontilhada((25,)))
    assert s.segmentos >= 4
    assert all(abs(x - 25) < 10 for x, _ in s.pontos)


def test_sem_sugestao_nao_classifica_linha_como_ausente():
    for brilho in [0, 128, 255]:
        s = sugerir_linha(np.full((640, 360), brilho, np.uint8))
        assert s.pontos == [] and s.segmentos == 0
        assert 'não significa' in s.aviso
        assert not hasattr(s, 'visibilidade')


def test_segmento_unico_sugere_apenas_seu_trecho_interno():
    img = np.full((640, 360, 3), 230, np.uint8)
    cv2.rectangle(img, (170, 200), (190, 400), (20, 20, 20), -1)
    s = sugerir_linha(img)
    assert s.segmentos == 1 and len(s.pontos) >= 2
    assert all(170 <= x <= 190 and 200 <= y <= 400 for x, y in s.pontos)
    assert 'Só um segmento' in s.aviso


def test_coordenadas_voltam_para_imagem_original():
    img = imagem_pontilhada()
    ampliada = cv2.resize(img, (720, 1280), interpolation=cv2.INTER_NEAREST)
    s = sugerir_linha(ampliada)
    assert len(s.pontos) >= 4
    assert all(abs(x - 360) < 15 and 0 <= y < 1280 for x, y in s.pontos)


def test_referencia_ajuda_a_escolher_entre_duas_trajetorias():
    img = imagem_pontilhada((90, 270))
    s = sugerir_linha(img, referencia=[[270, 80], [270, 530]])
    assert len(s.pontos) >= 4
    assert all(abs(x - 270) < 10 for x, _ in s.pontos)


def test_salvar_exige_visibilidade_explicita_e_registra_proveniencia():
    pontos = [[180, 100], [180, 500]]
    sugestao = {'versao': VERSAO, 'metodo': 'teste', 'pontos_px': pontos}
    try:
        montar_revisao(registro(), '', pontos, 'hash', sugestao)
    except ValueError:
        pass
    else:
        raise AssertionError('Sugestão aceita sem visibilidade humana')
    item = montar_revisao(registro(), 'parcial', pontos, 'hash', sugestao)
    assert item['origem_rotulo'] == 'opencv_confirmado'
    assert item['confirmacao_humana'] is True and item['sugestao_automatica'] is True
    corrigido = montar_revisao(registro(), 'visivel', [[170, 100], [180, 500]], 'hash', sugestao)
    assert corrigido['origem_rotulo'] == 'opencv_corrigido'
    ausente = montar_revisao(registro(), 'ausente', [], 'hash', sugestao)
    assert ausente['origem_rotulo'] == 'humano' and not ausente['sugestao_automatica']


def test_revisao_anterior_nao_cruza_video_nem_usa_futuro():
    r = {**registro(), 'pontos_px': [[180, 100], [180, 500]], 'visibilidade': 'visivel'}
    revisoes = {'a.jpg': r}
    assert referencia_anterior(registro(tempo='.5'), revisoes) == r
    assert referencia_anterior(registro(video='b.mp4', tempo='.5'), revisoes) is None
    assert referencia_anterior(registro(tempo='3'), revisoes) is None
    assert referencia_anterior(registro(tempo='-1'), revisoes) is None
    assert referencia_anterior(registro(tempo='0'), revisoes) is None


def test_avanco_pula_revisoes_salvas_e_nao_as_modifica():
    registros = [registro(nome=n) for n in ['a', 'b', 'c']]
    revisoes = {'a': {'original': True}, 'c': {'original': True}}
    antes = repr(revisoes)
    assert proxima_pendente(registros, revisoes, 0) == 1
    assert proxima_pendente(registros, revisoes, 2) == 1
    assert repr(revisoes) == antes
    revisoes['b'] = {}
    assert proxima_pendente(registros, revisoes, 0) is None


def test_lote_tem_limite_equilibra_videos_e_preserva_teste():
    registros = [registro(f'{v}_{t}.jpg', v, str(t)) for v in ['a', 'b', 'teste'] for t in range(11)]
    revisoes = {r['imagem']: r for r in registros if r['timestamp'] in {'0', '10'}}
    lote = selecionar_lote(registros, revisoes, 6, ['a', 'b'])
    assert len(lote) == len({r['imagem'] for r in lote}) == 6
    assert [r['timestamp'] for r in lote[:2]] == ['5', '5']
    assert sum(r['video_origem'] == 'a' for r in lote) == 3
    assert sum(r['video_origem'] == 'b' for r in lote) == 3
    assert all(r['imagem'] not in revisoes and r['video_origem'] != 'teste' for r in lote)


def test_lote_reaberto_nao_acrescenta_imagens_apos_salvamentos():
    registros = [registro(f'a_{t}.jpg', 'a', str(t)) for t in range(10)]
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / 'plano.json'
        lote = preparar_lote(registros, {}, 4, ['a'], caminho)
        antes = caminho.read_bytes()
        revisoes = {r['imagem']: r for r in lote[:2]}
        reaberto = preparar_lote(registros, revisoes, 4, ['a'], caminho)
        assert reaberto == lote and caminho.read_bytes() == antes
        assert sum(r['imagem'] not in revisoes for r in reaberto) == 2
        assert json.loads(antes)['rotulos_gerados'] is False


def test_lote_concluido_ou_sem_candidatos_nao_inventa_exemplos():
    registros = [registro('a', 'a', '0')]
    assert selecionar_lote(registros, {}, 30, ['a']) == registros
    assert selecionar_lote(registros, {'a': registros[0]}, 30, ['a']) == []
    assert selecionar_lote(registros, {}, 30, ['outro']) == []


def test_fluxo_de_confirmacao_com_widgets_simulados():
    """Exercita callbacks reais; não substitui teste visual no desktop/VNC."""
    comandos, estados, erros = {}, {}, []

    class Widget:
        def pack(self, **kwargs):
            pass

    class Variavel:
        def __init__(self, value=''):
            self.valor = value

        def set(self, valor):
            self.valor = valor

        def get(self):
            return self.valor

    class Canvas(Widget):
        def __init__(self, *args, **kwargs):
            self.eventos = {}
            self.cores = []

        def bind(self, nome, callback):
            self.eventos[nome] = callback

        def delete(self, *args):
            pass

        def create_image(self, *args, **kwargs):
            pass

        create_line = create_image

        def create_oval(self, *args, **kwargs):
            self.cores.append(kwargs['fill'])

        def itemconfigure(self, *args, **kwargs):
            self.imagem_atual = kwargs['image']

    canvas = Canvas()
    with tempfile.TemporaryDirectory() as pasta:
        p = Path(pasta)
        caminho = p / 'b.jpg'
        assert cv2.imwrite(str(caminho), imagem_pontilhada())
        anterior = montar_revisao(registro('a.jpg'), 'visivel', [[180, 100], [180, 500]], 'hash_antigo')
        saida = p / 'revisoes.jsonl'
        salvo = json.dumps(anterior) + '\n'
        saida.write_text(salvo)

        def simular_interacao():
            # A janela abre na pendente b; calcular a sugestão não cria rótulos.
            assert saida.read_text() == salvo
            comandos['Alternar original/tratada']()
            comandos['Alternar original/tratada']()
            assert saida.read_text() == salvo
            comandos['Confirmar e avançar']()
            assert erros and saida.read_text() == salvo  # ainda falta escolher visibilidade
            # Arrasta o centro de um segmento: imagem 360x640 exibida com altura 700.
            canvas.eventos['<Button-1>'](SimpleNamespace(x=197, y=109))
            canvas.eventos['<B1-Motion>'](SimpleNamespace(x=208, y=110))
            canvas.eventos['<ButtonRelease-1>'](None)
            estados['visivel'].set('visivel')
            comandos['Confirmar e avançar']()
            revisoes = carregar_revisoes(saida)
            assert revisoes['a.jpg'] == anterior
            assert revisoes['b.jpg']['origem_rotulo'] == 'opencv_corrigido'
            assert revisoes['b.jpg']['confirmacao_humana'] is True
            assert revisoes['b.jpg']['sugestao']['preprocessamento'] == 'normalizado'
            assert len(saida.read_text().splitlines()) == 2
            # Recalcular após revisão salva deve continuar ciano, mesmo quando
            # os pontos diferem dos que estavam na tela ao abrir a imagem.
            canvas.cores.clear()
            comandos['Recalcular sugestão']()
            assert canvas.cores and set(canvas.cores) == {'cyan'}
            assert len(saida.read_text().splitlines()) == 2
            comandos['Tentar sem correção']()
            assert len(saida.read_text().splitlines()) == 2

        def botao(*args, **kwargs):
            comandos[kwargs['text']] = kwargs['command']
            return Widget()

        def radio(*args, **kwargs):
            estados[kwargs['value']] = kwargs['variable']
            return Widget()

        raiz = SimpleNamespace(title=lambda *a: None, protocol=lambda *a: None,
                               mainloop=simular_interacao, winfo_screenheight=lambda: 960)
        mensagens = SimpleNamespace(showerror=lambda *a: erros.append(a), showinfo=lambda *a: None,
                                     askyesno=lambda *a: True)
        tk = SimpleNamespace(Tk=lambda: raiz, StringVar=Variavel, Label=lambda *a, **k: Widget(),
                             Frame=lambda *a, **k: Widget(), Canvas=lambda *a, **k: canvas,
                             Radiobutton=radio, Button=botao, PhotoImage=lambda **k: object(),
                             messagebox=mensagens)
        with patch.dict(sys.modules, {'tkinter': tk}):
            abrir_interface([registro('a.jpg'), registro('b.jpg')], {'b.jpg': caminho}, saida)


if __name__ == '__main__':
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith('test_'):
            funcao()
            print('OK', nome)
