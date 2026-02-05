from __future__ import annotations
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torchvision import datasets, transforms
from flask import Flask, render_template_string
from flask_socketio import SocketIO
import threading
import time
import base64
from io import BytesIO
from PIL import Image

# --- VR表示用HTML (Softmax Before/After 可視化版) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI Decision Inspector VR</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="https://aframe.io/releases/1.4.0/aframe.min.js"></script>
</head>
<body>
    <a-scene>
        <a-sky color="#050505"></a-sky>
        <a-plane position="0 0 0" rotation="-90 0 0" width="50" height="50" color="#111"></a-plane>

        <a-entity position="-6 2.5 -4" rotation="0 30 0">
            <a-text value="INPUT SOURCE (X)" align="center" width="6" position="0 2.2 0"></a-text>
            <a-image id="input-src-img" width="3.5" height="3.5"></a-image>
        </a-entity>

        <a-entity position="0 3.5 -6">
            <a-text id="weight-label" value="ACTIVE WEIGHT PATTERN" align="center" color="cyan" scale="1.2 1.2 1.2" position="0 2.5 0"></a-text>
            <a-entity id="graph-container" position="-1.4 0 0"></a-entity>
        </a-entity>

        <a-entity id="comparison-panel" position="6 2.5 -3.5" rotation="0 -45 0">
            <a-plane width="6.5" height="6" color="#222" opacity="0.95" position="0 0 -0.05"></a-plane>
            <a-text value="DECISION PROCESS (Softmax Analysis)" position="0 2.6 0" align="center" width="7" color="yellow"></a-text>
            
            <a-entity position="-1.5 0.5 0">
                <a-text value="[BEFORE] LOGITS" align="center" width="5" color="#FF6666" position="0 1.5 0"></a-text>
                <a-text value="(Raw Calculation)" align="center" width="3" color="#AAA" position="0 1.2 0"></a-text>
                <a-text id="logit-text" value="Waiting..." align="left" width="4.5" font="monospace" position="-1.2 -0.5 0"></a-text>
            </a-entity>

            <a-entity position="1.5 0.5 0">
                <a-text value="[AFTER] SOFTMAX" align="center" width="5" color="#66FF66" position="0 1.5 0"></a-text>
                <a-text value="(Probability %)" align="center" width="3" color="#AAA" position="0 1.2 0"></a-text>
                <a-text id="softmax-text" value="Waiting..." align="left" width="4.5" font="monospace" position="-0.8 -0.5 0"></a-text>
            </a-entity>

            <a-entity position="0 -2.2 0">
                <a-text id="judgment-text" value="ANALYZING..." align="center" scale="1.8 1.8 1.8"></a-text>
            </a-entity>
        </a-entity>

        <a-camera position="0 2 5"><a-cursor color="white" scale="0.1 0.1 0.1"></a-cursor></a-camera>
    </a-scene>

    <script>
        const socket = io();
        const weightLabel = document.getElementById('weight-label');
        const container = document.getElementById('graph-container');
        const logitText = document.getElementById('logit-text');
        const softmaxText = document.getElementById('softmax-text');
        const judgmentText = document.getElementById('judgment-text');
        const inputImg = document.getElementById('input-src-img');

        // 重み表示用の3Dバー初期化
        const bars = [];
        for (let y = 0; y < 28; y++) {
            for (let x = 0; x < 28; x++) {
                const bar = document.createElement('a-box');
                bar.setAttribute('width', '0.08'); bar.setAttribute('depth', '0.08');
                bar.setAttribute('position', `${x * 0.1} ${(27-y) * 0.1 - 1.4} 0`);
                container.appendChild(bar);
                bars.push(bar);
            }
        }

        socket.on('update_data', (data) => {
            // 画像更新
            inputImg.setAttribute('src', 'data:image/png;base64,' + data.image);
            weightLabel.setAttribute('value', `WEIGHT PATTERN FOR LABEL: ${data.label}`);

            // Logits (Before) vs Softmax (After) の文字列生成
            let lStr = ""; let sStr = "";
            const logits = data.logits[0];
            const probs = data.probs[0];
            
            for(let i=0; i<10; i++) {
                const prefix = (i === data.prediction) ? ">" : " ";
                // Logitは生の数値（正負あり）
                lStr += `${prefix}[${i}]: ${logits[i].toFixed(2).padStart(6, ' ')}\\n`;
                // Softmaxは%表記
                sStr += `${prefix}[${i}]: ${(probs[i]*100).toFixed(1).padStart(5, ' ')}%\\n`;
            }
            logitText.setAttribute('value', lStr);
            softmaxText.setAttribute('value', sStr);

            // 最終判定の更新
            const isCorrect = data.prediction === data.label;
            judgmentText.setAttribute('value', `PRED: ${data.prediction} | ACTUAL: ${data.label}`);
            judgmentText.setAttribute('color', isCorrect ? "#0F0" : "#F00");

            // 重みバー（現在学習/検証中のラベルに対応するもの）の更新
            const weights = data.weights.flat();
            bars.forEach((bar, i) => {
                const w = weights[i];
                const h = Math.abs(w) * 15 + 0.01;
                bar.setAttribute('height', h);
                bar.setAttribute('color', w >= 0 ? "#4CC3D9" : "#FF6B6B");
                bar.setAttribute('position', {x: (i%28)*0.1 - 1.4, y: (27-Math.floor(i/28))*0.1 - 1.4, z: w>=0?h/2:-h/2});
            });
        });
    </script>
</body>
</html>
"""

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# 単層ニューラルネットワーク
model = nn.Linear(784, 10)
optimizer = optim.SGD(model.parameters(), lr=0.03)
criterion = nn.CrossEntropyLoss()

def train_loop():
    train_loader = torch.utils.data.DataLoader(
        datasets.MNIST('./data', train=True, download=True, transform=transforms.ToTensor()),
        batch_size=1, shuffle=True)

    for epoch in range(5):
        for images, labels in train_loader:
            optimizer.zero_grad()
            input_flat = images.view(-1, 784)
            
            # [演算1] Logits (生の出力)
            logits = model(input_flat)
            
            # [演算2] Softmax (確率への変換)
            probs = F.softmax(logits, dim=1)
            
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            _, predicted = torch.max(logits.data, 1)

            # VR送信用の画像処理
            img_raw = (images[0][0].numpy() * 255).astype('uint8')
            pil_img = Image.fromarray(img_raw)
            buff = BytesIO()
            pil_img.save(buff, format="PNG")
            img_str = base64.b64encode(buff.getvalue()).decode()

            # 現在の正解ラベルに対応する重みを動的に抽出
            current_label = int(labels[0])
            weights_to_send = model.weight.data[current_label].detach().cpu().numpy().reshape(28, 28).tolist()

            # クライアントへ送信
            socketio.emit('update_data', {
                'image': img_str,
                'logits': logits.detach().cpu().numpy().tolist(),
                'probs': probs.detach().cpu().numpy().tolist(),
                'weights': weights_to_send,
                'prediction': int(predicted[0]),
                'label': current_label
            })
            
            # 視認性のためのディレイ
            time.sleep(1.2)

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    threading.Thread(target=train_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5006)