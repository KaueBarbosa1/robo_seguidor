"""Confere o ambiente da Raspberry Pi SEM mexer em motores: sistema, Python, bibliotecas, modelos de voz, câmera,
serial, áudio e Bluetooth. Cada linha termina em OK, AVISO ou FALTA, com o comando para corrigir.

    python tools/verificar_ambiente.py            # tudo
    python tools/verificar_ambiente.py --camera   # também tenta abrir a câmera e capturar 1 quadro (precisa da câmera)

Mande a saída para quem estiver ajudando: ela diz exatamente o que está faltando.
"""
import argparse
import importlib
import platform
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

resultado = {"OK": 0, "AVISO": 0, "FALTA": 0}


def linha(estado: str, texto: str, dica: str = "") -> None:
    resultado[estado] += 1
    print(f"[{estado:<5}] {texto}" + (f"\n         -> {dica}" if dica and estado != "OK" else ""))


def ler(caminho: str) -> str:
    try:
        return Path(caminho).read_text(errors="ignore").strip("\x00\n ")
    except OSError:
        return ""


def sistema() -> None:
    print("== Sistema ==")
    os_rel = {}
    for l in ler("/etc/os-release").splitlines():
        if "=" in l:
            k, v = l.split("=", 1)
            os_rel[k] = v.strip('"')
    print(f"         SO: {os_rel.get('PRETTY_NAME', platform.platform())} | kernel {platform.release()} | {platform.machine()}")
    modelo = ler("/proc/device-tree/model")
    print(f"         Placa: {modelo or 'não é uma Raspberry Pi (ou não foi possível ler)'}")
    rpi = Path("/etc/rpi-issue").exists()
    print(f"         Raspberry Pi OS (/etc/rpi-issue): {'sim' if rpi else 'não'}")
    v = sys.version_info
    linha("OK" if v >= (3, 10) else "FALTA", f"Python {v.major}.{v.minor}.{v.micro}", "o projeto precisa de Python 3.10 ou mais novo")
    import config as cfg
    if not rpi and cfg.FONTE_IMAGEM == "csi":
        linha("AVISO", "Não é Raspberry Pi OS: pacotes da câmera (python3-picamera2, rpicam-apps) vêm do repositório da Raspberry Pi",
              "confira com:  apt-cache policy python3-picamera2   (se não houver candidato, use o Raspberry Pi OS)")


def bibliotecas() -> None:
    print("\n== Bibliotecas Python ==")
    itens = [("numpy", "numpy", True), ("cv2", "opencv (cv2)", True), ("serial", "pyserial", True),
             ("sounddevice", "sounddevice", True), ("scipy", "scipy", True), ("joblib", "joblib", True),
             ("sklearn", "scikit-learn", True)]
    import config as cfg
    if cfg.FONTE_IMAGEM == "csi":
        itens.append(("picamera2", "picamera2 (câmera CSI)", True))
    for modulo, nome, _ in itens:
        try:
            m = importlib.import_module(modulo)
            ver = getattr(m, "__version__", "?")
            if modulo == "sklearn" and ver != "1.8.0":
                linha("AVISO", f"{nome} {ver}", "os modelos de voz foram salvos com a 1.8.0:  pip install scikit-learn==1.8.0")
            else:
                linha("OK", f"{nome} {ver}")
        except Exception as e:
            dica = {"picamera2": "sudo apt install -y python3-picamera2   (e crie o venv com --system-site-packages)",
                    "sounddevice": "sudo apt install -y libportaudio2 && pip install sounddevice",
                    "cv2": "pip install opencv-python-headless   (ou: sudo apt install python3-opencv)"}.get(modulo, "pip install -r requirements.txt")
            linha("FALTA", f"{nome}: {type(e).__name__}: {e}", dica)


def voz() -> None:
    print("\n== Voz ==")
    import config as cfg
    for caminho in (cfg.MODELO_MISTURA, cfg.MODELO_MLP):
        p = Path(caminho)
        linha("OK" if p.exists() else "FALTA", f"{p.relative_to(RAIZ)} ({p.stat().st_size // 1024} KB)" if p.exists() else f"{p.name} ausente",
              "copie a pasta voz/modelo do projeto")
    try:
        from voz.mistura import carregar_pacote
        carregar_pacote(cfg.MODELO_MISTURA)
        linha("OK", "pacote da mistura lê sem PyTorch")
    except Exception as e:
        linha("FALTA", f"não consegui ler o modelo da mistura: {type(e).__name__}: {e}", "confira a versão do scikit-learn e o arquivo")


