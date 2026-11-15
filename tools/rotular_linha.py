"""Rotulagem assistida por OpenCV, sem câmera e sem comandos de motor.

Raspberry Pi com desktop/VNC: .venv/bin/python tools/rotular_linha.py
Confira a sugestão, escolha a visibilidade e confirme. Arraste pontos para corrigir.
"""
import argparse
import base64
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from visao.sugestao import VERSAO, preparar_imagem, sugerir_linha  # noqa: E402


def validar_anotacao(status, pontos, largura, altura):
    if status not in {'visivel', 'parcial', 'ausente', 'ambiguo'}:
        raise ValueError('Escolha um estado de visibilidade.')
    if status in {'ausente', 'ambiguo'}:
        if pontos:
            raise ValueError('Limpe os pontos para marcar ausente ou ambíguo.')
        return []
    if len(pontos) < 2:
        raise ValueError('Marque ao menos dois centros da trajetória, em alturas diferentes.')
    pontos = sorted(([int(x), int(y)] for x, y in pontos), key=lambda p: p[1])
    if any(not (0 <= x < largura and 0 <= y < altura) for x, y in pontos):
        raise ValueError('Ponto fora da imagem.')
    if len({y for _, y in pontos}) != len(pontos):
        raise ValueError('Use alturas diferentes para os pontos da mesma trajetória.')
    return pontos


def carregar_revisoes(caminho):
    revisoes = {}
    if caminho.exists():
        for numero, linha in enumerate(caminho.read_text(encoding='utf-8').splitlines(), 1):
            try:
                item = json.loads(linha)
                if item['schema'] != 'trajetoria_humana_v1':
                    raise ValueError('schema incompatível')
                revisoes[item['imagem']] = item
            except (ValueError, KeyError) as erro:
                raise ValueError(f'Arquivo de revisão inválido na linha {numero}: {erro}') from erro
    return revisoes


def montar_revisao(registro, status, pontos, sha256, sugestao=None):
    """Só chamada na confirmação explícita; sem inferência de visibilidade."""
    pts = validar_anotacao(status, pontos, int(registro['largura']), int(registro['altura']))
    assistido = bool(sugestao and sugestao['pontos_px'] and pts)
    origem = 'humano'
    if assistido:
        iniciais = sorted(sugestao['pontos_px'], key=lambda p: p[1])
        origem = 'opencv_confirmado' if pts == iniciais else 'opencv_corrigido'
    item = {**registro, 'schema': 'trajetoria_humana_v1', 'sha256': sha256,
            'revisado_utc': datetime.now(timezone.utc).isoformat(),
            'visibilidade': status, 'pontos_px': pts, 'origem_rotulo': origem,
            'sugestao_automatica': assistido, 'confirmacao_humana': True}
    if assistido:
        item['sugestao'] = sugestao
    return item


def proxima_pendente(registros, revisoes, indice):
    for deslocamento in range(1, len(registros) + 1):
        candidato = (indice + deslocamento) % len(registros)
        if registros[candidato]['imagem'] not in revisoes:
            return candidato
    return None


def referencia_anterior(registro, revisoes):
    """Apenas revisão humana anterior do mesmo vídeo, com até dois segundos."""
    candidatos = [r for r in revisoes.values()
                  if r['video_origem'] == registro['video_origem']
                  and r['largura'] == registro['largura'] and r['altura'] == registro['altura']
                  and r['visibilidade'] in {'visivel', 'parcial'} and len(r['pontos_px']) >= 2
                  and 0 < float(registro['timestamp']) - float(r['timestamp']) <= 2.]
    return max(candidatos, key=lambda r: float(r['timestamp'])) if candidatos else None


