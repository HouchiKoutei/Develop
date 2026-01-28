import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import time

# --- ネットワーク設定 ---
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

model = nn.Linear(784, 10)
optimizer = optim.SGD(model.parameters(), lr=0.05)
criterion = nn.CrossEntropyLoss()

# --- 学習プロセス (別スレッドで実行) ---
def train_loop():
    train_loader = torch.utils.data.DataLoader(
        datasets.MNIST('./data', train=True, download=True, transform=transforms.ToTensor()),
        batch_size=32, shuffle=True)

    print("学習スレッド開始。Questからの接続を待機中...")
    
    for epoch in range(5):
        for batch_idx, (images, labels) in enumerate(train_loader):
            optimizer.zero_grad()
            outputs = model(images.view(-1, 784))
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            if batch_idx % 10 == 0:
                # 精度(自信)の計算
                _, predicted = torch.max(outputs.data, 1)
                accuracy = (predicted == labels).sum().item() / labels.size(0)
                
                # 重みデータ(数字の3用)をVRへ送信
                weights = model.weight.data[3].numpy().reshape(28, 28).tolist()
                socketio.emit('update_data', {
                    'weights': weights,
                    'loss': float(loss),
                    'accuracy': accuracy,
                    'step': batch_idx + (epoch * len(train_loader))
                })
                time.sleep(0.1) # VR側の描画が追いつくよう少し待機

@app.route('/')
def index():
    return "Server is running. Connect via Quest 3 browser to /vr"

if __name__ == '__main__':
    threading.Thread(target=train_loop).start()
    # PCのIPアドレスで公開（Questからアクセス可能にする）
    socketio.run(app, host='0.0.0.0', port=5000)
