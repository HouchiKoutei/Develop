from __future__ import annotations
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
from flask import Flask, render_template_string
from flask_socketio import SocketIO
import threading
import time
import socket
import base64
from io import BytesIO
from PIL import Image

# --- VR表示用HTML (全部入り・頭上高密度版) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI Full Inspector VR</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="https://aframe.io/releases/1.4.0/aframe.min.js"></script>
</head>
<body>
    <a-scene>
        <a-sky color="#020202"></a-sky>
        <a-plane position="0 0 0" rotation="-90 0 0" width="30" height="30" color="#111"></a-plane>

        <a-entity position="-6 2.5 -3" rotation="0 45 0">
            <a-text value="INPUT (X)" position="0 2.2 0" align="center" width="8"></a-text>
            <a-image id="input-src-img" width="3.5" height="3.5"></a-image>
        </a-entity>

        <a-entity position="0 5.5 1" rotation="75 0 0">
            <a-text value="REAL-TIME CALCULATION (X * W for Node 3)" position="0 3 0" align="center" width="5" color="yellow"></a-text>
            <a-text id="calc-list-text" value="Loading..." align="center" width="2.2" color="#FFFFFF" font="monospace" wrapCount="90"></a-text>
        </a-entity>

        <a-entity position="0 4.5 -5">
            <a-text value="WEIGHTS (W)" align="center" color="cyan" scale="2 2 2"></a-text>
            <a-text value="<-- MINUS(Back) | PLUS(Front) -->" position="0 -0.5 0" align="center" scale="0.8 0.8 0.8"></a-text>
        </a-entity>
        <a-entity id="graph-container" position="-1.4 2.5 -5"></a-entity>

        <a-entity position="5 2 -2" rotation="0 -60 0">
            <a-plane width="3.5" height="5" color="#000" opacity="0.9"></a-plane>
            <a-text value="OUTPUT (Y)" position="0 2.2 0.1" align="center" width="6"></a-text>
            
            <a-text id="result-text" value="Scores..." position="-1.5 0.8 0.1" color="#00FF00" width="5"></a-text>
            <a-text id="bias-text" value="Bias: --" position="-1.5 -1.2 0.1" color="#FFD700" width="5"></a-text>
            <a-text id="judgment-text" value="JUDGMENT" position="0 -2.0 0.1" scale="1.5 1.5 1.5" align="center"></a-text>
        </a-entity>

        <a-camera position="0 2 5"></a-camera>
    </a-scene>

    <script>
        const socket = io();
        const container = document.getElementById('graph-container');
        const inputImg = document.getElementById('input-src-img');
        const resultText = document.getElementById('result-text');
        const biasText = document.getElementById('bias-text');
        const judgmentText = document.getElementById('judgment-text');
        const calcListText = document.getElementById('calc-list-text');
        
        const bars = [];
        const labels = [];
        
        for (let y = 0; y < 28; y++) {
            for (let x = 0; x < 28; x++) {
                const bar = document.createElement('a-box');
                bar.setAttribute('width', '0.08');
                bar.setAttribute('depth', '0.08');
                bar.setAttribute('position', `${x * 0.1} ${ (27-y) * 0.1 - 1.35 } 0`);
                container.appendChild(bar);
                bars.push(bar);

                const txt = document.createElement('a-text');
                txt.setAttribute('scale', '0.12 0.12 0.12');
                txt.setAttribute('align', 'center');
                container.appendChild(txt);
                labels.push({el: txt, x: x*0.1, y: (27-y)*0.1 - 1.35});
            }
        }

        socket.on('update_data', (data) => {
            inputImg.setAttribute('src', 'data:image/png;base64,' + data.image);
            
            // 右側：スコア
            let outStr = "Scores:\\n";
            data.outputs[0].forEach((v, i) => {
                outStr += `${(i === data.pred ? ">" : " ")} [${i}]: ${v.toFixed(2).padStart(6)}\\n`;
            });
            resultText.setAttribute('value', outStr);
            biasText.setAttribute('value', `Bias (Node 3): ${data.bias.toFixed(5)}`);
            
            judgmentText.setAttribute('value', `PRED: ${data.pred}\\nACTUAL: ${data.label}`);
            judgmentText.setAttribute('color', data.pred === data.label ? "#0F0" : "#F00");

            // 頭上：全28行の計算プロセス（実際の値を代入）
            const flatX = data.input_raw.flat();
            const flatW = data.weights.flat();
            let fullMatrixStr = "";
            for(let r=0; r<5; r++) {
                let rowSum = 0;
                let rowTerms = `R${r.toString().padStart(2,'0')}: `;
                for(let c=0; c<28; c++) {
                    const i = r * 28 + c;
                    const val = flatX[i] * flatW[i];
                    rowSum += val;
                    rowTerms += `${flatX[i].toFixed(1)}*${flatW[i].toFixed(1)}+`;
                }
                fullMatrixStr += rowTerms.slice(0,-1) + ` = [${rowSum.toFixed(2)}]\\n`;
            }
            calcListText.setAttribute('value', fullMatrixStr);

            // 正面：重み更新
            const weights = data.weights.flat();
            bars.forEach((bar, i) => {
                const w = weights[i];
                const h = Math.abs(w) * 15 + 0.01;
                bar.setAttribute('height', h);
                bar.setAttribute('rotation', '90 0 0'); 
                const zPos = (w >= 0 ? h/2 : -h/2);
                bar.setAttribute('position', {x: labels[i].x, y: labels[i].y, z: zPos});
                bar.setAttribute('color', w >= 0 ? "#00AAFF" : "#FF3300");

                const r = Math.floor(i/28); const c = i%28;
                labels[i].el.setAttribute('value', `${w.toFixed(2)}`);
                labels[i].el.setAttribute('position', `${labels[i].x} ${labels[i].y} ${w >= 0 ? -h - 0.1 : h + 0.1}`);
            });
        });
    </script>
</body>
</html>
"""

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
model = nn.Linear(784, 10)
optimizer = optim.SGD(model.parameters(), lr=0.01)
criterion = nn.CrossEntropyLoss()

def train_loop():
    train_loader = torch.utils.data.DataLoader(
        datasets.MNIST('./data', train=True, download=True, transform=transforms.ToTensor()),
        batch_size=1, shuffle=True)
    step = 0
    correct_count = 0
    for epoch in range(5):
        for images, labels in train_loader:
            step += 1
            optimizer.zero_grad()
            input_flat = images.view(-1, 784)
            outputs = model(input_flat)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            _, predicted = torch.max(outputs.data, 1)
            if predicted == labels: correct_count += 1
            
            if step % 2 == 0:
                img_data = (images[0][0].numpy() * 255).astype('uint8')
                pil_img = Image.fromarray(img_data)
                buff = BytesIO()
                pil_img.save(buff, format="PNG")
                img_str = base64.b64encode(buff.getvalue()).decode()

                weights = model.weight.data[3].detach().cpu().numpy().reshape(28, 28).tolist()
                bias = float(model.bias.data[3])
                
                socketio.emit('update_data', {
                    'image': img_str,
                    'input_raw': images[0][0].numpy().tolist(), # Xの値
                    'weights': weights,
                    'bias': bias,
                    'outputs': outputs.detach().cpu().numpy().tolist(),
                    'pred': int(predicted[0]),
                    'label': int(labels[0]),
                    'accuracy': correct_count / step,
                    'step': step,
                    'loss': float(loss)
                })
                time.sleep(1.5)

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    local_ip = socket.gethostbyname(socket.gethostname())
    threading.Thread(target=train_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5006, ssl_context='adhoc')