def selecionar_lote(registros, revisoes, limite, videos_permitidos):
    """Distribui o orçamento por vídeo, afastando frames das revisões existentes."""
    if limite < 1:
        raise ValueError('O lote precisa ter ao menos uma imagem')
    grupos = {}
    referencias = {}
    for video in sorted(set(videos_permitidos)):
        grupos[video] = [r for r in registros if r['video_origem'] == video and r['imagem'] not in revisoes]
        referencias[video] = [float(r['timestamp']) for r in revisoes.values() if r['video_origem'] == video]
    escolhidos = []
    while len(escolhidos) < limite:
        houve_escolha = False
        for video, candidatos in grupos.items():
            if not candidatos or len(escolhidos) >= limite:
                continue
            refs = referencias[video]
            if refs:
                escolhido = max(candidatos, key=lambda r: (
                    min(abs(float(r['timestamp']) - t) for t in refs), -float(r['timestamp'])))
            else:
                escolhido = min(candidatos, key=lambda r: float(r['timestamp']))
            escolhidos.append(escolhido)
            candidatos.remove(escolhido)
            refs.append(float(escolhido['timestamp']))
            houve_escolha = True
        if not houve_escolha:
            break
    return escolhidos


def preparar_lote(registros, revisoes, limite, videos_permitidos, caminho):
    """Congela a seleção em arquivo separado; reabrir continua o mesmo lote."""
    caminho = Path(caminho)
    if caminho.exists():
        plano = json.loads(caminho.read_text(encoding='utf-8'))
        if plano.get('schema') != 'lote_revisao_v1' or plano.get('limite') != limite:
            raise ValueError('Plano de lote incompatível; escolha outro --plano-lote')
        meta = {r['imagem']: r for r in registros}
        escolhidos = []
        for r in plano['registros']:
            if r['imagem'] not in meta or meta[r['imagem']] != r:
                raise ValueError(f'Metadados do lote mudaram: {r["imagem"]}')
            if r['video_origem'] not in videos_permitidos:
                raise ValueError('Vídeo do lote não pertence ao treino/validação atual')
            escolhidos.append(r)
        return escolhidos
    escolhidos = selecionar_lote(registros, revisoes, limite, videos_permitidos)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open('x', encoding='utf-8') as arquivo:
        json.dump({'schema': 'lote_revisao_v1', 'limite': limite,
                   'criterio': 'equilibrio_por_video_e_distancia_temporal',
                   'criado_utc': datetime.now(timezone.utc).isoformat(),
                   'registros': escolhidos, 'rotulos_gerados': False}, arquivo, indent=2, ensure_ascii=False)
    return escolhidos


