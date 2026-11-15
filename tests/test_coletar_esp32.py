import csv
import json
from argparse import Namespace
from email.message import Message
from io import BytesIO

import cv2
import numpy as np
import pytest

from tools import coletar_esp32_cam as coletor
from tools.testar_esp32_cam import receber, receber_quadro
from visao.recorte_esp32 import RecorteESP32


class Resposta(BytesIO):
    status = 200

    def __init__(self, dados):
        super().__init__(dados)
        self.headers = Message()
        self.headers["Content-Type"] = "image/jpeg"
        self.headers["X-Frame-Age-Us"] = "25000"


class ReceptorSimulado:
    def __init__(self, *respostas):
        self.respostas = iter(respostas)

    def open(self, requisicao, timeout):
        return Resposta(next(self.respostas))


def jpeg(largura=320):
    imagem = np.zeros((240, largura, 3), np.uint8)
    imagem[:, :largura // 2] = 180
    ok, dados = cv2.imencode(".jpg", imagem)
    assert ok
    return dados.tobytes()


def test_recepcao_preserva_jpeg_e_interface_da_bancada():
    dados = jpeg()
    receptor = ReceptorSimulado(dados, dados, jpeg(160))
    q = receber_quadro(receptor, coletor.URL_PADRAO, 1)
    assert q.jpeg == dados and q.recepcao_utc.endswith("+00:00")
    img, http, idade, limite = receber(receptor, coletor.URL_PADRAO, 1)
    np.testing.assert_array_equal(img, q.imagem)
    assert idade == 25 and limite == 25 + http
    with pytest.raises(ValueError, match="320x240"):
        receber_quadro(receptor, coletor.URL_PADRAO, 1)


def test_coleta_grava_bytes_originais_e_registra_recuperacao(tmp_path, monkeypatch):
    dados = jpeg()
    receptor = ReceptorSimulado(dados, dados[:-2], dados)
    monkeypatch.setattr(coletor, "build_opener", lambda *_: receptor)
    monkeypatch.setattr(coletor, "esperar", lambda *_: True)
    saida = tmp_path / "sessao"
    args = Namespace(sem_janela=True, previa=False, saida=saida, url=coletor.URL_PADRAO, nota="curva",
                     duracao=None, quadros=2, intervalo=0., timeout=1.)
    recorte = RecorteESP32(10, 35, 160, 80, espelhar_v=True)
    coletor.executar(args, recorte)
    with (saida / "capturas.csv").open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    assert [r["status"] for r in linhas] == ["ok", "falha", "ok"]
    assert [r["quadro"] for r in linhas] == ["1", "", "2"]
    assert all((saida / r["jpeg"]).read_bytes() == dados for r in linhas if r["status"] == "ok")
    assert not list(saida.rglob("*.part"))
    manifesto = json.loads((saida / "sessao.json").read_text(encoding="utf-8"))
    assert manifesto["estado"] == "encerrada" and manifesto["quadros"] == 2 and manifesto["falhas"] == 1
    assert manifesto["previa"]["recorte"]["espelhar_v"] is True and manifesto["nota"] == "curva"
    with pytest.raises(FileExistsError):
        coletor.executar(args, recorte)


def test_recorte_orienta_antes_de_reduzir_e_nao_muda_imagem():
    imagem = np.zeros((240, 320, 3), np.uint8)
    imagem[:, 240:] = 200
    recorte = RecorteESP32(0, 50, 80, 40, espelhar_h=True)
    pequena = recorte.reduzir(recorte.orientar(imagem))
    assert pequena.shape == (40, 80) and np.all(pequena == 200)
    previa = coletor.montar_previa(imagem, recorte, "Quadro de teste")
    assert previa.shape == (296, 652, 3)
    assert np.all(previa[28:188, -320:] == 200) and np.all(imagem[:, :240] == 0)
    with pytest.raises(ValueError, match="2:1"):
        RecorteESP32(0, 200, 80, 50)
