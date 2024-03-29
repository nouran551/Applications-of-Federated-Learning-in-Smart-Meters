# -*- coding: utf-8 -*-
"""Copy of Nour.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/19PrDwPNgWYKOOhrU7I8qw_Y_MSqjOuJ_

https://gist.github.com/saranshmanu/3e2807409a2838a3e221186ef5528bc7#file-federated_learning-ipynb
"""

from google.colab import drive
drive.mount('/content/drive')

!pip install syft==0.2.8

# Commented out IPython magic to ensure Python compatibility.
import syft as sy 

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import seaborn as sns
# %matplotlib inline

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
from syft.frameworks.torch.fl import utils

import random
import time
import json
import copy
import os
import glob

hook = sy.TorchHook(torch)
smart_meter1 = sy.VirtualWorker(hook, id="sm1")
smart_meter2 = sy.VirtualWorker(hook, id="sm2")
compute_nodes = [smart_meter1, smart_meter2]

class Parser:
    def __init__(self):
        self.epochs = 200
        self.lr = 0.001
        self.test_batch_size = 8                                                # number here is [A] and should be equal to [B]
        self.batch_size = 8
        self.log_interval = 10
        self.seed = 1
        self.no_cuda = False
    
args = Parser()
use_cuda = not args.no_cuda and torch.cuda.is_available()
torch.manual_seed(args.seed)
device = torch.device("cuda" if use_cuda else "cpu")
kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}
device

path='/content/drive/My Drive/GP | Smart Meter | CIC/Datasets'

data = pd.read_csv(path + "/sample_data_.csv")

data = data.drop(['Unnamed: 0','day'], axis = 1)
print(data[:])

# data --> [2:]
# target --> [only second column]

features = data.drop(['LCLid','energy_sum'], axis = 1)
features = features.to_numpy()  # inputs <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
target = data[['energy_sum']]
target = target.to_numpy()      # output <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

split_frac = 0.8
split_idx= int (len(features)*split_frac)
train_x,test_x = features[:split_idx], features[split_idx:]
train_y,test_y = target[:split_idx], target[split_idx:]

train_y = train_y.ravel()
test_y = test_y.ravel()

print("\t\t\t Feature shapes:")
print("Train set: \t\t{}\n".format(train_x.shape), "Test set: \t\t{}\n".format(test_x.shape))

train = TensorDataset(torch.from_numpy(train_x).float(), torch.from_numpy(train_y).float())
test = TensorDataset(torch.from_numpy(test_x).float(), torch.from_numpy(test_y).float())
train_loader = DataLoader(train, batch_size=args.batch_size, shuffle=True)
test_loader = DataLoader(test, batch_size=args.test_batch_size, shuffle=True)

class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.fc1 = nn.Linear(256, 128, bias=True)                                          # this number here is [C] and should be equal to [D]
        self.fc2 = nn.Linear(128, 64, bias=True)
        self.fc3 = nn.Linear(64, 32, bias=True)
        self.fc4 = nn.Linear(32, 16, bias=True)
        self.fc5 = nn.Linear(16, 8, bias=True)                                          # this number here is [B] and should be equal to [A]

    def forward(self, x):
        # print(x.shape)  # (8, 32) --> 1D vector of 8*32 = 256
        x = x.view(-1, 256)                                                     # this number here is [D] and should be equal to [C]
        x = F.leaky_relu(self.fc1(x))
        x = F.relu_(self.fc2(x))
        x = F.relu6(self.fc3(x))
        x = F.rrelu(self.fc4(x))
        x = torch.tanh(self.fc5(x)) #self.fc6(x)
        return x

"""Though data will be available offline for federated learning with the workers but here we are sending the data over to the workers for training with ondevice capability"""

remote_dataset = (list(), list())
train_distributed_dataset = []

for batch_idx, (data,target) in enumerate(train_loader):
    data = data.send(compute_nodes[batch_idx % len(compute_nodes)])
    target = target.send(compute_nodes[batch_idx % len(compute_nodes)])
    remote_dataset[batch_idx % len(compute_nodes)].append((data, target))

smart_meter1_model = Net()
smart_meter2_model = Net()
smart_meter1_optimizer = optim.SGD(smart_meter1_model.parameters(), lr=args.lr)
smart_meter2_optimizer = optim.SGD(smart_meter2_model.parameters(), lr=args.lr)

models = [smart_meter1_model, smart_meter2_model]
optimizers = [smart_meter1_optimizer, smart_meter2_optimizer]

model = Net()
model

def update(data, target, model, optimizer):
    model.send(data.location)
    optimizer.zero_grad()
    prediction = model(data)
    loss = F.mse_loss(prediction.view(-1), target)
    # print('prediction', prediction.view(-1).shape)                              # this number here is [E] and should be equal to [F]
    # print('target', target.shape)                                               # this number here is [F] and should be equal to [E]
    loss.backward()
    optimizer.step()
    return model

def train():
    for data_index in range(len(remote_dataset[0])-1):
        for remote_index in range(len(compute_nodes)):
            data, target = remote_dataset[remote_index][data_index]
            models[remote_index] = update(data, target, models[remote_index], optimizers[remote_index])
        for model in models:
            model.get()
        return utils.federated_avg({
            "sm1": models[0],
            "sm2": models[1]
        })

def test(federated_model):
    federated_model.eval()
    test_loss = 0
    for data, target in test_loader:
        output = federated_model(data)
        test_loss += F.mse_loss(output.view(-1), target, reduction='sum').item()
        predection = output.data.max(1, keepdim=True)[1]
        
    test_loss /= len(test_loader.dataset)
    print('Test set: Average loss: {:.4f}'.format(test_loss))

for epoch in range(args.epochs):
    start_time = time.time()
    print(f"Epoch Number {epoch + 1}")
    federated_model = train()
    model = federated_model
    test(federated_model)
    total_time = time.time() - start_time
    print('Communication time over the network', round(total_time, 2), 's\n')