def abrir_interface(registros, caminhos, saida, preprocessamento='normalizado'):
    import tkinter as tk
    from tkinter import messagebox

    revisoes = carregar_revisoes(saida)
    janela = tk.Tk()
    janela.title('Rotulagem assistida por OpenCV — confirme cada imagem')
    indice = next((i for i, r in enumerate(registros) if r['imagem'] not in revisoes), 0)
    pontos, atual = [], {}
    status = tk.StringVar(value='')
    info = tk.StringVar()
    aviso = tk.StringVar()
    tk.Label(janela, textvariable=info).pack()
    tk.Label(janela, text='Ciano: sugestão não confirmada | Vermelho: edição ou revisão salva').pack()
    tk.Label(janela, text='Arraste pontos para corrigir | Clique para adicionar | Botão direito para remover').pack()
    tk.Label(janela, textvariable=aviso, wraplength=600).pack()
    altura_canvas = max(220, min(700, janela.winfo_screenheight() - 260))
    canvas = tk.Canvas(janela, width=420, height=altura_canvas, background='#333333')
    canvas.pack()
    barra = tk.Frame(janela)
    barra.pack()
    for valor in ['visivel', 'parcial', 'ausente', 'ambiguo']:
        tk.Radiobutton(barra, text=valor, variable=status, value=valor).pack(side='left')

    def redesenhar():
        canvas.delete('pontos')
        coords = [(x * atual['escala_x'], y * atual['escala_y']) for x, y in sorted(pontos, key=lambda p: p[1])]
        proposta = atual.get('sugestao') or {}
        cor = 'cyan' if (atual.get('nao_confirmado') and pontos == proposta.get('pontos_px')) else 'red'
        for x, y in coords:
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=cor, tags='pontos')
        if len(coords) > 1:
            canvas.create_line(*[v for p in coords for v in p], fill=cor, width=2, tags='pontos')

    def atualizar_tratada(modo):
        _, tratada = preparar_imagem(atual['imagem'], modo)
        tamanho = (round(atual['largura'] * atual['escala_x']), round(atual['altura'] * atual['escala_y']))
        tratada = cv2.resize(tratada, tamanho, interpolation=cv2.INTER_AREA)
        ok, png = cv2.imencode('.png', tratada)
        if not ok:
            raise ValueError('Falha ao preparar a visualização tratada')
        atual['foto_tratada'] = tk.PhotoImage(data=base64.b64encode(png).decode('ascii'))
        atual['modo_tratamento'] = modo
        if atual['mostrando_tratada']:
            canvas.itemconfigure(atual['item_imagem'], image=atual['foto_tratada'])

    def calcular_sugestao(modo=None):
        try:
            modo = modo or preprocessamento
            if modo != atual.get('modo_tratamento'):
                atualizar_tratada(modo)
            referencia = referencia_anterior(registros[indice], revisoes)
            sugestao = sugerir_linha(atual['imagem'], referencia=referencia['pontos_px'] if referencia else None,
                                     preprocessamento=modo)
            atual['sugestao'] = {'versao': VERSAO, 'metodo': sugestao.metodo,
                                 'preprocessamento': sugestao.preprocessamento,
                                 'pontos_px': [p[:] for p in sugestao.pontos]}
            if referencia:
                atual['sugestao']['referencia'] = {k: referencia[k] for k in ['imagem', 'timestamp', 'sha256']}
            pontos[:] = [p[:] for p in sugestao.pontos]
            atual['nao_confirmado'] = True
            temporal = ' Usa como apoio a revisão anterior do mesmo vídeo.' if referencia else ''
            aviso.set(f'{len(pontos)} pontos sugeridos. Tratamento: {modo}. ' + sugestao.aviso + temporal +
                      ' Escolha a visibilidade e confirme para salvar.')
        except (ValueError, cv2.error) as erro:
            atual['sugestao'] = None
            pontos.clear()
            aviso.set(f'Não foi possível sugerir: {erro}. Você pode marcar manualmente.')

    def mudou():
        return pontos != atual['pontos_iniciais'] or status.get() != atual['status_inicial']

    def mostrar():
        registro = registros[indice]
        caminho = caminhos[registro['imagem']]
        bruto = caminho.read_bytes()
        imagem = cv2.imdecode(np.frombuffer(bruto, dtype=np.uint8), cv2.IMREAD_COLOR)
        if imagem is None:
            raise ValueError(f'Imagem ilegível: {caminho}')
        h, w = imagem.shape[:2]
        if (w, h) != (int(registro['largura']), int(registro['altura'])):
            raise ValueError(f'Resolução divergente: {caminho}')
        hash_atual = hashlib.sha256(bruto).hexdigest()
        anterior = revisoes.get(registro['imagem'])
        if anterior and anterior['sha256'] != hash_atual:
            raise ValueError(f'Imagem mudou desde a revisão: {caminho}')
        fator = min(420 / w, altura_canvas / h)
        pequena = cv2.resize(imagem, (round(w * fator), round(h * fator)), interpolation=cv2.INTER_AREA)
        ok, png = cv2.imencode('.png', pequena)
        if not ok:
            raise ValueError('Falha ao preparar a imagem para revisão')
        foto = tk.PhotoImage(data=base64.b64encode(png).decode('ascii'))
        atual.update(largura=w, altura=h, escala_x=pequena.shape[1] / w,
                     escala_y=pequena.shape[0] / h, foto=foto, sha256=hash_atual, imagem=imagem,
                     foto_tratada=None, mostrando_tratada=False,
                     sugestao=None, nao_confirmado=False, arraste=None)
        canvas.delete('all')
        atual['item_imagem'] = canvas.create_image(0, 0, image=foto, anchor='nw')
        atualizar_tratada(preprocessamento)
        if anterior:
            pontos[:] = [p[:] for p in anterior['pontos_px']]
            atual['sugestao'] = anterior.get('sugestao')
            status.set(anterior['visibilidade'])
            aviso.set('Revisão já salva: preservada. Use Próxima pendente para continuar.')
        else:
            status.set('')
            calcular_sugestao()
        atual['pontos_iniciais'] = [p[:] for p in pontos]
        atual['status_inicial'] = status.get()
        info.set(f'{indice + 1}/{len(registros)} | {registro["imagem"]} | t={registro["timestamp"]} s | '
                 f'{"REVISADO" if anterior else "PENDENTE"}')
        redesenhar()

    def ponto_proximo(evento):
        distancias = [((x * atual['escala_x'] - evento.x) ** 2 +
                       (y * atual['escala_y'] - evento.y) ** 2, i) for i, (x, y) in enumerate(pontos)]
        if distancias:
            distancia, i = min(distancias)
            if distancia <= 12 ** 2:
                return i
        return None

    def clicar(evento):
        perto = ponto_proximo(evento)
        if perto is not None:
            atual['arraste'] = perto
            return
        x, y = int(evento.x / atual['escala_x']), int(evento.y / atual['escala_y'])
        if 0 <= x < atual['largura'] and 0 <= y < atual['altura']:
            pontos.append([x, y])
            atual['arraste'] = len(pontos) - 1
            redesenhar()

    def arrastar(evento):
        i = atual.get('arraste')
        if i is not None:
            x = min(atual['largura'] - 1, max(0, int(evento.x / atual['escala_x'])))
            y = min(atual['altura'] - 1, max(0, int(evento.y / atual['escala_y'])))
            pontos[i] = [x, y]
            redesenhar()

    def soltar(evento):
        atual['arraste'] = None

    def remover(evento):
        if pontos:
            perto = ponto_proximo(evento)
            pontos.pop(perto if perto is not None else -1)
            atual['arraste'] = None
            redesenhar()

    def limpar():
        pontos.clear()
        atual['arraste'] = None
        redesenhar()

    def recalcular(modo=None):
        if (pontos or status.get()) and not messagebox.askyesno('Recalcular sugestão',
                'Substituir os pontos na tela por uma nova sugestão? A revisão salva será preservada até você confirmar novamente.'):
            return
        calcular_sugestao(modo)
        status.set('')
        redesenhar()

    def alternar_imagem():
        atual['mostrando_tratada'] = not atual['mostrando_tratada']
        foto = atual['foto_tratada'] if atual['mostrando_tratada'] else atual['foto']
        canvas.itemconfigure(atual['item_imagem'], image=foto)

    def salvar():
        nonlocal indice
        try:
            registro = registros[indice]
            item = montar_revisao(registro, status.get(), pontos, atual['sha256'], atual.get('sugestao'))
            # Append preserva as revisões; a última por imagem é a vigente.
            saida.parent.mkdir(parents=True, exist_ok=True)
            with saida.open('a', encoding='utf-8') as arquivo:
                arquivo.write(json.dumps(item, ensure_ascii=False) + '\n')
                arquivo.flush()
            revisoes[registro['imagem']] = item
            proximo = proxima_pendente(registros, revisoes, indice)
            if proximo is not None:
                indice = proximo
            else:
                messagebox.showinfo('Revisão', 'Todas as imagens desta seleção foram revisadas e salvas. Isso não inicia o treinamento.')
            mostrar()
        except (ValueError, OSError) as erro:
            messagebox.showerror('Não foi possível salvar', str(erro))

    def mover(delta, pendente=False):
        nonlocal indice
        if mudou() and not messagebox.askyesno('Alterações não salvas', 'Descartar alterações desta imagem?'):
            return
        if pendente:
            proximo = proxima_pendente(registros, revisoes, indice)
            if proximo is None:
                messagebox.showinfo('Revisão', 'Não há imagens pendentes nesta seleção.')
                return
            indice = proximo
        else:
            indice = max(0, min(len(registros) - 1, indice + delta))
        mostrar()

    botoes = tk.Frame(janela)
    botoes.pack()
    for texto, acao in [('Anterior', lambda: mover(-1)), ('Limpar pontos', limpar),
                        ('Confirmar e avançar', salvar), ('Pular sem salvar', lambda: mover(1))]:
        tk.Button(botoes, text=texto, command=acao).pack(side='left')
    adicionais = tk.Frame(janela)
    adicionais.pack()
    tk.Button(adicionais, text='Próxima pendente', command=lambda: mover(1, pendente=True)).pack(side='left')
    tk.Button(adicionais, text='Recalcular sugestão', command=recalcular).pack(side='left')
    tk.Button(adicionais, text='Alternar original/tratada', command=alternar_imagem).pack(side='left')
    tk.Button(adicionais, text='Tentar sem correção', command=lambda: recalcular('legado')).pack(side='left')
    def fechar():
        if not mudou() or messagebox.askyesno('Alterações não salvas', 'Fechar e descartar alterações desta imagem?'):
            janela.destroy()
    janela.protocol('WM_DELETE_WINDOW', fechar)
    canvas.bind('<Button-1>', clicar)
    canvas.bind('<B1-Motion>', arrastar)
    canvas.bind('<ButtonRelease-1>', soltar)
    canvas.bind('<Button-3>', remover)
    mostrar()
    janela.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=RAIZ / 'dataset_pista')
    parser.add_argument('--manifesto', type=Path, default=RAIZ / 'dataset_pista/resultados/estudo_01/manifesto.json')
    parser.add_argument('--saida', type=Path, default=RAIZ / 'dataset_pista/rotulos/revisoes.jsonl')
    selecao = parser.add_mutually_exclusive_group()
    selecao.add_argument('--todos', action='store_true', help='revisar todos os registros (padrão)')
    selecao.add_argument('--amostras', action='store_true', help='rever somente as 45 amostras do estudo')
    selecao.add_argument('--lote', type=int, metavar='N', help='revisar só N imagens novas de treino/validação')
    parser.add_argument('--plano-lote', type=Path, help='arquivo de seleção para retomar o mesmo lote')
    parser.add_argument('--preprocessamento', choices=['normalizado', 'legado'], default='normalizado',
                        help='tratamento para gerar sugestões; padrão: corrigir iluminação local')
    args = parser.parse_args()
    if args.lote is not None and args.lote < 1:
        parser.error('--lote deve ser positivo')
    if args.plano_lote is not None and args.lote is None:
        parser.error('--plano-lote exige --lote N')
    with (args.dataset / 'metadados.csv').open(encoding='utf-8-sig', newline='') as arquivo:
        registros = list(csv.DictReader(arquivo, delimiter=';'))
    if args.amostras:
        manifesto = json.loads(args.manifesto.read_text(encoding='utf-8'))
        selecionados = {r['imagem'] for r in manifesto['amostras']}
        registros = [r for r in registros if r['imagem'] in selecionados]
        if len(registros) != len(selecionados):
            parser.error('As amostras do manifesto não correspondem ao CSV')
    if not registros or len({r['imagem'] for r in registros}) != len(registros):
        parser.error('Seleção vazia ou nomes repetidos no CSV')
    if args.lote is not None:
        from aprendizado.dataset_rotulado import DIVISAO
        revisoes = carregar_revisoes(args.saida)
        plano = args.plano_lote or args.saida.parent / 'lotes' / f'lote_{args.lote}.json'
        if (args.dataset / 'imagens').resolve() in plano.resolve().parents:
            parser.error('O plano do lote deve ficar fora da pasta de imagens')
        registros = preparar_lote(registros, revisoes, args.lote,
                                  DIVISAO['treino'] + DIVISAO['validacao'], plano)
        pendentes = sum(r['imagem'] not in revisoes for r in registros)
        print(f'Lote: {len(registros)} imagens; faltam {pendentes}. Plano: {plano}', flush=True)
        if not pendentes:
            print('Lote concluído. As marcações estão salvas; não é necessário revisar todos os frames.')
            return
    caminhos = {}
    for caminho in (args.dataset / 'imagens').rglob('*'):
        if caminho.is_file():
            if caminho.name in caminhos:
                parser.error(f'Nome de imagem duplicado: {caminho.name}')
            caminhos[caminho.name] = caminho
    if any(r['imagem'] not in caminhos for r in registros):
        parser.error('Faltam arquivos de imagem da seleção')
    saida = args.saida.resolve()
    if saida.suffix != '.jsonl' or (args.dataset / 'imagens').resolve() in saida.parents:
        parser.error('Use saída .jsonl fora da pasta de imagens')
    try:
        abrir_interface(registros, caminhos, saida, preprocessamento=args.preprocessamento)
    except Exception as erro:
        parser.exit(1, f'Não foi possível abrir a revisão: {erro}\nUse desktop/VNC na Raspberry Pi e Python com tkinter.\n')


if __name__ == '__main__':
    main()
