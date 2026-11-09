import hashlib
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parent / 'models'
root.mkdir(exist_ok=True)
base = 'https://github.com/opencv/opencv_zoo/raw/main/models'
models = {
    'face_detection_yunet_2023mar.onnx': (
        f'{base}/face_detection_yunet/face_detection_yunet_2023mar.onnx',
        '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',
    ),
    'face_recognition_sface_2021dec.onnx': (
        f'{base}/face_recognition_sface/face_recognition_sface_2021dec.onnx',
        '0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79',
    ),
}
for name, (url, expected_hash) in models.items():
    dest = root / name
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == expected_hash:
        print(f'{name} déjà présent et vérifié')
        continue
    print(f'Téléchargement de {name}…', flush=True)
    with urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise RuntimeError(f'Empreinte SHA-256 invalide : {name}')
    dest.write_bytes(data)
print('Modèles prêts.')