def audio() -> None:
    print("\n== Áudio ==")
    try:
        import sounddevice as sd
        entradas = [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        if entradas:
            linha("OK", "entradas de áudio: " + "; ".join(f"[{i}] {n}" for i, n in entradas))
        else:
            linha("AVISO", "nenhuma entrada de áudio", "pareie o headset Bluetooth (docs/03) e rode  python tools/testar_microfone.py")
    except Exception as e:
        linha("AVISO", f"não consegui listar o áudio: {e}", "sudo apt install -y libportaudio2")


def serial_() -> None:
    print("\n== Serial (Arduino) ==")
    import glob
    import config as cfg
    portas = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyAMA*"))
    print(f"         portas encontradas: {portas or 'nenhuma'}  | SERIAL_PORTA em config.py: {cfg.SERIAL_PORTA} @ {cfg.SERIAL_BAUD}")
    if cfg.SERIAL_PORTA in portas:
        linha("OK", f"{cfg.SERIAL_PORTA} existe")
    else:
        linha("AVISO", f"{cfg.SERIAL_PORTA} não existe agora",
              "ligação Pi<->Arduino ainda indefinida: ligue o Arduino por USB ou ajuste SERIAL_PORTA; sem ele: python main.py --sem-arduino")
    import grp
    import os
    try:
        grupos = {grp.getgrgid(g).gr_name for g in os.getgroups()}
        faltam = {"dialout", "audio", "video"} - grupos
        tem = ", ".join(sorted(grupos & {"dialout", "audio", "video"})) or "nenhum dos três"
        linha("OK" if not faltam else "AVISO", f"grupos do usuário (dialout/audio/video): {tem}",
              "sudo usermod -aG dialout,audio,video $USER   (depois saia e entre na sessão)")
    except Exception:
        pass


def camera(tentar_abrir: bool) -> None:
    import config as cfg
    if cfg.FONTE_IMAGEM != "csi":
        print("\n== Câmera ==")
        print(f"         FONTE_IMAGEM = {cfg.FONTE_IMAGEM!r}: a OV7670 está no Arduino; a imagem só chega com o firmware gravado.")
        print("         Teste: python tools/ver_camera.py --salvar foto.png   (roteiro: docs/02_bringup_camera.md)")
        return
    print("\n== Câmera CSI ==")
    try:
        from picamera2 import Picamera2
    except ImportError:
        linha("FALTA", "picamera2 não instalado", "sudo apt install -y python3-picamera2")
        return
    try:
        info = Picamera2.global_camera_info()
    except Exception as e:
        linha("FALTA", f"não consegui consultar as câmeras: {type(e).__name__}: {e}", "rpicam-hello --list-cameras")
        return
    if not info:
        linha("FALTA", "nenhuma câmera detectada",
              "Pi desligada: confira o cabo (Pi 5 = conector mini de 22 pinos; a câmera de 15 pinos precisa do cabo adaptador). "
              "Se o cabo estiver certo: dtoverlay=ov5647 em /boot/firmware/config.txt e reiniciar")
        return
    for c in info:
        linha("OK", f"câmera detectada: {c.get('Model', '?')} (local {c.get('Location', '?')})")
    if tentar_abrir:
        from visao.camera_csi import CameraCSI
        cam = CameraCSI()
        try:
            cam.iniciar()
            q = cam.proximo_quadro(cam.id_atual(), 5.0)
            if q is None:
                linha("FALTA", "a câmera abriu mas não entregou quadro em 5 s", "rpicam-hello --list-cameras")
            else:
                img = q[1]
                linha("OK", f"quadro recebido: {img.shape}, brilho médio {img.mean():.0f}, contraste (máx-mín) {int(img.max()) - int(img.min())}")
        except Exception as e:
            linha("FALTA", f"erro ao abrir a câmera: {type(e).__name__}: {e}", "veja docs/05_camera_csi.md")
        finally:
            cam.parar()
    else:
        print("         (use --camera para abrir a câmera e capturar um quadro)")


def bluetooth() -> None:
    import config as cfg
    import grp
    import os
    import shutil
    import subprocess
    print("\n== Bluetooth (controle pelo celular) ==")
    if not cfg.REMOTO_BT_ATIVO:
        print("         REMOTO_BT_ATIVO = False em config.py: servidor Bluetooth desligado.")
        return
    try:
        importlib.import_module("dbus_fast")
        linha("OK", "dbus-fast instalado")
    except Exception as e:
        linha("FALTA", f"dbus-fast: {type(e).__name__}: {e}", "pip install dbus-fast   (dentro do venv)")
    if shutil.which("systemctl"):
        r = subprocess.run(["systemctl", "is-active", "bluetooth"], capture_output=True, text=True, timeout=10)
        ativo = r.stdout.strip() == "active"
        linha("OK" if ativo else "FALTA", f"serviço bluetooth: {r.stdout.strip() or 'desconhecido'}",
              "sudo apt install -y bluez && sudo systemctl enable --now bluetooth")
    else:
        linha("AVISO", "systemctl não encontrado: não consegui ver se o bluetoothd está ativo")
    if shutil.which("bluetoothctl"):
        r = subprocess.run(["bluetoothctl", "show"], capture_output=True, text=True, timeout=10)
        txt = r.stdout
        if "Controller" not in txt:
            linha("FALTA", "nenhum adaptador Bluetooth encontrado pelo bluetoothctl", "rfkill list; sudo rfkill unblock bluetooth; bluetoothctl power on")
        else:
            for chave, dica in (("Powered: yes", "bluetoothctl power on"), ("Pairable: yes", "bluetoothctl pairable on")):
                linha("OK" if chave in txt else "AVISO", f"adaptador: {chave.replace(': yes', '')} {'sim' if chave in txt else 'não'}", dica)
            print(f"         Discoverable: {'yes' if 'Discoverable: yes' in txt else 'no'} (só precisa ficar 'yes' na hora de parear)")
    else:
        linha("AVISO", "bluetoothctl não encontrado", "sudo apt install -y bluez")
    try:
        grupos = {grp.getgrgid(g).gr_name for g in os.getgroups()}
        linha("OK" if "bluetooth" in grupos else "AVISO", "usuário no grupo bluetooth" if "bluetooth" in grupos else "usuário fora do grupo bluetooth",
              "sudo usermod -aG bluetooth $USER   (depois saia e entre na sessão)")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", action="store_true", help="abre a câmera e captura 1 quadro")
    a = ap.parse_args()
    sistema()
    bibliotecas()
    for etapa in (voz, audio, serial_, bluetooth):
        try:
            etapa()
        except Exception as e:
            linha("AVISO", f"{etapa.__name__}: verificação falhou ({type(e).__name__}: {e})")
    camera(a.camera)
    print(f"\nResumo: {resultado['OK']} OK, {resultado['AVISO']} aviso(s), {resultado['FALTA']} FALTA")
    return 1 if resultado["FALTA"] else 0


if __name__ == "__main__":
    sys.exit(main())
